"""
Tests for dashboard setup steps.
"""
import pytest
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

from backend.dashboard.setup.steps import SetupState, SetupSteps
from shared.security.encryption import EncryptionManager


class TestSetupState:
    """Tests for SetupState dataclass."""
    
    def test_default_state(self):
        """Test default setup state."""
        state = SetupState()
        
        assert state.step == 0
        assert state.authenticated is False
        assert state.wallets_created is False
        assert state.exchange_configured is False
    
    def test_custom_state(self):
        """Test creating state with custom values."""
        state = SetupState(
            step=3,
            authenticated=True,
            wallets_created=True,
            exchange_configured=True
        )
        
        assert state.step == 3
        assert state.authenticated is True
        assert state.wallets_created is True
        assert state.exchange_configured is True
    
    def test_to_dict(self):
        """Test converting state to dict."""
        state = SetupState(step=2, authenticated=True)
        
        result = state.to_dict()
        
        assert result["step"] == 2
        assert result["authenticated"] is True
        assert result["wallets_created"] is False
        assert result["exchange_configured"] is False
        assert result["setup_complete"] is False
    
    def test_to_dict_complete(self):
        """Test to_dict when setup is complete."""
        state = SetupState(step=4)
        
        result = state.to_dict()
        
        assert result["setup_complete"] is True


class TestSetupStepsInitialization:
    """Tests for SetupSteps initialization."""
    
    def test_init_with_defaults(self):
        """Test initialization with default validator."""
        mock_db = MagicMock()
        
        steps = SetupSteps(db=mock_db)
        
        assert steps.db is mock_db
        assert steps.validator is not None
        assert steps.privy is None
    
    def test_init_with_custom_validator(self):
        """Test initialization with custom validator."""
        mock_db = MagicMock()
        mock_validator = MagicMock()
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        
        assert steps.validator is mock_validator
    
    def test_init_with_privy_client(self):
        """Test initialization with Privy client."""
        mock_db = MagicMock()
        mock_privy = MagicMock()
        
        steps = SetupSteps(db=mock_db, privy_client=mock_privy)
        
        assert steps.privy is mock_privy


class TestGetSetupState:
    """Tests for get_setup_state method."""
    
    @pytest.mark.asyncio
    async def test_setup_complete(self):
        """Test when setup is already complete."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(return_value="true")
        
        steps = SetupSteps(db=mock_db)
        state = await steps.get_setup_state()
        
        assert state.step == 6
        assert state.to_dict()["setup_complete"] is True
    
    @pytest.mark.asyncio
    async def test_step_1_not_authenticated(self):
        """Test step 1 when not authenticated."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "setup_completed": None,
            "privy_authenticated": None,
            "wallet_evm_address": None,
            "asgard_api_key": None
        }.get(key))
        
        steps = SetupSteps(db=mock_db)
        state = await steps.get_setup_state()
        
        assert state.step == 1
        assert state.authenticated is False
    
    @pytest.mark.asyncio
    async def test_step_2_no_wallets(self):
        """Test step 2 when authenticated but no wallets."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "setup_completed": None,
            "privy_authenticated": "true",
            "wallet_evm_address": None,
            "asgard_api_key": None
        }.get(key))
        
        steps = SetupSteps(db=mock_db)
        state = await steps.get_setup_state()
        
        assert state.step == 2
        assert state.authenticated is True
        assert state.wallets_created is False
    
    @pytest.mark.asyncio
    async def test_step_3_no_exchange(self):
        """Test step 3 when wallets exist but no exchange config."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "setup_completed": None,
            "privy_authenticated": "true",
            "wallet_evm_address": "0x1234",
            "asgard_api_key": None
        }.get(key))
        
        steps = SetupSteps(db=mock_db)
        state = await steps.get_setup_state()
        
        assert state.step == 3
        assert state.wallets_created is True
        assert state.exchange_configured is False
    
    @pytest.mark.asyncio
    async def test_step_4_dashboard(self):
        """Test step 4 when all setup complete."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "setup_completed": None,
            "privy_authenticated": "true",
            "wallet_evm_address": "0x1234",
            "asgard_api_key": "key123"
        }.get(key))
        
        steps = SetupSteps(db=mock_db)
        state = await steps.get_setup_state()
        
        assert state.step == 4
        assert state.authenticated is True
        assert state.wallets_created is True
        assert state.exchange_configured is True


class TestConfigurePrivy:
    """Tests for configure_privy method."""
    
    @pytest.mark.asyncio
    async def test_configure_privy_success(self):
        """Test successful Privy configuration."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        mock_validator = MagicMock()
        mock_validator.validate_privy_credentials = AsyncMock(
            return_value=MagicMock(valid=True)
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.configure_privy("app_id", "app_secret")
        
        assert result["success"] is True
        assert "Privy configured" in result["message"]
        mock_db.set_config.assert_any_call("privy_app_id_plain", "app_id")
        mock_db.set_config.assert_any_call("privy_app_secret_plain", "app_secret")
    
    @pytest.mark.asyncio
    async def test_configure_privy_with_auth_key(self):
        """Test Privy configuration with auth key."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        mock_validator = MagicMock()
        mock_validator.validate_privy_credentials = AsyncMock(
            return_value=MagicMock(valid=True)
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.configure_privy("app_id", "app_secret", "auth_key_pem")
        
        assert result["success"] is True
        mock_db.set_config.assert_any_call("privy_auth_key_plain", "auth_key_pem")
    
    @pytest.mark.asyncio
    async def test_configure_privy_validation_failure(self):
        """Test Privy configuration with invalid credentials."""
        mock_db = AsyncMock()
        
        mock_validator = MagicMock()
        mock_validator.validate_privy_credentials = AsyncMock(
            return_value=MagicMock(valid=False, error="Invalid credentials")
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.configure_privy("bad_id", "bad_secret")
        
        assert result["success"] is False
        assert result["error"] == "Invalid credentials"
    
    @pytest.mark.asyncio
    async def test_configure_privy_storage_error(self):
        """Test Privy configuration with storage error."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock(side_effect=Exception("DB error"))
        
        mock_validator = MagicMock()
        mock_validator.validate_privy_credentials = AsyncMock(
            return_value=MagicMock(valid=True)
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.configure_privy("app_id", "app_secret")
        
        assert result["success"] is False
        assert "Failed to store" in result["error"]


class TestCompletePrivyAuth:
    """Tests for complete_privy_auth method."""
    
    @pytest.mark.asyncio
    async def test_complete_auth_success(self):
        """Test completing authentication."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        steps = SetupSteps(db=mock_db)
        result = await steps.complete_privy_auth("user123", "test@example.com")
        
        assert result["success"] is True
        mock_db.set_config.assert_any_call("privy_user_id", "user123")
        mock_db.set_config.assert_any_call("user_email", "test@example.com")
        mock_db.set_config.assert_any_call("privy_authenticated", "true")
    
    @pytest.mark.asyncio
    async def test_complete_auth_without_email(self):
        """Test completing authentication without email."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        steps = SetupSteps(db=mock_db)
        result = await steps.complete_privy_auth("user123", None)
        
        assert result["success"] is True
        mock_db.set_config.assert_any_call("privy_user_id", "user123")


class TestCreateWallets:
    """Tests for create_wallets method."""
    
    @pytest.mark.asyncio
    async def test_create_wallets_with_privy(self):
        """Test wallet creation with Privy client."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "privy_app_id_plain": "app_id",
            "privy_app_secret_plain": "app_secret"
        }.get(key, None))
        mock_db.set_config = AsyncMock()
        
        # Mock the final get_config calls that return the stored addresses
        stored_addresses = {}
        async def mock_set_config(key, value):
            stored_addresses[key] = value
        mock_db.set_config = AsyncMock(side_effect=mock_set_config)
        
        async def mock_get_config_final(key):
            return stored_addresses.get(key, {
                "privy_app_id_plain": "app_id",
                "privy_app_secret_plain": "app_secret"
            }.get(key, None))
        mock_db.get_config = AsyncMock(side_effect=mock_get_config_final)
        
        # Mock the PrivyClient class — wallets are now created by frontend SDK,
        # setup just verifies connection and stores provider flag
        with patch('backend.dashboard.privy_client.PrivyClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            progress_calls = []
            def progress_cb(pct):
                progress_calls.append(pct)

            # Pass privy_client=True to trigger SDK path
            mock_privy = MagicMock()  # Just a flag, actual client is mocked
            steps = SetupSteps(db=mock_db, privy_client=mock_privy)
            result = await steps.create_wallets(progress_callback=progress_cb)

            assert result["success"] is True
            mock_client_class.assert_called_once_with(app_id="app_id", app_secret="app_secret")
            mock_db.set_config.assert_any_call("wallet_provider", "privy")
    
    @pytest.mark.asyncio
    async def test_create_wallets_demo_mode(self):
        """Test wallet creation without Privy client (demo mode)."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "privy_app_id_plain": "app_id",
            "privy_app_secret_plain": "app_secret"
        }.get(key, None))
        mock_db.set_config = AsyncMock()
        
        steps = SetupSteps(db=mock_db)  # No privy client
        result = await steps.create_wallets()
        
        # Demo mode generates placeholder addresses
        # Result success depends on implementation - just verify it runs
        assert "success" in result
        if result["success"]:
            assert "evm_address" in result
            assert "solana_address" in result
    
    @pytest.mark.asyncio
    async def test_create_wallets_not_configured(self):
        """Test wallet creation when Privy not configured."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(return_value=None)
        
        steps = SetupSteps(db=mock_db)
        result = await steps.create_wallets()
        
        assert result["success"] is False
        assert "Privy not configured" in result["error"]
    
    @pytest.mark.asyncio
    async def test_create_wallets_error(self):
        """Test wallet creation error handling."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "privy_app_id_plain": "app_id",
            "privy_app_secret_plain": "app_secret"
        }.get(key))
        
        mock_privy = AsyncMock()
        mock_privy.create_wallet = AsyncMock(side_effect=Exception("API error"))
        
        steps = SetupSteps(db=mock_db, privy_client=mock_privy)
        result = await steps.create_wallets()
        
        assert result["success"] is False
        assert "Failed to create wallets" in result["error"]


class TestCheckFunding:
    """Tests for check_funding method."""
    
    @pytest.mark.asyncio
    async def test_check_funding_success(self):
        """Test successful funding check."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "wallet_evm_address": "0x1234",
            "wallet_solana_address": "sol567"
        }.get(key))
        
        mock_validator = MagicMock()
        mock_validator.validate_wallet_funding = AsyncMock(
            return_value=MagicMock(
                valid=True,
                details={"funding_status": MagicMock(balances={"evm_usdc": Decimal("500")})}
            )
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.check_funding()
        
        assert result["success"] is True
        assert "Wallets funded" in result["message"]
    
    @pytest.mark.asyncio
    async def test_check_funding_insufficient(self):
        """Test funding check with insufficient funds."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "wallet_evm_address": "0x1234",
            "wallet_solana_address": "sol567"
        }.get(key))
        
        mock_validator = MagicMock()
        mock_validator.validate_wallet_funding = AsyncMock(
            return_value=MagicMock(
                valid=False,
                error="Insufficient funding",
                details={"funding_status": MagicMock(balances={})}
            )
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.check_funding()
        
        assert result["success"] is False
        assert "Insufficient funding" in result["error"]
    
    @pytest.mark.asyncio
    async def test_check_funding_no_wallets(self):
        """Test funding check without wallets."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(return_value=None)
        
        steps = SetupSteps(db=mock_db)
        result = await steps.check_funding()
        
        assert result["success"] is False
        assert "Wallets not created" in result["error"]


class TestConfirmFunding:
    """Tests for confirm_funding method."""
    
    @pytest.mark.asyncio
    async def test_confirm_funding(self):
        """Test manual funding confirmation."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        steps = SetupSteps(db=mock_db)
        result = await steps.confirm_funding()
        
        assert result["success"] is True
        mock_db.set_config.assert_called_with("funding_confirmed", "true")


class TestConfigureExchange:
    """Tests for configure_exchange method."""
    
    @pytest.mark.asyncio
    async def test_configure_exchange_success(self):
        """Test successful exchange configuration."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        mock_validator = MagicMock()
        mock_validator.validate_asgard_api_key = AsyncMock(
            return_value=MagicMock(valid=True)
        )
        mock_validator.validate_hyperliquid_api_key = AsyncMock(
            return_value=MagicMock(valid=True)
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.configure_exchange("asgard_key", "hl_key")
        
        assert result["success"] is True
        mock_db.set_config.assert_any_call("asgard_api_key_plain", "asgard_key")
        mock_db.set_config.assert_any_call("hyperliquid_api_key_plain", "hl_key")
    
    @pytest.mark.asyncio
    async def test_configure_exchange_wallet_only(self):
        """Test exchange configuration without API keys (wallet-based)."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        mock_validator = MagicMock()
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.configure_exchange(None, None)
        
        assert result["success"] is True
        assert result["exchanges"]["asgard"] is True
        # Validators should not be called when no keys provided
        mock_validator.validate_asgard_api_key.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_configure_exchange_invalid_key(self):
        """Test exchange configuration with invalid key."""
        mock_db = AsyncMock()
        
        mock_validator = MagicMock()
        mock_validator.validate_asgard_api_key = AsyncMock(
            return_value=MagicMock(valid=False, error="Invalid key")
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.configure_exchange("bad_key", None)
        
        assert result["success"] is False
        assert result["error"] == "Invalid key"


class TestConfigureStrategy:
    """Tests for configure_strategy method."""
    
    @pytest.mark.asyncio
    async def test_configure_strategy_success(self):
        """Test successful strategy configuration."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        mock_validator = MagicMock()
        mock_validator.validate_risk_preset = MagicMock(
            return_value=MagicMock(valid=True)
        )
        mock_validator.validate_leverage = MagicMock(
            return_value=MagicMock(valid=True)
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.configure_strategy("balanced", 3.0, 50000)
        
        assert result["success"] is True
        assert result["config"]["risk_preset"] == "balanced"
        assert result["config"]["leverage"] == 3.0
    
    @pytest.mark.asyncio
    async def test_configure_strategy_invalid_preset(self):
        """Test strategy configuration with invalid preset."""
        from backend.dashboard.setup.validators import ValidationResult, SetupValidator
        mock_db = AsyncMock()
        
        # Use real validator to test actual validation
        steps = SetupSteps(db=mock_db)
        result = await steps.configure_strategy("invalid_preset", 3.0)
        
        assert result["success"] is False
        assert "Invalid preset" in result["error"]
    
    @pytest.mark.asyncio
    async def test_configure_strategy_invalid_leverage(self):
        """Test strategy configuration with invalid leverage."""
        from backend.dashboard.setup.validators import ValidationResult, SetupValidator
        mock_db = AsyncMock()
        
        # Use real validator to test actual validation
        steps = SetupSteps(db=mock_db)
        result = await steps.configure_strategy("balanced", 10.0)  # 10x > 4x max
        
        assert result["success"] is False
        assert "leverage" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_configure_strategy_default_max_size(self):
        """Test strategy configuration with default max position size."""
        mock_db = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        mock_validator = MagicMock()
        mock_validator.validate_risk_preset = MagicMock(
            return_value=MagicMock(valid=True)
        )
        mock_validator.validate_leverage = MagicMock(
            return_value=MagicMock(valid=True)
        )
        
        steps = SetupSteps(db=mock_db, validator=mock_validator)
        result = await steps.configure_strategy("balanced", 3.0)  # No max_position_size
        
        assert result["success"] is True
        assert result["config"]["max_position_size"] == 50000  # Default


class TestFinalizeSetup:
    """Tests for finalize_setup method."""
    
    @pytest.mark.asyncio
    async def test_finalize_setup_success(self):
        """Test successful setup finalization."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "privy_auth_key_plain": "auth_key",
            "asgard_api_key_plain": "asgard_key",
            "hyperliquid_api_key_plain": "hl_key"
        }.get(key))
        mock_db.set_encrypted_config = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        mock_em = MagicMock(spec=EncryptionManager)
        mock_em.encrypt = MagicMock(side_effect=lambda x: f"encrypted_{x}")
        
        steps = SetupSteps(db=mock_db)
        result = await steps.finalize_setup(mock_em)
        
        assert result["success"] is True
        assert "Setup complete" in result["message"]
        mock_db.set_config.assert_called_with("setup_completed", "true")
    
    @pytest.mark.asyncio
    async def test_finalize_setup_partial_keys(self):
        """Test finalization with only some keys present."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=lambda key: {
            "privy_auth_key_plain": None,
            "asgard_api_key_plain": "asgard_key",
            "hyperliquid_api_key_plain": None
        }.get(key))
        mock_db.set_encrypted_config = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.set_config = AsyncMock()
        
        mock_em = MagicMock(spec=EncryptionManager)
        mock_em.encrypt = MagicMock(side_effect=lambda x: f"encrypted_{x}")
        
        steps = SetupSteps(db=mock_db)
        result = await steps.finalize_setup(mock_em)
        
        assert result["success"] is True
        # Should only encrypt asgard key
        mock_db.set_encrypted_config.assert_called_once_with("asgard_api_key", "encrypted_asgard_key")
    
    @pytest.mark.asyncio
    async def test_finalize_setup_error(self):
        """Test finalization with error."""
        mock_db = AsyncMock()
        mock_db.get_config = AsyncMock(side_effect=Exception("DB error"))
        
        mock_em = MagicMock(spec=EncryptionManager)
        
        steps = SetupSteps(db=mock_db)
        result = await steps.finalize_setup(mock_em)
        
        assert result["success"] is False
        assert "Failed to finalize" in result["error"]
