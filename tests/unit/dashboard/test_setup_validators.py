"""
Tests for dashboard setup validators.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from src.dashboard.setup.validators import (
    ValidationResult, FundingStatus, SetupValidator
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""
    
    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(valid=True)
        
        assert result.valid is True
        assert result.error is None
        assert result.details is None
    
    def test_invalid_result(self):
        """Test creating an invalid result with error."""
        result = ValidationResult(valid=False, error="Something went wrong")
        
        assert result.valid is False
        assert result.error == "Something went wrong"
    
    def test_result_with_details(self):
        """Test creating a result with details."""
        details = {"key": "value"}
        result = ValidationResult(valid=True, details=details)
        
        assert result.details == details


class TestFundingStatus:
    """Tests for FundingStatus dataclass."""
    
    def test_funding_status_creation(self):
        """Test creating a funding status."""
        balances = {
            "evm_usdc": Decimal("500"),
            "solana_sol": Decimal("1.5"),
            "solana_usdc": Decimal("200")
        }
        
        status = FundingStatus(
            evm_funded=True,
            solana_sol_funded=True,
            solana_usdc_funded=True,
            balances=balances
        )
        
        assert status.evm_funded is True
        assert status.solana_sol_funded is True
        assert status.solana_usdc_funded is True
        assert status.balances == balances


class TestSetupValidatorInitialization:
    """Tests for SetupValidator initialization."""
    
    def test_init_with_defaults(self):
        """Test initialization with default clients."""
        validator = SetupValidator()
        
        assert validator.privy is None
        assert validator.solana is None
        assert validator.arbitrum is None
        assert validator.asgard is None
    
    def test_init_with_clients(self):
        """Test initialization with custom clients."""
        mock_privy = MagicMock()
        mock_solana = MagicMock()
        mock_arbitrum = MagicMock()
        mock_asgard = MagicMock()
        
        validator = SetupValidator(
            privy_client=mock_privy,
            solana_client=mock_solana,
            arbitrum_client=mock_arbitrum,
            asgard_client=mock_asgard
        )
        
        assert validator.privy is mock_privy
        assert validator.solana is mock_solana
        assert validator.arbitrum is mock_arbitrum
        assert validator.asgard is mock_asgard


class TestValidatePassword:
    """Tests for validate_password method."""
    
    @pytest.mark.asyncio
    async def test_password_too_short(self):
        """Test password that's too short."""
        validator = SetupValidator()
        result = await validator.validate_password("short")
        
        assert result.valid is False
        assert "at least 16 characters" in result.error
    
    @pytest.mark.asyncio
    async def test_password_missing_uppercase(self):
        """Test password without uppercase."""
        validator = SetupValidator()
        result = await validator.validate_password("lowercase1234567!")
        
        assert result.valid is False
        assert "uppercase letter" in result.error
    
    @pytest.mark.asyncio
    async def test_password_missing_lowercase(self):
        """Test password without lowercase."""
        validator = SetupValidator()
        result = await validator.validate_password("UPPERCASE1234567!")
        
        assert result.valid is False
        assert "lowercase letter" in result.error
    
    @pytest.mark.asyncio
    async def test_password_missing_digit(self):
        """Test password without digit."""
        validator = SetupValidator()
        result = await validator.validate_password("NoDigitsHere!!!!!")
        
        assert result.valid is False
        assert "digit" in result.error
    
    @pytest.mark.asyncio
    async def test_password_missing_special(self):
        """Test password without special character."""
        validator = SetupValidator()
        result = await validator.validate_password("NoSpecial1234567")
        
        assert result.valid is False
        assert "special character" in result.error
    
    @pytest.mark.asyncio
    async def test_password_multiple_missing(self):
        """Test password missing multiple requirements."""
        validator = SetupValidator()
        result = await validator.validate_password("a" * 20)  # Only lowercase
        
        assert result.valid is False
        assert "uppercase letter" in result.error
        assert "digit" in result.error
        assert "special character" in result.error
    
    @pytest.mark.asyncio
    async def test_valid_password(self):
        """Test a valid password."""
        validator = SetupValidator()
        result = await validator.validate_password("ValidP@ssw0rd123!")
        
        assert result.valid is True
        assert result.error is None


class TestValidatePrivyCredentials:
    """Tests for validate_privy_credentials method."""
    
    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test with missing credentials."""
        validator = SetupValidator()
        result = await validator.validate_privy_credentials("", "")
        
        assert result.valid is False
        assert "required" in result.error
    
    @pytest.mark.asyncio
    async def test_invalid_app_id_format(self):
        """Test with invalid app ID format."""
        validator = SetupValidator()
        result = await validator.validate_privy_credentials("app@id!", "secret")
        
        assert result.valid is False
        assert "Invalid App ID" in result.error
    
    @pytest.mark.asyncio
    async def test_valid_format_no_client(self):
        """Test valid format without client (just validates format)."""
        validator = SetupValidator()
        result = await validator.validate_privy_credentials("app_id_123", "secret")
        
        assert result.valid is True
    
    @pytest.mark.asyncio
    async def test_with_client_success(self):
        """Test with client that succeeds."""
        mock_privy = AsyncMock()
        mock_privy.health_check = AsyncMock()
        
        validator = SetupValidator(privy_client=mock_privy)
        result = await validator.validate_privy_credentials("app_id", "secret")
        
        assert result.valid is True
        mock_privy.health_check.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_with_client_failure(self):
        """Test with client that fails."""
        mock_privy = AsyncMock()
        mock_privy.health_check = AsyncMock(side_effect=Exception("Connection failed"))
        
        validator = SetupValidator(privy_client=mock_privy)
        result = await validator.validate_privy_credentials("app_id", "secret")
        
        assert result.valid is False
        assert "Failed to connect" in result.error


class TestValidateWalletFunding:
    """Tests for validate_wallet_funding method."""
    
    @pytest.mark.asyncio
    async def test_no_clients_returns_empty_balances(self):
        """Test without clients returns empty balances and fails validation."""
        validator = SetupValidator()
        result = await validator.validate_wallet_funding("0x1234", "sol567")
        
        # Returns False because balances are all 0 (insufficient)
        assert result.valid is False
        assert "Insufficient funding" in result.error
    
    @pytest.mark.asyncio
    async def test_evm_funded(self):
        """Test with funded EVM wallet but missing Solana still fails."""
        mock_arbitrum = AsyncMock()
        mock_arbitrum.get_usdc_balance = AsyncMock(return_value=Decimal("500"))
        
        validator = SetupValidator(arbitrum_client=mock_arbitrum)
        result = await validator.validate_wallet_funding("0x1234", None)
        
        # EVM is funded but Solana is missing, so overall fails
        assert result.valid is False
        assert result.details["funding_status"].evm_funded is True
    
    @pytest.mark.asyncio
    async def test_evm_not_funded(self):
        """Test with unfunded EVM wallet."""
        mock_arbitrum = AsyncMock()
        mock_arbitrum.get_usdc_balance = AsyncMock(return_value=Decimal("10"))
        
        validator = SetupValidator(arbitrum_client=mock_arbitrum)
        result = await validator.validate_wallet_funding("0x1234", None)
        
        assert result.valid is False
        assert result.details["funding_status"].evm_funded is False
    
    @pytest.mark.asyncio
    async def test_solana_funded(self):
        """Test with funded Solana wallet but missing EVM still fails."""
        mock_solana = AsyncMock()
        mock_solana.get_sol_balance = AsyncMock(return_value=Decimal("1.5"))
        mock_solana.get_usdc_balance = AsyncMock(return_value=Decimal("200"))
        
        validator = SetupValidator(solana_client=mock_solana)
        result = await validator.validate_wallet_funding(None, "sol567")
        
        # Solana is funded but EVM is missing, so overall fails
        assert result.valid is False
        assert result.details["funding_status"].solana_sol_funded is True
        assert result.details["funding_status"].solana_usdc_funded is True
    
    @pytest.mark.asyncio
    async def test_solana_not_funded(self):
        """Test with unfunded Solana wallet."""
        mock_solana = AsyncMock()
        mock_solana.get_sol_balance = AsyncMock(return_value=Decimal("0.01"))
        mock_solana.get_usdc_balance = AsyncMock(return_value=Decimal("10"))
        
        validator = SetupValidator(solana_client=mock_solana)
        result = await validator.validate_wallet_funding(None, "sol567")
        
        assert result.valid is False
        assert result.details["funding_status"].solana_sol_funded is False
        assert result.details["funding_status"].solana_usdc_funded is False
    
    @pytest.mark.asyncio
    async def test_arbitrum_error(self):
        """Test Arbitrum balance check error."""
        mock_arbitrum = AsyncMock()
        mock_arbitrum.get_usdc_balance = AsyncMock(side_effect=Exception("RPC error"))
        
        validator = SetupValidator(arbitrum_client=mock_arbitrum)
        result = await validator.validate_wallet_funding("0x1234", None)
        
        assert result.valid is False
        assert "Failed to check EVM balance" in result.error
    
    @pytest.mark.asyncio
    async def test_solana_error(self):
        """Test Solana balance check error."""
        mock_solana = AsyncMock()
        mock_solana.get_sol_balance = AsyncMock(side_effect=Exception("RPC error"))
        
        validator = SetupValidator(solana_client=mock_solana)
        result = await validator.validate_wallet_funding(None, "sol567")
        
        assert result.valid is False
        assert "Failed to check Solana balance" in result.error
    
    @pytest.mark.asyncio
    async def test_partial_funding_message(self):
        """Test error message with partial funding."""
        mock_arbitrum = AsyncMock()
        mock_arbitrum.get_usdc_balance = AsyncMock(return_value=Decimal("50"))
        
        mock_solana = AsyncMock()
        mock_solana.get_sol_balance = AsyncMock(return_value=Decimal("0.05"))
        mock_solana.get_usdc_balance = AsyncMock(return_value=Decimal("50"))
        
        validator = SetupValidator(
            arbitrum_client=mock_arbitrum,
            solana_client=mock_solana
        )
        result = await validator.validate_wallet_funding("0x1234", "sol567")
        
        assert result.valid is False
        assert "EVM" in result.error
        assert "Solana SOL" in result.error


class TestValidateAsgardApiKey:
    """Tests for validate_asgard_api_key method."""
    
    @pytest.mark.asyncio
    async def test_missing_key(self):
        """Test with missing API key."""
        validator = SetupValidator()
        result = await validator.validate_asgard_api_key("")
        
        assert result.valid is False
        assert "required" in result.error
    
    @pytest.mark.asyncio
    async def test_short_key(self):
        """Test with too short API key."""
        validator = SetupValidator()
        result = await validator.validate_asgard_api_key("short")
        
        assert result.valid is False
        assert "too short" in result.error
    
    @pytest.mark.asyncio
    async def test_valid_format_no_client(self):
        """Test valid format without client."""
        validator = SetupValidator()
        result = await validator.validate_asgard_api_key("a" * 32)
        
        assert result.valid is True
    
    @pytest.mark.asyncio
    async def test_with_client_success(self):
        """Test with client that succeeds."""
        mock_asgard = AsyncMock()
        mock_asgard.health_check = AsyncMock()
        
        validator = SetupValidator(asgard_client=mock_asgard)
        result = await validator.validate_asgard_api_key("valid_key_" * 4)
        
        assert result.valid is True
        mock_asgard.health_check.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_with_client_failure(self):
        """Test with client that fails."""
        mock_asgard = AsyncMock()
        mock_asgard.health_check = AsyncMock(side_effect=Exception("API error"))
        
        validator = SetupValidator(asgard_client=mock_asgard)
        result = await validator.validate_asgard_api_key("valid_key_" * 4)
        
        assert result.valid is False
        assert "Failed to connect" in result.error


class TestValidateHyperliquidApiKey:
    """Tests for validate_hyperliquid_api_key method."""
    
    @pytest.mark.asyncio
    async def test_no_client(self):
        """Test without client (accepts any key)."""
        validator = SetupValidator()
        result = await validator.validate_hyperliquid_api_key("any_key")
        
        assert result.valid is True
    
    @pytest.mark.asyncio
    async def test_with_client_success(self):
        """Test with client that succeeds."""
        mock_hl = AsyncMock()
        mock_hl.info = AsyncMock(return_value={"type": "meta"})
        
        validator = SetupValidator()
        validator.hyperliquid = mock_hl
        result = await validator.validate_hyperliquid_api_key("valid_key")
        
        assert result.valid is True
        mock_hl.info.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_with_client_failure(self):
        """Test with client that fails."""
        mock_hl = AsyncMock()
        mock_hl.info = AsyncMock(side_effect=Exception("API error"))
        
        validator = SetupValidator()
        validator.hyperliquid = mock_hl
        result = await validator.validate_hyperliquid_api_key("valid_key")
        
        assert result.valid is False
        assert "Failed to connect" in result.error


class TestValidateExchangeConfig:
    """Tests for validate_exchange_config method."""
    
    @pytest.mark.asyncio
    async def test_valid_asgard_only(self):
        """Test with valid Asgard config only."""
        validator = SetupValidator()
        
        with patch.object(validator, 'validate_asgard_api_key', 
                         AsyncMock(return_value=ValidationResult(valid=True))):
            result = await validator.validate_exchange_config("asgard_key")
            
            assert result.valid is True
    
    @pytest.mark.asyncio
    async def test_invalid_asgard(self):
        """Test with invalid Asgard config."""
        validator = SetupValidator()
        
        with patch.object(validator, 'validate_asgard_api_key', 
                         AsyncMock(return_value=ValidationResult(valid=False, error="Bad key"))):
            result = await validator.validate_exchange_config("bad_key")
            
            assert result.valid is False
            assert result.error == "Bad key"
    
    @pytest.mark.asyncio
    async def test_valid_both_exchanges(self):
        """Test with valid configs for both exchanges."""
        validator = SetupValidator()
        
        with patch.object(validator, 'validate_asgard_api_key', 
                         AsyncMock(return_value=ValidationResult(valid=True))):
            with patch.object(validator, 'validate_hyperliquid_api_key',
                            AsyncMock(return_value=ValidationResult(valid=True))):
                result = await validator.validate_exchange_config("asgard_key", "hl_key")
                
                assert result.valid is True
    
    @pytest.mark.asyncio
    async def test_invalid_hyperliquid(self):
        """Test with invalid Hyperliquid config."""
        validator = SetupValidator()
        
        with patch.object(validator, 'validate_asgard_api_key', 
                         AsyncMock(return_value=ValidationResult(valid=True))):
            with patch.object(validator, 'validate_hyperliquid_api_key',
                            AsyncMock(return_value=ValidationResult(valid=False, error="HL error"))):
                result = await validator.validate_exchange_config("asgard_key", "bad_hl_key")
                
                assert result.valid is False
                assert result.error == "HL error"


class TestValidateLeverage:
    """Tests for validate_leverage method."""
    
    def test_leverage_too_low(self):
        """Test leverage below 1x."""
        validator = SetupValidator()
        result = validator.validate_leverage(0.5)
        
        assert result.valid is False
        assert "at least 1x" in result.error
    
    def test_leverage_too_high(self):
        """Test leverage above 4x."""
        validator = SetupValidator()
        result = validator.validate_leverage(5.0)
        
        assert result.valid is False
        assert "Maximum leverage is 4x" in result.error
    
    def test_valid_leverage(self):
        """Test valid leverage values."""
        validator = SetupValidator()
        
        result = validator.validate_leverage(1.0)
        assert result.valid is True
        
        result = validator.validate_leverage(2.5)
        assert result.valid is True
        
        result = validator.validate_leverage(4.0)
        assert result.valid is True


class TestValidateRiskPreset:
    """Tests for validate_risk_preset method."""
    
    def test_valid_presets(self):
        """Test valid risk presets."""
        validator = SetupValidator()
        
        valid_presets = ["conservative", "balanced", "aggressive"]
        for preset in valid_presets:
            result = validator.validate_risk_preset(preset)
            assert result.valid is True, f"{preset} should be valid"
    
    def test_invalid_preset(self):
        """Test invalid risk preset."""
        validator = SetupValidator()
        result = validator.validate_risk_preset("invalid_preset")
        
        assert result.valid is False
        assert "Invalid preset" in result.error
        assert "conservative" in result.error
        assert "balanced" in result.error
        assert "aggressive" in result.error
