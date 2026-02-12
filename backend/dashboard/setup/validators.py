"""
Validation functions for setup wizard steps.
"""

import re
from decimal import Decimal
from typing import Optional, Dict, Any
from dataclasses import dataclass

import aiohttp


@dataclass
class ValidationResult:
    """Result of validation."""
    valid: bool
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class FundingStatus:
    """Wallet funding status."""
    evm_funded: bool
    solana_sol_funded: bool
    solana_usdc_funded: bool
    balances: Dict[str, Decimal]


class SetupValidator:
    """Validates configuration at each wizard step."""
    
    # Minimum funding requirements
    MIN_EVM_USDC = Decimal("100")
    MIN_SOLANA_SOL = Decimal("0.1")
    MIN_SOLANA_USDC = Decimal("100")
    
    def __init__(
        self,
        privy_client=None,
        solana_client=None,
        arbitrum_client=None,
        asgard_client=None
    ):
        self.privy = privy_client
        self.solana = solana_client
        self.arbitrum = arbitrum_client
        self.asgard = asgard_client
    
    async def validate_password(self, password: str) -> ValidationResult:
        """
        Validate password meets requirements.
        
        Requirements:
        - Minimum 16 characters
        - Contains uppercase, lowercase, number, special char
        """
        if len(password) < 16:
            return ValidationResult(
                valid=False,
                error="Password must be at least 16 characters"
            )
        
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
        
        if not all([has_upper, has_lower, has_digit, has_special]):
            missing = []
            if not has_upper:
                missing.append("uppercase letter")
            if not has_lower:
                missing.append("lowercase letter")
            if not has_digit:
                missing.append("digit")
            if not has_special:
                missing.append("special character")
            
            return ValidationResult(
                valid=False,
                error=f"Password must contain: {', '.join(missing)}"
            )
        
        return ValidationResult(valid=True)
    
    async def validate_privy_credentials(
        self,
        app_id: str,
        app_secret: str
    ) -> ValidationResult:
        """
        Test Privy API connectivity using the official SDK.
        
        Args:
            app_id: Privy app ID
            app_secret: Privy app secret
            
        Returns:
            ValidationResult with success/error
        """
        if not app_id or not app_secret:
            return ValidationResult(
                valid=False,
                error="App ID and App Secret are required"
            )
        
        # Basic format validation
        if not re.match(r'^[a-zA-Z0-9_-]+$', app_id):
            return ValidationResult(
                valid=False,
                error="Invalid App ID format"
            )
        
        # Test API connection using the SDK
        try:
            from backend.dashboard.privy_client import PrivyClient
            client = PrivyClient(app_id=app_id, app_secret=app_secret)
            # Try to list users (with limit 1) to verify credentials
            await client.list_users(limit=1)
            await client.close()
            return ValidationResult(
                valid=True,
                details={"message": "Successfully connected to Privy API"}
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                error=f"Failed to connect to Privy API: {str(e)}"
            )
    
    async def validate_wallet_funding(
        self,
        evm_address: Optional[str] = None,
        solana_address: Optional[str] = None
    ) -> ValidationResult:
        """
        Check wallet balances across chains.
        
        Args:
            evm_address: EVM wallet address
            solana_address: Solana wallet address
            
        Returns:
            ValidationResult with FundingStatus in details
        """
        balances = {
            "evm_usdc": Decimal("0"),
            "solana_sol": Decimal("0"),
            "solana_usdc": Decimal("0")
        }
        
        # Check EVM balance if client available
        if evm_address and self.arbitrum:
            try:
                balances["evm_usdc"] = await self.arbitrum.get_usdc_balance(evm_address)
            except Exception as e:
                return ValidationResult(
                    valid=False,
                    error=f"Failed to check EVM balance: {str(e)}"
                )
        
        # Check Solana balances if client available
        if solana_address and self.solana:
            try:
                balances["solana_sol"] = await self.solana.get_sol_balance(solana_address)
                balances["solana_usdc"] = await self.solana.get_usdc_balance(solana_address)
            except Exception as e:
                return ValidationResult(
                    valid=False,
                    error=f"Failed to check Solana balance: {str(e)}"
                )
        
        # Determine funding status
        funding_status = FundingStatus(
            evm_funded=balances["evm_usdc"] >= self.MIN_EVM_USDC,
            solana_sol_funded=balances["solana_sol"] >= self.MIN_SOLANA_SOL,
            solana_usdc_funded=balances["solana_usdc"] >= self.MIN_SOLANA_USDC,
            balances=balances
        )
        
        # All must be funded
        all_funded = all([
            funding_status.evm_funded,
            funding_status.solana_sol_funded,
            funding_status.solana_usdc_funded
        ])
        
        if not all_funded:
            missing = []
            if not funding_status.evm_funded:
                missing.append(
                    f"EVM: {balances['evm_usdc']} USDC (need {self.MIN_EVM_USDC})"
                )
            if not funding_status.solana_sol_funded:
                missing.append(
                    f"Solana SOL: {balances['solana_sol']} (need {self.MIN_SOLANA_SOL})"
                )
            if not funding_status.solana_usdc_funded:
                missing.append(
                    f"Solana USDC: {balances['solana_usdc']} (need {self.MIN_SOLANA_USDC})"
                )
            
            return ValidationResult(
                valid=False,
                error=f"Insufficient funding: {'; '.join(missing)}",
                details={"funding_status": funding_status}
            )
        
        return ValidationResult(
            valid=True,
            details={"funding_status": funding_status}
        )
    
    async def validate_asgard_api_key(self, api_key: str) -> ValidationResult:
        """
        Test Asgard API key.
        
        Args:
            api_key: Asgard API key
            
        Returns:
            ValidationResult with success/error
        """
        if not api_key:
            return ValidationResult(
                valid=False,
                error="Asgard API key is required"
            )
        
        # Test connection if client available
        if self.asgard:
            try:
                await self.asgard.health_check(api_key)
                return ValidationResult(valid=True)
            except Exception as e:
                return ValidationResult(
                    valid=False,
                    error=f"Failed to connect to Asgard API: {str(e)}"
                )
        
        # No client, just validate format (should be base58-like)
        if len(api_key) < 20:
            return ValidationResult(
                valid=False,
                error="Asgard API key appears invalid (too short)"
            )
        
        return ValidationResult(valid=True)
    
    async def validate_hyperliquid_api_key(self, api_key: str) -> ValidationResult:
        """
        Test Hyperliquid API connection.
        
        Note: Hyperliquid uses wallet-based authentication (EIP-712 signatures),
        but we accept an API key for SDK initialization or rate limit purposes.
        
        Args:
            api_key: Hyperliquid API key (optional for some operations)
            
        Returns:
            ValidationResult with success/error
        """
        # Test connection if client available
        if hasattr(self, 'hyperliquid') and self.hyperliquid:
            try:
                # Test with a simple info request
                await self.hyperliquid.info({"type": "meta"})
                return ValidationResult(valid=True)
            except Exception as e:
                return ValidationResult(
                    valid=False,
                    error=f"Failed to connect to Hyperliquid API: {str(e)}"
                )
        
        # If no client but key provided, accept it (will be validated at runtime)
        return ValidationResult(valid=True)
    
    async def validate_exchange_config(
        self,
        asgard_api_key: str,
        hyperliquid_api_key: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate both exchange configurations.
        
        Args:
            asgard_api_key: Asgard API key
            hyperliquid_api_key: Hyperliquid API key (optional)
            
        Returns:
            ValidationResult with combined status
        """
        # Validate Asgard (required)
        asgard_result = await self.validate_asgard_api_key(asgard_api_key)
        if not asgard_result.valid:
            return asgard_result
        
        # Validate Hyperliquid (optional but recommended)
        if hyperliquid_api_key:
            hl_result = await self.validate_hyperliquid_api_key(hyperliquid_api_key)
            if not hl_result.valid:
                return hl_result
        
        return ValidationResult(valid=True)
    
    def validate_leverage(self, leverage: float) -> ValidationResult:
        """
        Validate leverage setting.
        
        Args:
            leverage: Leverage value (e.g., 3.0 for 3x)
            
        Returns:
            ValidationResult
        """
        if leverage < 1:
            return ValidationResult(
                valid=False,
                error="Leverage must be at least 1x"
            )
        
        if leverage > 4:
            return ValidationResult(
                valid=False,
                error="Maximum leverage is 4x"
            )
        
        return ValidationResult(valid=True)
    
    def validate_risk_preset(self, preset: str) -> ValidationResult:
        """
        Validate risk preset selection.
        
        Args:
            preset: Risk preset name
            
        Returns:
            ValidationResult
        """
        valid_presets = ["conservative", "balanced", "aggressive"]
        
        if preset not in valid_presets:
            return ValidationResult(
                valid=False,
                error=f"Invalid preset. Choose from: {', '.join(valid_presets)}"
            )
        
        return ValidationResult(valid=True)
