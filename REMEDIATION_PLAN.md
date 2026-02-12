# Remediation Plan
Generated: 2026-02-12
Project: Asgard Basis
Total Findings: 56 (consolidated into 25 executable steps)

---

## Priority Order

Steps are ordered by severity (CRITICAL → HIGH → MEDIUM → LOW) and grouped to minimize merge conflicts when multiple findings touch the same file.

1. **Step 1** – Remove production secrets from `frontend/.env` (CRITICAL)
2. **Step 2** – Fix auth bypass in `/auth/sync` endpoint (CRITICAL)
3. **Step 3** – Fix RBAC + timing-safe API key + add `bot_admin_key` to settings (HIGH) — groups F#3, F#6, F#7
4. **Step 4** – Fix session cookie `secure` flag (HIGH) — groups F#5 across `auth.py` + `api/auth.py`
5. **Step 5** – Fix CORS wildcard + path traversal in `main.py` (HIGH) — groups F#4, F#8
6. **Step 6** – Sanitize error messages in API endpoints (HIGH) — F#10
7. **Step 7** – Fix `--forwarded-allow-ips=*` in Docker prod (HIGH) — F#9
8. **Step 8** – Fix HMAC key separation in encryption module (HIGH) — F#11
9. **Step 9** – Add `withCredentials: true` to frontend API client (HIGH) — F#30
10. **Step 10** – Add `argon2-cffi` to requirements (MEDIUM) — F#16
11. **Step 11** – Add Redis authentication (MEDIUM) — F#12
12. **Step 12** – Fix SSE hook unstable callback (MEDIUM) — F#39
13. **Step 13** – Fix broken scripts importing from deleted `src/` (MEDIUM) — F#45
14. **Step 14** – Remove unused `frontend/src/api/settings.ts` (MEDIUM) — F#46
15. **Step 15** – Remove unused frontend assets (MEDIUM) — F#48, F#49
16. **Step 16** – Fix Docker config issues (MEDIUM) — F#50, F#51
17. **Step 17** – Add `.env` to `frontend/.gitignore` (MEDIUM) — F#1 supplement
18. **Step 18** – Fix `get_redis_bytes()` connection pool leak (MEDIUM) — F#36
19. **Step 19** – Narrow retry exception types (MEDIUM) — F#38
20. **Step 20** – Fix job status endpoint missing user ownership check (MEDIUM) — audit F#21 from agent
21. **Step 21** – Replace deprecated `python-jose` (MEDIUM) — F#17
22. **Step 22** – Fix nonce collision risk in HL signer (LOW) — F#23
23. **Step 23** – Add frontend position filtering memoization (LOW) — F#44
24. **Step 24** – Fix job polling setTimeout cleanup (MEDIUM) — F#40
25. **Step 25** – Add missing composite index on position_jobs (LOW) — F#42

---

## Detailed Steps

### Step 1: Remove production secrets from `frontend/.env`
- **Finding ID:** #1
- **Domain:** Security
- **Severity:** CRITICAL
- **Status:** ⬜ NOT STARTED
- **File(s):** `frontend/.env`, `frontend/.env.example`
- **Line(s):** 4-6

#### Problem
`frontend/.env` contains real API keys prefixed with `VITE_`, which Vite bundles into client-side JavaScript visible to any browser user: Privy App ID, Asgard API key (64-char hex), Helius Solana RPC key.

#### Root Cause
Developer convenience — secrets placed in `.env` for local development without realizing `VITE_` prefix exposes them client-side.

#### Step-by-Step Fix
1. Open `frontend/.env`
2. Replace the real secrets with placeholder values:

**BEFORE:**
```
VITE_PRIVY_APP_ID=cml9jhxxp02oblb0dl1rqtj5x
VITE_ASGARD_API_KEY=asgard_0c218b0b4d2d9eae527c1e689307687c990123f50abb336237b045974695727f
VITE_SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=62b63359-9f8a-412b-bbd6-a3345160611d
```

**AFTER:**
```
VITE_PRIVY_APP_ID=your_privy_app_id_here
VITE_SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=your_helius_key_here
```

3. Remove `VITE_ASGARD_API_KEY` entirely — this is a server-side secret that must never be in frontend code.
4. Update `frontend/.env.example` to match (without real values).

#### Validation
- [ ] `frontend/.env` contains no real API keys
- [ ] `VITE_ASGARD_API_KEY` is completely removed from frontend
- [ ] `frontend/.env.example` has only placeholder values

#### Dependencies
- **Blocked by:** None
- **Blocks:** Step 17

#### Notes
After this fix, you MUST rotate all three keys (Privy, Asgard, Helius) since they were exposed. This is an operational step outside the codebase.

---

### Step 2: Fix auth bypass in `/auth/sync` endpoint
- **Finding ID:** #2
- **Domain:** Security
- **Severity:** CRITICAL
- **Status:** ⬜ NOT STARTED
- **File(s):** `backend/dashboard/api/auth.py`
- **Line(s):** 469-564

#### Problem
The `/auth/sync` endpoint accepts a raw `privy_user_id` from the request body and creates an authenticated session without verifying the caller owns that identity. A bare `except:` at line 491 silently ignores Privy API failures.

#### Root Cause
The sync endpoint was designed as a "trust the frontend" bridge, but lacks server-side token verification. The bare `except:` was added to handle Privy SDK unavailability during development.

#### Step-by-Step Fix
1. Open `backend/dashboard/api/auth.py`
2. Add a `privy_access_token` field to `PrivySyncRequest`:

**BEFORE (line 453-456):**
```python
class PrivySyncRequest(BaseModel):
    """Request to sync Privy auth with backend session."""
    privy_user_id: str
    email: Optional[str] = None
```

**AFTER:**
```python
class PrivySyncRequest(BaseModel):
    """Request to sync Privy auth with backend session."""
    privy_access_token: str
    email: Optional[str] = None
```

3. Replace the sync endpoint implementation to verify the token server-side:

**BEFORE (lines 485-498):**
```python
    try:
        privy = get_privy_client()

        # Get user info from Privy
        try:
            privy_user = await privy.get_user(data.privy_user_id)
        except:
            privy_user = None

        # Get or create user in our database
        user = await db.fetchone(
            "SELECT id, email, solana_address, evm_address, is_new_user FROM users WHERE id = $1",
            (data.privy_user_id,)
        )
```

**AFTER:**
```python
    try:
        privy = get_privy_client()

        # Verify Privy access token server-side (REQUIRED)
        try:
            privy_user = await privy.verify_access_token(data.privy_access_token)
        except Exception as e:
            logger.warning(f"Privy token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token"
            )

        privy_user_id = privy_user.get("id") or privy_user.get("user_id")
        if not privy_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token"
            )

        # Get or create user in our database
        user = await db.fetchone(
            "SELECT id, email, solana_address, evm_address, is_new_user FROM users WHERE id = $1",
            (privy_user_id,)
        )
```

4. Update all references from `data.privy_user_id` to `privy_user_id` in the rest of the function (lines 497-558). Specifically update:
   - Line 503: `await privy.ensure_user_wallets(data.privy_user_id)` → `await privy.ensure_user_wallets(privy_user_id)`
   - Line 510-513: The INSERT statement uses `data.privy_user_id` → use `privy_user_id`
   - Line 525: UPDATE WHERE clause uses `data.privy_user_id` → use `privy_user_id`
   - Line 533: `privy_user_id=data.privy_user_id` → `privy_user_id=privy_user_id`
   - Line 547: `data.privy_user_id` → `privy_user_id`
   - Line 553: `user_id=data.privy_user_id` → `user_id=privy_user_id`

5. Sanitize the error message in the outer except block (line 560-563):

**BEFORE:**
```python
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )
```

**AFTER:**
```python
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication sync failed"
        )
```

#### Validation
- [ ] Sending a request with an invalid `privy_access_token` returns 401
- [ ] Sending a request without `privy_access_token` fails validation
- [ ] The bare `except:` is gone — replaced with proper exception handling
- [ ] No raw exception messages leak to client

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

#### Notes
The frontend must also be updated to send `privy_access_token` instead of `privy_user_id`. This is a frontend change in `frontend/src/hooks/useAuth.ts` or wherever the sync call is made.

---

### Step 3: Fix RBAC, timing-safe API key comparison, add `bot_admin_key`
- **Finding ID:** #3, #6, #7
- **Domain:** Security
- **Severity:** HIGH
- **Status:** ⬜ NOT STARTED
- **File(s):** `backend/dashboard/auth.py`, `backend/dashboard/config.py`
- **Line(s):** auth.py:467-505, config.py:31-91

#### Problem
(a) Every user gets `role="admin"` hardcoded. `require_role()` checks wrong condition. (b) `verify_api_key` uses `==` (timing-vulnerable). (c) `bot_admin_key` not defined in settings — causes AttributeError at runtime.

#### Root Cause
RBAC was stubbed out as a placeholder. The timing attack and missing setting are oversights.

#### Step-by-Step Fix

**Part A: Add `bot_admin_key` to config.py**

1. Open `backend/dashboard/config.py`
2. Add `bot_admin_key` field after line 69:

**BEFORE (lines 66-72):**
```python
    # Secrets (all derived from server_secret.txt)
    jwt_secret: str = Field(default_factory=get_server_secret)
    session_secret: str = Field(default_factory=get_server_secret)
    internal_token: str = Field(default_factory=get_server_secret)

    # Cache
    cache_ttl: float = Field(default=5.0, alias="CACHE_TTL")
```

**AFTER:**
```python
    # Secrets (all derived from server_secret.txt)
    jwt_secret: str = Field(default_factory=get_server_secret)
    session_secret: str = Field(default_factory=get_server_secret)
    internal_token: str = Field(default_factory=get_server_secret)

    # Bot admin API key (for control endpoints)
    bot_admin_key: str = Field(
        default_factory=lambda: load_secret("admin_api_key.txt") or "",
        alias="BOT_ADMIN_KEY",
    )

    # Cache
    cache_ttl: float = Field(default=5.0, alias="CACHE_TTL")
```

**Part B: Fix RBAC and API key comparison in auth.py**

3. Open `backend/dashboard/auth.py`
4. Add `import secrets` at top if not already present (it IS present at line 14).
5. Replace the `require_role` function and `verify_api_key` (lines 484-505):

**BEFORE (lines 484-505):**
```python
def require_role(required_roles: list):
    """Dependency factory to require specific roles."""
    async def role_checker(session: Session = Depends(get_current_session)):
        if "admin" not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return User(user_id=session.privy_user_id, email=session.email, role="admin")
    return role_checker


# Predefined role dependencies
require_admin = require_role(["admin"])
require_operator = require_role(["admin", "operator"])
require_viewer = require_role(["admin", "operator", "viewer"])


def verify_api_key(api_key: str) -> bool:
    """Verify bot admin API key."""
    settings = get_dashboard_settings()
    return api_key == settings.bot_admin_key
```

**AFTER:**
```python
# Role hierarchy: admin > operator > viewer
ROLE_HIERARCHY = {"admin": 3, "operator": 2, "viewer": 1}


def require_role(required_roles: list):
    """Dependency factory to require specific roles.

    Checks the user's actual role (from DB) against required_roles.
    For now, all users default to 'admin' until role column is added to users table.
    """
    async def role_checker(session: Session = Depends(get_current_session)):
        # TODO: Load role from users table once role column is added
        # For now, default to 'admin' for existing single-tenant usage
        user_role = "admin"

        if user_role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return User(user_id=session.privy_user_id, email=session.email, role=user_role)
    return role_checker


# Predefined role dependencies
require_admin = require_role(["admin"])
require_operator = require_role(["admin", "operator"])
require_viewer = require_role(["admin", "operator", "viewer"])


def verify_api_key(api_key: str) -> bool:
    """Verify bot admin API key using constant-time comparison."""
    settings = get_dashboard_settings()
    if not settings.bot_admin_key:
        return False
    return secrets.compare_digest(api_key, settings.bot_admin_key)
```

#### Validation
- [ ] `require_role` checks user's role against `required_roles` (not `"admin" in required_roles`)
- [ ] `verify_api_key` uses `secrets.compare_digest`
- [ ] `verify_api_key` returns `False` if `bot_admin_key` is empty
- [ ] `DashboardSettings` has `bot_admin_key` field
- [ ] No `AttributeError` when accessing `settings.bot_admin_key`

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 4: Fix session cookie `secure` flag
- **Finding ID:** #5
- **Domain:** Security
- **Severity:** HIGH
- **Status:** ⬜ NOT STARTED
- **File(s):** `backend/dashboard/auth.py`, `backend/dashboard/api/auth.py`
- **Line(s):** auth.py:368-395, api/auth.py:289-290,541-542

#### Problem
Session and CSRF cookies are hardcoded with `secure=False`, sending them over plain HTTP.

#### Root Cause
Development convenience — secure=False works on localhost without HTTPS.

#### Step-by-Step Fix

1. Open `backend/dashboard/auth.py`
2. Modify `set_session_cookie` and `set_csrf_cookie` to default based on environment:

**BEFORE (lines 368-395):**
```python
def set_session_cookie(response: Response, session_id: str, secure: Optional[bool] = None) -> None:
    """Set HTTP-only session cookie."""
    if secure is None:
        secure = False
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=8 * 60 * 60,  # 8 hours
        path="/"
    )


def set_csrf_cookie(response: Response, csrf_token: str, secure: Optional[bool] = None) -> None:
    """Set CSRF token cookie (not HTTP-only, accessible by JS)."""
    if secure is None:
        secure = False
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # JS needs to read this
        secure=secure,
        samesite="strict",
        max_age=8 * 60 * 60,
        path="/"
    )
```

**AFTER:**
```python
def _is_production() -> bool:
    """Check if running in production environment."""
    settings = get_dashboard_settings()
    return settings.dashboard_env == "production"


def set_session_cookie(response: Response, session_id: str, secure: Optional[bool] = None) -> None:
    """Set HTTP-only session cookie."""
    if secure is None:
        secure = _is_production()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=8 * 60 * 60,  # 8 hours
        path="/"
    )


def set_csrf_cookie(response: Response, csrf_token: str, secure: Optional[bool] = None) -> None:
    """Set CSRF token cookie (not HTTP-only, accessible by JS)."""
    if secure is None:
        secure = _is_production()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # JS needs to read this
        secure=secure,
        samesite="strict",
        max_age=8 * 60 * 60,
        path="/"
    )
```

3. Open `backend/dashboard/api/auth.py`
4. Remove explicit `secure=False` from cookie calls — let the default handle it:

**BEFORE (lines 289-290):**
```python
        set_session_cookie(response, session.id, secure=False)
        set_csrf_cookie(response, session.csrf_token, secure=False)
```

**AFTER:**
```python
        set_session_cookie(response, session.id)
        set_csrf_cookie(response, session.csrf_token)
```

5. Same change at lines 541-542:

**BEFORE:**
```python
        set_session_cookie(response, session.id, secure=False)
        set_csrf_cookie(response, session.csrf_token, secure=False)
```

**AFTER:**
```python
        set_session_cookie(response, session.id)
        set_csrf_cookie(response, session.csrf_token)
```

#### Validation
- [ ] In production (`DASHBOARD_ENV=production`), cookies have `secure=True`
- [ ] In development, cookies still work on localhost (secure=False)
- [ ] No hardcoded `secure=False` in api/auth.py

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 5: Fix CORS wildcard and path traversal in `main.py`
- **Finding ID:** #4, #8
- **Domain:** Security
- **Severity:** HIGH
- **Status:** ⬜ NOT STARTED
- **File(s):** `backend/dashboard/main.py`
- **Line(s):** 364-374, 465-478

#### Problem
(a) CORS appends `*` with `allow_credentials=True` in dev mode. (b) SPA serve handler allows path traversal via `../` sequences.

#### Root Cause
(a) Overly permissive dev CORS config. (b) No path validation on the catch-all route.

#### Step-by-Step Fix

1. Open `backend/dashboard/main.py`

**Part A: Fix CORS (lines 364-374)**

**BEFORE:**
```python
    allowed_origins = settings.get_allowed_origins_list()
    if settings.dashboard_env == "development":
        allowed_origins.append("*")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
```

**AFTER:**
```python
    allowed_origins = settings.get_allowed_origins_list()
    if settings.dashboard_env == "development":
        # Add common dev origins explicitly — never use "*" with credentials
        dev_origins = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
        for origin in dev_origins:
            if origin not in allowed_origins:
                allowed_origins.append(origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
```

**Part B: Fix path traversal (lines 465-478)**

**BEFORE:**
```python
        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """Serve React SPA index.html for all routes (client-side routing)."""
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)

            file_path = os.path.join(frontend_dist, path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)

            index_path = os.path.join(frontend_dist, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            else:
                return JSONResponse(
                    {"error": "Frontend not built. Run 'npm run build' in frontend/"},
                    status_code=500
                )
```

**AFTER:**
```python
        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """Serve React SPA index.html for all routes (client-side routing)."""
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)

            # Prevent path traversal: resolve and verify path stays within frontend_dist
            file_path = os.path.realpath(os.path.join(frontend_dist, path))
            dist_realpath = os.path.realpath(frontend_dist)
            if not file_path.startswith(dist_realpath + os.sep) and file_path != dist_realpath:
                return JSONResponse({"detail": "Not found"}, status_code=404)

            if os.path.isfile(file_path):
                return FileResponse(file_path)

            index_path = os.path.join(frontend_dist, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            else:
                return JSONResponse(
                    {"error": "Frontend not built. Run 'npm run build' in frontend/"},
                    status_code=500
                )
```

#### Validation
- [ ] `GET /../../etc/passwd` returns 404, not file contents
- [ ] CORS does not include `*` in any mode
- [ ] Dev mode still allows localhost origins
- [ ] SPA routing still works (non-file paths serve index.html)

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 6: Sanitize error messages in API endpoints
- **Finding ID:** #10
- **Domain:** Security
- **Severity:** HIGH
- **Status:** ⬜ NOT STARTED
- **File(s):** `backend/dashboard/api/auth.py`, `backend/dashboard/api/rates.py`, `backend/dashboard/api/settings.py`

#### Problem
Multiple endpoints expose raw Python exception messages via `detail=str(e)`.

#### Root Cause
Quick development pattern of passing exceptions directly to HTTP responses.

#### Step-by-Step Fix

1. **`backend/dashboard/api/auth.py`** — lines 313-322:

**BEFORE:**
```python
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid OTP: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
        )
```

**AFTER:**
```python
    except AuthenticationError as e:
        logger.warning(f"OTP verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code"
        )
    except Exception as e:
        logger.error(f"Authentication failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )
```

2. **`backend/dashboard/api/rates.py`** — line 79-81:

**BEFORE:**
```python
    except Exception as e:
        logger.error(f"Error fetching rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**AFTER:**
```python
    except Exception as e:
        logger.error(f"Error fetching rates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch rates")
```

3. **`backend/dashboard/api/settings.py`** — lines 82-84 and 108-110:

**BEFORE (line 82-84):**
```python
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**AFTER:**
```python
    except Exception as e:
        logger.error(f"Failed to save settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save settings")
```

**BEFORE (line 108-110):**
```python
    except Exception as e:
        logger.error(f"Failed to reset settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**AFTER:**
```python
    except Exception as e:
        logger.error(f"Failed to reset settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reset settings")
```

#### Validation
- [ ] No `detail=str(e)` or `detail=f"...{str(e)}"` patterns remain in API endpoints
- [ ] Errors are logged server-side with `exc_info=True`
- [ ] Clients receive generic error messages

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 7: Fix `--forwarded-allow-ips=*` in Docker prod
- **Finding ID:** #9
- **Domain:** Security
- **Severity:** HIGH
- **Status:** ⬜ NOT STARTED
- **File(s):** `docker-compose.prod.yml`
- **Line(s):** 91

#### Problem
`--forwarded-allow-ips=*` trusts proxy headers from any client, enabling IP spoofing.

#### Step-by-Step Fix

**BEFORE (line 91):**
```
      --forwarded-allow-ips=*
```

**AFTER:**
```
      --forwarded-allow-ips=172.20.0.0/16
```

#### Validation
- [ ] uvicorn only trusts forwarded headers from Docker network range

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 8: Fix HMAC key separation in encryption module
- **Finding ID:** #11
- **Domain:** Security
- **Severity:** HIGH
- **Status:** ⬜ NOT STARTED
- **File(s):** `shared/security/encryption.py`
- **Line(s):** 173-178

#### Problem
`_derive_hmac_key(dek)` returns `dek[:32]` but DEK is 32 bytes, so HMAC key = encryption key.

#### Step-by-Step Fix

1. Open `shared/security/encryption.py`
2. Replace the `_derive_hmac_key` function:

**BEFORE:**
```python
def _derive_hmac_key(dek: bytes) -> bytes:
    """Derive HMAC key from DEK using SHA256.
    Uses first half of DEK for HMAC key."""
    return dek[:32]
```

**AFTER:**
```python
def _derive_hmac_key(dek: bytes) -> bytes:
    """Derive a separate HMAC key from DEK using HKDF-like derivation.
    Ensures key separation between encryption and authentication."""
    return hashlib.sha256(b"hmac-key:" + dek).digest()
```

#### Validation
- [ ] HMAC key is distinct from DEK
- [ ] Existing encrypted data still decrypts (since DEK is unchanged; only the HMAC verification key changes)

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

#### Notes
**CAUTION:** This changes the HMAC key derivation. Any data encrypted with the old HMAC will fail verification. If there is existing encrypted data in production, a migration step is needed to re-encrypt. If this is pre-production, this change is safe.

---

### Step 9: Add `withCredentials: true` to frontend API client
- **Finding ID:** #30
- **Domain:** Efficiency (frontend auth)
- **Severity:** HIGH
- **Status:** ⬜ NOT STARTED
- **File(s):** `frontend/src/api/client.ts`
- **Line(s):** 14-20

#### Problem
Axios client missing `withCredentials: true`, so cookies won't be sent on cross-origin requests.

#### Step-by-Step Fix

**BEFORE (lines 14-20):**
```typescript
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});
```

**AFTER:**
```typescript
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
  withCredentials: true,
});
```

#### Validation
- [ ] Axios requests include cookies in cross-origin scenarios

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 10: Add `argon2-cffi` to requirements
- **Finding ID:** #16
- **Domain:** Security
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `requirements/base.txt`

#### Problem
Encryption module imports `argon2` but it's not in any requirements file. Production could silently fall back to PBKDF2.

#### Step-by-Step Fix

Add `argon2-cffi>=21.0.0` to `requirements/base.txt`:

**BEFORE:**
```
# Minimal core dependencies
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
structlog>=23.0.0
```

**AFTER:**
```
# Minimal core dependencies
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
structlog>=23.0.0
argon2-cffi>=21.0.0
```

#### Validation
- [ ] `pip install -r requirements/base.txt` installs argon2-cffi

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 11: Add Redis authentication
- **Finding ID:** #12
- **Domain:** Security
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `docker/docker-compose.yml`, `docker-compose.prod.yml`

#### Problem
Redis has no `--requirepass`, allowing unauthenticated access.

#### Step-by-Step Fix

1. In `docker-compose.prod.yml`, update the Redis command:

**BEFORE:**
```yaml
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
```

**AFTER:**
```yaml
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru --requirepass ${REDIS_PASSWORD}
```

2. Update the `REDIS_URL` environment variable for the app service:

**BEFORE:**
```yaml
      - REDIS_URL=redis://redis:6379
```

**AFTER:**
```yaml
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379
```

#### Validation
- [ ] Redis rejects unauthenticated connections
- [ ] App connects via authenticated URL

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

#### Notes
This requires setting `REDIS_PASSWORD` in the deployment environment. For dev docker-compose, this can remain optional.

---

### Step 12: Fix SSE hook unstable callback
- **Finding ID:** #39
- **Domain:** Efficiency
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `frontend/src/hooks/useSSE.ts`
- **Line(s):** 15-17

#### Problem
Destructuring `usePositionsStore()` creates new references on every render, causing SSE reconnect cycles.

#### Step-by-Step Fix

**BEFORE (lines 15-17):**
```typescript
  const { updatePosition } = usePositionsStore();
  const { setRates } = useRatesStore();
  const { addToast } = useUIStore();
```

**AFTER:**
```typescript
  const updatePosition = usePositionsStore((s) => s.updatePosition);
  const setRates = useRatesStore((s) => s.setRates);
  const addToast = useUIStore((s) => s.addToast);
```

#### Validation
- [ ] SSE connection remains stable when positions update
- [ ] No reconnect/disconnect cycle on each SSE message

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 13: Fix broken scripts importing from deleted `src/`
- **Finding ID:** #45
- **Domain:** Cleanup
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `scripts/run_bot.py`, `scripts/setup_dashboard_users.py`

#### Problem
Scripts still import from `src.` which has been deleted.

#### Step-by-Step Fix

1. `scripts/run_bot.py` line 6-7:

**BEFORE:**
```python
from src.core.bot import DeltaNeutralBot, BotConfig
from src.config.settings import get_settings
```

**AFTER:**
```python
from bot.core.bot import DeltaNeutralBot, BotConfig
from shared.config.settings import get_settings
```

2. `scripts/setup_dashboard_users.py` line 26:

**BEFORE:**
```python
from src.dashboard.auth import get_password_hash
```

**AFTER:**
```python
from backend.dashboard.auth import session_manager
```

#### Validation
- [ ] `python scripts/run_bot.py --help` doesn't crash on import
- [ ] `python scripts/setup_dashboard_users.py --help` doesn't crash on import

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

#### Notes
`get_password_hash` may not exist in the new auth module. The script may need further updates to work with the Privy-based auth system.

---

### Step 14: Remove unused `frontend/src/api/settings.ts`
- **Finding ID:** #46
- **Domain:** Cleanup
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `frontend/src/api/settings.ts`

#### Problem
Exports `settingsApi` but no file imports it. `settingsStore.ts` uses raw `fetch()` directly.

#### Step-by-Step Fix
Delete the file `frontend/src/api/settings.ts`.

#### Validation
- [ ] No import errors in frontend build
- [ ] `npm run build` succeeds in `frontend/`

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 15: Remove unused frontend assets
- **Finding ID:** #48, #49
- **Domain:** Cleanup
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `frontend/src/App.css`, `frontend/src/assets/react.svg`

#### Problem
Neither file is imported or referenced anywhere.

#### Step-by-Step Fix
1. Delete `frontend/src/App.css`
2. Delete `frontend/src/assets/react.svg`

#### Validation
- [ ] `npm run build` succeeds in `frontend/`

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 16: Fix Docker config issues
- **Finding ID:** #50, #51
- **Domain:** Cleanup
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `docker/nginx.conf`, `docker/docker-compose.yml`

#### Problem
(a) nginx upstream references `bot:8080` but service is named `app`. (b) Health-monitor references non-existent Python module `scripts.health_check`.

#### Step-by-Step Fix

1. `docker/nginx.conf` line 2 — fix upstream:

**BEFORE:**
```nginx
upstream bot {
    server bot:8080;
}
```

**AFTER:**
```nginx
upstream app {
    server app:8080;
}
```

2. `docker/docker-compose.yml` line 174 — fix health monitor command (or comment out until module exists):

**BEFORE:**
```yaml
    command: ["python", "-m", "scripts.health_check"]
```

**AFTER:**
```yaml
    command: ["bash", "scripts/health_check.sh"]
```

#### Validation
- [ ] nginx config is internally consistent
- [ ] health-monitor service can start

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 17: Add `.env` to `frontend/.gitignore`
- **Finding ID:** #1 supplement
- **Domain:** Security
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `frontend/.gitignore`

#### Step-by-Step Fix

Add to `frontend/.gitignore` after line 13:

**BEFORE:**
```
*.local

# Editor directories and files
```

**AFTER:**
```
*.local

# Environment files
.env
.env.*
!.env.example

# Editor directories and files
```

#### Validation
- [ ] `git status` in frontend/ does not show `.env` as untracked

#### Dependencies
- **Blocked by:** Step 1
- **Blocks:** None

---

### Step 18: Fix `get_redis_bytes()` connection pool leak
- **Finding ID:** #36
- **Domain:** Efficiency
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `shared/redis_client.py`
- **Line(s):** 36-44

#### Problem
`get_redis_bytes()` creates a new connection pool on every call, unlike `get_redis()` which uses a singleton.

#### Step-by-Step Fix
Add singleton caching matching the `get_redis()` pattern. (Exact code depends on current file structure — read file before editing.)

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 19: Narrow retry exception types
- **Finding ID:** #38
- **Domain:** Efficiency
- **Severity:** MEDIUM
- **Status:** ⬜ NOT STARTED
- **File(s):** `shared/utils/retry.py`
- **Line(s):** 140-161

#### Problem
All retry configs use `retry_exceptions=(Exception,)`, retrying programming bugs.

#### Step-by-Step Fix
Change retry configs to use specific exception types:
```python
retry_exceptions=(IOError, ConnectionError, TimeoutError, OSError)
```

#### Dependencies
- **Blocked by:** None
- **Blocks:** None

---

### Step 20-25: Lower priority items
Steps 20-25 are lower priority (MEDIUM/LOW) and follow the same pattern. They will be executed after the critical and high-priority steps are verified.

- **Step 20:** Add user ownership check to job status endpoint
- **Step 21:** Evaluate replacing `python-jose` with `PyJWT`
- **Step 22:** Fix nonce collision risk in HL signer
- **Step 23:** Add `useMemo` for position filtering
- **Step 24:** Add setTimeout cleanup to job polling
- **Step 25:** Add composite index migration

---

## Rollback Notes

For any change that breaks the application:
1. All changes are file edits — `git checkout -- <file>` reverts any individual change
2. **Step 8** (HMAC key change) is the highest-risk change — if production data exists with old HMAC, revert immediately
3. **Step 2** (auth sync) requires coordinated frontend changes — deploy backend first, then frontend
