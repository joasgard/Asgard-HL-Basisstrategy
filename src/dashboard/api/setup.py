"""
Setup wizard API endpoints (Privy-based authentication).
"""

from typing import Optional
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from fastapi.responses import RedirectResponse

from src.db.database import Database, get_db
from src.dashboard.auth import (
    session_manager, set_session_cookie, set_csrf_cookie,
    clear_session_cookies, PrivyAuth
)
from src.dashboard.setup import SetupJobManager, SetupSteps, SetupValidator
from src.dashboard.setup.jobs import JobType
from src.dashboard.security import sanitize_for_audit, SecretSanitizer

router = APIRouter(prefix="/setup", tags=["setup"])


def get_setup_steps(db: Database = Depends(get_db)) -> SetupSteps:
    """Dependency to get setup steps handler."""
    return SetupSteps(db=db)


def get_job_manager(db: Database = Depends(get_db)) -> SetupJobManager:
    """Dependency to get job manager."""
    return SetupJobManager(db=db)


@router.get("/status")
async def get_setup_status(
    db: Database = Depends(get_db)
) -> dict:
    """
    Get current setup progress.
    
    Returns:
        Current setup state and step
    """
    steps = SetupSteps(db=db)
    state = await steps.get_setup_state()
    
    return {
        "setup_complete": state.step >= 6,
        "current_step": state.step,
        "steps": state.to_dict()
    }


# Step 1: Privy Configuration & Authentication
@router.get("/privy/config")
async def privy_config_page(
    request: Request,
    db: Database = Depends(get_db)
):
    """Show Privy configuration form."""
    # Return HTML for step 1
    from src.dashboard.main import templates
    return templates.TemplateResponse(
        request, 
        "setup/step1_privy.html",
        context={"step": 1}
    )


@router.post("/privy/config")
async def configure_privy(
    request: Request,
    app_id: str = None,
    app_secret: str = None,
    auth_key: str = None,
    db: Database = Depends(get_db)
) -> dict:
    """
    Step 1a: Configure Privy credentials.
    
    Form: app_id=...&app_secret=...&auth_key=...
    """
    # Handle both form and JSON input
    if app_id is None:
        try:
            data = await request.form()
            app_id = data.get("app_id", "")
            app_secret = data.get("app_secret", "")
            auth_key = data.get("auth_key")
        except:
            data = await request.json()
            app_id = data.get("app_id", "")
            app_secret = data.get("app_secret", "")
            auth_key = data.get("auth_key")
    
    steps = SetupSteps(db=db)
    result = await steps.configure_privy(
        app_id=app_id,
        app_secret=app_secret,
        auth_key=auth_key
    )
    
    # Audit log (sanitized)
    await db.execute(
        "INSERT INTO audit_log (action, user, ip_address, details, success) VALUES (?, ?, ?, ?, ?)",
        ("setup_privy", "admin", request.client.host,
         sanitize_for_audit("setup_privy", {"app_id": app_id}),
         result["success"])
    )
    await db._connection.commit()
    
    if result["success"]:
        # Redirect to Privy auth
        return RedirectResponse(url="/setup/privy/auth", status_code=303)
    
    return result


@router.get("/privy/auth")
async def privy_auth_page(
    request: Request,
    db: Database = Depends(get_db)
):
    """Show Privy authentication page (email/social login)."""
    from src.dashboard.main import templates
    
    # Get Privy app ID for embedding
    app_id = await db.get_config("privy_app_id_plain")
    
    return templates.TemplateResponse(
        request,
        "setup/step1_privy_auth.html",
        context={
            "step": 1,
            "privy_app_id": app_id,
            "privy_configured": app_id is not None
        }
    )


@router.post("/privy/callback")
async def privy_callback(
    request: Request,
    response: Response,
    db: Database = Depends(get_db)
) -> dict:
    """
    Step 1b: Handle Privy OAuth callback.
    
    Form: token=... (Privy ID token)
    """
    try:
        data = await request.form()
        token = data.get("token")
    except:
        data = await request.json()
        token = data.get("token")
    
    if not token:
        return {"success": False, "error": "No token provided"}
    
    # Get Privy credentials
    app_id = await db.get_config("privy_app_id_plain")
    app_secret = await db.get_config("privy_app_secret_plain")
    
    if not app_id or not app_secret:
        return {"success": False, "error": "Privy not configured"}
    
    # Verify token with Privy
    try:
        privy = PrivyAuth(app_id, app_secret)
        user_info = await privy.verify_token(token)
        
        privy_user_id = user_info.get("id")
        email = user_info.get("email")
        
        # Mark auth complete
        steps = SetupSteps(db=db)
        await steps.complete_privy_auth(privy_user_id, email)
        
        # Create session with encryption
        settings = request.app.state.settings if hasattr(request.app.state, 'settings') else None
        server_secret = settings.session_secret if settings else "dev-secret-change-in-production"
        
        session = await session_manager.create_session(
            privy_user_id=privy_user_id,
            email=email,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent", ""),
            server_secret=server_secret
        )
        
        # Set cookies
        set_session_cookie(response, session.id)
        set_csrf_cookie(response, session.csrf_token)
        
        # Audit log
        await db.execute(
            "INSERT INTO audit_log (action, user, ip_address, details, success) VALUES (?, ?, ?, ?, ?)",
            ("privy_auth", privy_user_id, request.client.host,
             sanitize_for_audit("privy_auth", {"email": email}), True)
        )
        await db._connection.commit()
        
        return {"success": True, "message": "Authenticated", "redirect": "/setup"}
        
    except Exception as e:
        return {"success": False, "error": f"Authentication failed: {str(e)}"}


# Step 2: Wallet Creation (Async Job)
@router.post("/wallets")
async def create_wallets(
    request: Request,
    db: Database = Depends(get_db)
) -> dict:
    """
    Step 2: Create wallets via Privy (async job).
    
    Returns:
        {"job_id": "..."} - Poll GET /setup/jobs/{job_id} for status
    """
    job_manager = SetupJobManager(db=db)
    
    # Register wallet creation handler
    async def wallet_handler(params, progress_cb):
        steps = SetupSteps(db=db)
        return await steps.create_wallets(progress_callback=progress_cb)
    
    job_manager.register_handler(JobType.CREATE_WALLETS, wallet_handler)
    
    job_id = await job_manager.create_job(
        job_type=JobType.CREATE_WALLETS,
        params={}
    )
    
    # Audit log
    await db.execute(
        "INSERT INTO audit_log (action, user, ip_address, details, success) VALUES (?, ?, ?, ?, ?)",
        ("setup_create_wallets", "admin", request.client.host, "{}", True)
    )
    await db._connection.commit()
    
    return {"job_id": job_id, "status": "pending"}


# Step 3: Funding Verification
@router.get("/funding")
async def check_funding(
    db: Database = Depends(get_db)
) -> dict:
    """
    Step 3: Check wallet funding status.
    """
    steps = SetupSteps(db=db)
    result = await steps.check_funding()
    
    return result


@router.post("/funding/confirm")
async def confirm_funding(
    request: Request,
    db: Database = Depends(get_db)
) -> dict:
    """
    Step 3b: Manually confirm funding.
    """
    steps = SetupSteps(db=db)
    result = await steps.confirm_funding()
    
    await db.execute(
        "INSERT INTO audit_log (action, user, ip_address, details, success) VALUES (?, ?, ?, ?, ?)",
        ("setup_confirm_funding", "admin", request.client.host, "{}", result["success"])
    )
    await db._connection.commit()
    
    return result


# Step 3: Exchange Configuration
@router.post("/exchange")
async def configure_exchange(
    request: Request,
    asgard_api_key: str = None,
    hyperliquid_api_key: str = None,
    db: Database = Depends(get_db)
) -> dict:
    """
    Step 3: Configure exchange API keys.
    
    Form: asgard_api_key=...&hyperliquid_api_key=...
    """
    # Handle both form and JSON input
    if asgard_api_key is None:
        try:
            data = await request.form()
            asgard_api_key = data.get("asgard_api_key", "")
            hyperliquid_api_key = data.get("hyperliquid_api_key")
        except:
            data = await request.json()
            asgard_api_key = data.get("asgard_api_key", "")
            hyperliquid_api_key = data.get("hyperliquid_api_key")
    
    steps = SetupSteps(db=db)
    result = await steps.configure_exchange(
        asgard_api_key=asgard_api_key,
        hyperliquid_api_key=hyperliquid_api_key
    )
    
    # Audit log (sanitized)
    await db.execute(
        "INSERT INTO audit_log (action, user, ip_address, details, success) VALUES (?, ?, ?, ?, ?)",
        ("setup_exchange", "admin", request.client.host,
         sanitize_for_audit("setup_exchange"), result["success"])
    )
    await db._connection.commit()
    
    # On success, redirect to dashboard
    if result.get("success"):
        return RedirectResponse(url="/dashboard", status_code=303)
    
    return result


# Step 5: Strategy Configuration
@router.post("/strategy")
async def configure_strategy(
    request: Request,
    risk_preset: str = None,
    leverage: float = None,
    max_position_size: float = None,
    db: Database = Depends(get_db)
) -> dict:
    """
    Step 5: Configure trading strategy.
    
    Form: risk_preset=...&leverage=...&max_position_size=...
    """
    # Handle both form and JSON input
    if risk_preset is None:
        try:
            data = await request.form()
            risk_preset = data.get("risk_preset", "balanced")
            leverage = float(data.get("leverage", 3.0))
            max_position_size = data.get("max_position_size")
            if max_position_size:
                max_position_size = float(max_position_size)
        except:
            data = await request.json()
            risk_preset = data.get("risk_preset", "balanced")
            leverage = data.get("leverage", 3.0)
            max_position_size = data.get("max_position_size")
    else:
        # Use defaults if not provided
        if risk_preset is None:
            risk_preset = "balanced"
        if leverage is None:
            leverage = 3.0
    
    steps = SetupSteps(db=db)
    result = await steps.configure_strategy(
        risk_preset=risk_preset,
        leverage=leverage,
        max_position_size=max_position_size
    )
    
    await db.execute(
        "INSERT INTO audit_log (action, user, ip_address, details, success) VALUES (?, ?, ?, ?, ?)",
        ("setup_strategy", "admin", request.client.host,
         sanitize_for_audit("setup_strategy", {"risk_preset": risk_preset}), result["success"])
    )
    await db._connection.commit()
    
    return result


# Step 6: Finalize and Launch
@router.post("/launch")
async def finalize_setup(
    request: Request,
    db: Database = Depends(get_db)
) -> dict:
    """
    Step 6: Finalize setup and encrypt all credentials.
    
    Requires active session with unlocked encryption.
    """
    from src.dashboard.auth import get_current_session
    
    try:
        session = await get_current_session(request)
    except HTTPException:
        return {"success": False, "error": "Session required - please log in"}
    
    if not session.encryption_manager.is_unlocked:
        return {"success": False, "error": "Encryption not unlocked"}
    
    steps = SetupSteps(db=db)
    result = await steps.finalize_setup(session.encryption_manager)
    
    await db.execute(
        "INSERT INTO audit_log (action, user, ip_address, details, success) VALUES (?, ?, ?, ?, ?)",
        ("setup_launch", "admin", request.client.host, "{}", result["success"])
    )
    await db._connection.commit()
    
    return result


# Job status polling
@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    db: Database = Depends(get_db)
) -> dict:
    """
    Get status of an async setup job.
    
    Returns:
        Job status with progress
    """
    job_manager = SetupJobManager(db=db)
    status = await job_manager.get_status(job_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return status


# Logout endpoint
@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Database = Depends(get_db)
) -> dict:
    """Logout and clear session."""
    session_id = request.cookies.get("session_id")
    
    if session_id:
        await session_manager.destroy_session(session_id)
    
    clear_session_cookies(response)
    
    return {"success": True, "message": "Logged out"}
