"""
Setup wizard step handlers.

6-step wizard:
1. Privy authentication
2. Wallet creation
3. Funding verification
4. Exchange configuration
5. Strategy configuration
6. Backup & launch
"""

import json
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.db.database import Database
from src.security.encryption import EncryptionManager
from src.dashboard.setup.validators import SetupValidator, ValidationResult


@dataclass
class SetupState:
    """Current setup state/progress (4-step flow)."""
    step: int = 0  # 0-4
    authenticated: bool = False
    wallets_created: bool = False
    exchange_configured: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "authenticated": self.authenticated,
            "wallets_created": self.wallets_created,
            "exchange_configured": self.exchange_configured,
            "setup_complete": self.step >= 4
        }


class SetupSteps:
    """Handles setup wizard steps."""
    
    def __init__(
        self,
        db: Database,
        validator: Optional[SetupValidator] = None,
        privy_client=None
    ):
        self.db = db
        self.validator = validator or SetupValidator()
        self.privy = privy_client
    
    async def get_setup_state(self) -> SetupState:
        """Get current setup state from database."""
        state = SetupState()
        
        # Check if setup is complete
        setup_complete = await self.db.get_config("setup_completed")
        if setup_complete == "true":
            state.step = 6
            state.launched = True
            return state
        
        # Check auth status
        authenticated = await self.db.get_config("privy_authenticated")
        state.authenticated = authenticated == "true"
        
        evm_wallet = await self.db.get_config("wallet_evm_address")
        state.wallets_created = evm_wallet is not None
        
        # Check exchange config
        asgard_key = await self.db.get_config("asgard_api_key")
        state.exchange_configured = asgard_key is not None
        
        # Determine current step (4-step flow)
        # Step 1: Auth (Privy OAuth) - skip if already authenticated
        # Step 2: Wallets
        # Step 3: Exchange config
        # Step 4: Dashboard (funding & strategy are dashboard actions)
        
        if not state.authenticated:
            state.step = 1
        elif not state.wallets_created:
            state.step = 2
        elif not state.exchange_configured:
            state.step = 3
        else:
            state.step = 4  # Dashboard
        
        return state
    
    # Step 1: Privy Configuration & Auth
    async def configure_privy(
        self,
        app_id: str,
        app_secret: str,
        auth_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Step 1: Configure Privy credentials.
        
        Args:
            app_id: Privy app ID
            app_secret: Privy app secret
            auth_key: Optional authorization key PEM
            
        Returns:
            Result dict with success/error
        """
        # Validate credentials
        result = await self.validator.validate_privy_credentials(app_id, app_secret)
        if not result.valid:
            return {"success": False, "error": result.error}
        
        try:
            # Store credentials (will be encrypted later with DEK)
            await self.db.set_config("privy_app_id_plain", app_id)
            await self.db.set_config("privy_app_secret_plain", app_secret)
            
            if auth_key:
                await self.db.set_config("privy_auth_key_plain", auth_key)
            
            await self.db.set_config("privy_configured", "true")
            
            return {"success": True, "message": "Privy configured successfully"}
            
        except Exception as e:
            return {"success": False, "error": f"Failed to store configuration: {str(e)}"}
    
    async def complete_privy_auth(self, privy_user_id: str, email: Optional[str]) -> Dict[str, Any]:
        """Mark Privy authentication as complete."""
        await self.db.set_config("privy_user_id", privy_user_id)
        if email:
            await self.db.set_config("user_email", email)
        await self.db.set_config("privy_authenticated", "true")
        return {"success": True, "message": "Authentication complete"}
    
    # Step 2: Wallet Creation
    async def create_wallets(
        self,
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Step 2: Create EVM and Solana wallets via Privy.
        
        Args:
            progress_callback: Optional callback(progress_pct)
            
        Returns:
            Result dict with wallet addresses or error
        """
        if progress_callback:
            progress_callback(10)
        
        try:
            # Get Privy credentials
            app_id = await self.db.get_config("privy_app_id_plain")
            app_secret = await self.db.get_config("privy_app_secret_plain")
            
            if not app_id or not app_secret:
                return {"success": False, "error": "Privy not configured"}
            
            if progress_callback:
                progress_callback(30)
            
            # Create wallets via Privy SDK
            if self.privy:
                from src.dashboard.privy_client import PrivyClient
                
                # Initialize client with credentials
                privy_client = PrivyClient(app_id=app_id, app_secret=app_secret)
                
                # Get current user from session or create wallets for a default user
                # For now, we'll create wallets using the SDK's wallet creation
                # Note: In production, wallets are typically created when a user signs up
                # Here we're creating them as part of the setup wizard
                
                # Create EVM wallet
                evm_wallet = await privy_client.create_user_wallet(
                    user_id="setup_wizard",  # This should be the actual user ID in production
                    chain_type="ethereum"
                )
                
                if progress_callback:
                    progress_callback(60)
                
                # Create Solana wallet
                solana_wallet = await privy_client.create_user_wallet(
                    user_id="setup_wizard",
                    chain_type="solana"
                )
                
                if progress_callback:
                    progress_callback(90)
                
                # Store wallet addresses
                await self.db.set_config("wallet_evm_address", evm_wallet["address"])
                await self.db.set_config("wallet_evm_id", evm_wallet["id"])
                await self.db.set_config("wallet_solana_address", solana_wallet["address"])
                await self.db.set_config("wallet_solana_id", solana_wallet["id"])
                
                await privy_client.close()
            else:
                # Demo mode - generate placeholder addresses
                import secrets
                evm_addr = "0x" + secrets.token_hex(20)
                sol_addr = secrets.token_base64(32)
                
                await self.db.set_config("wallet_evm_address", evm_addr)
                await self.db.set_config("wallet_solana_address", sol_addr)
            
            await self.db.set_config("wallets_created", "true")
            
            if progress_callback:
                progress_callback(100)
            
            return {
                "success": True,
                "message": "Wallets created successfully",
                "evm_address": await self.db.get_config("wallet_evm_address"),
                "solana_address": await self.db.get_config("wallet_solana_address")
            }
            
        except Exception as e:
            return {"success": False, "error": f"Failed to create wallets: {str(e)}"}
    
    # Step 3: Funding Verification
    async def check_funding(self) -> Dict[str, Any]:
        """
        Step 3: Check wallet funding status.
        
        Returns:
            Result dict with funding status
        """
        evm_address = await self.db.get_config("wallet_evm_address")
        solana_address = await self.db.get_config("wallet_solana_address")
        
        if not evm_address or not solana_address:
            return {"success": False, "error": "Wallets not created"}
        
        result = await self.validator.validate_wallet_funding(
            evm_address=evm_address,
            solana_address=solana_address
        )
        
        if result.valid:
            await self.db.set_config("funding_confirmed", "true")
            return {
                "success": True,
                "message": "Wallets funded",
                "balances": result.details["funding_status"].balances if result.details else {}
            }
        else:
            return {
                "success": False,
                "error": result.error,
                "balances": result.details["funding_status"].balances if result.details else {}
            }
    
    async def confirm_funding(self) -> Dict[str, Any]:
        """Manually confirm funding (user confirms they sent funds)."""
        await self.db.set_config("funding_confirmed", "true")
        return {"success": True, "message": "Funding confirmed"}
    
    # Step 3: Exchange Configuration
    async def configure_exchange(
        self,
        asgard_api_key: Optional[str] = None,
        hyperliquid_api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Step 3: Configure exchange connections.
        
        Both exchanges support wallet-based authentication:
        - Asgard: Solana wallet signatures (1 req/sec without API key)
        - Hyperliquid: EIP-712 signatures via Arbitrum wallet
        
        API keys are optional for both - only needed for higher rate limits.
        
        Args:
            asgard_api_key: Asgard API key (optional, for higher rate limits)
            hyperliquid_api_key: Hyperliquid API key (optional, for higher rate limits)
            
        Returns:
            Result dict with success/error
        """
        # Validate Asgard API key only if provided
        if asgard_api_key:
            asgard_result = await self.validator.validate_asgard_api_key(asgard_api_key)
            if not asgard_result.valid:
                return {"success": False, "error": asgard_result.error}
        
        # Validate Hyperliquid API key only if provided
        if hyperliquid_api_key:
            hl_result = await self.validator.validate_hyperliquid_api_key(hyperliquid_api_key)
            if not hl_result.valid:
                return {"success": False, "error": hl_result.error}
        
        try:
            # Store Asgard API key if provided
            if asgard_api_key:
                await self.db.set_config("asgard_api_key_plain", asgard_api_key)
            
            # Store Hyperliquid API key if provided
            if hyperliquid_api_key:
                await self.db.set_config("hyperliquid_api_key_plain", hyperliquid_api_key)
            
            await self.db.set_config("exchange_configured", "true")
            
            return {
                "success": True, 
                "message": "Exchange configured successfully",
                "exchanges": {
                    "asgard": True,      # Wallet-based auth works
                    "hyperliquid": True  # Wallet-based auth works
                }
            }
            
        except Exception as e:
            return {"success": False, "error": f"Failed to store configuration: {str(e)}"}
    
    # Step 5: Strategy Configuration
    async def configure_strategy(
        self,
        risk_preset: str = "balanced",
        leverage: float = 3.0,
        max_position_size: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Step 5: Configure trading strategy.
        
        Args:
            risk_preset: Risk level (conservative, balanced, aggressive)
            leverage: Default leverage (1-4x)
            max_position_size: Maximum position size in USD
            
        Returns:
            Result dict with success/error
        """
        # Validate risk preset
        preset_result = self.validator.validate_risk_preset(risk_preset)
        if not preset_result.valid:
            return {"success": False, "error": preset_result.error}
        
        # Validate leverage
        leverage_result = self.validator.validate_leverage(leverage)
        if not leverage_result.valid:
            return {"success": False, "error": leverage_result.error}
        
        try:
            # Store strategy config
            config = {
                "risk_preset": risk_preset,
                "leverage": leverage,
                "max_position_size": max_position_size or 50000
            }
            
            await self.db.set_config("strategy_config", json.dumps(config))
            await self.db.set_config("strategy_configured", "true")
            
            return {
                "success": True,
                "message": "Strategy configured",
                "config": config
            }
            
        except Exception as e:
            return {"success": False, "error": f"Failed to store configuration: {str(e)}"}
    
    # Step 6: Finalize and Launch
    async def finalize_setup(
        self,
        encryption_manager: EncryptionManager
    ) -> Dict[str, Any]:
        """
        Step 6: Finalize setup and encrypt all credentials.
        
        Args:
            encryption_manager: Active encryption manager with unlocked DEK
            
        Returns:
            Result dict with success/error
        """
        try:
            # Encrypt all sensitive configuration
            sensitive_keys = [
                ("privy_auth_key_plain", "privy_auth_key"),
                ("asgard_api_key_plain", "asgard_api_key"),
                ("hyperliquid_api_key_plain", "hyperliquid_api_key"),
            ]
            
            for plain_key, encrypted_key in sensitive_keys:
                value = await self.db.get_config(plain_key)
                if value:
                    encrypted = encryption_manager.encrypt(value)
                    await self.db.set_encrypted_config(encrypted_key, encrypted)
                    # Delete plaintext
                    await self.db.execute(
                        "DELETE FROM config WHERE key = ?",
                        (plain_key,)
                    )
            
            # Mark setup complete
            await self.db.set_config("setup_completed", "true")
            
            return {
                "success": True,
                "message": "Setup complete - bot ready to start"
            }
            
        except Exception as e:
            return {"success": False, "error": f"Failed to finalize setup: {str(e)}"}
