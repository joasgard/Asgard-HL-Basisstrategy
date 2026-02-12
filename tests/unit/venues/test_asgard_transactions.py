"""Tests for Asgard transaction builder."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shared.config.assets import Asset
from shared.models.common import Protocol
from bot.venues.asgard.transactions import (
    AsgardTransactionBuilder,
    BuildResult,
    SignResult,
    SubmitResult,
)


class TestAsgardTransactionBuilderInit:
    """Tests for transaction builder initialization."""
    
    @patch('bot.venues.asgard.transactions.get_settings')
    def test_init_loads_wallet_address_from_settings(self, mock_get_settings):
        """Test that wallet address is loaded from settings."""
        mock_settings = MagicMock()
        mock_settings.solana_wallet_address = "test_solana_address"
        mock_settings.privy_app_id = "test_app_id"
        mock_settings.privy_app_secret = "test_secret"
        mock_settings.privy_auth_key_path = "test.pem"
        mock_get_settings.return_value = mock_settings
        
        builder = AsgardTransactionBuilder()
        
        assert builder.wallet_address == "test_solana_address"
        assert builder._privy is None  # Lazy loaded
    
    def test_privy_property_lazy_loads(self):
        """Test that privy property lazy loads the client."""
        with patch('bot.venues.asgard.transactions.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                solana_wallet_address="test_address",
                privy_app_id="test_app",
                privy_app_secret="test_secret",
                privy_auth_key_path="test.pem"
            )
            
            with patch('privy.PrivyClient') as mock_privy:
                mock_client = MagicMock()
                mock_privy.return_value = mock_client
                
                builder = AsgardTransactionBuilder()
                
                # First access should create client
                privy = builder.privy
                assert privy == mock_client
                mock_privy.assert_called_once()
                
                # Second access should return same instance
                privy2 = builder.privy
                assert privy2 == mock_client
                mock_privy.assert_called_once()  # Not called again


class TestBuildCreatePosition:
    """Tests for building create position transactions."""
    
    @pytest.fixture
    def mock_builder(self):
        """Create mock builder with mocked dependencies."""
        with patch('bot.venues.asgard.transactions.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                solana_wallet_address="test_address",
                privy_app_id="test_app",
                privy_app_secret="test_secret",
                privy_auth_key_path="test.pem"
            )
            
            builder = AsgardTransactionBuilder()
            builder.client = AsyncMock()
            builder.state_machine = MagicMock()
            
            return builder
    
    @pytest.mark.asyncio
    async def test_build_create_position_success(self, mock_builder):
        """Test successful create position building."""
        # Mock client response
        mock_builder.client._post.return_value = {
            "transaction": "dGVzdF90eF9kYXRh",  # base64 encoded "test_tx_data"
            "blockhash": "test_blockhash_123"
        }
        
        result = await mock_builder.build_create_position(
            intent_id="test-intent",
            asset=Asset.SOL,
            protocol=Protocol.MARGINFI,
            collateral_amount=1000.0,
            borrow_amount=2000.0,
            collateral_mint="SOL_MINT",
            borrow_mint="USDC_MINT"
        )
        
        assert isinstance(result, BuildResult)
        assert result.intent_id == "test-intent"
        assert result.blockhash == "test_blockhash_123"
        assert result.protocol == Protocol.MARGINFI
        assert result.unsigned_tx == b"test_tx_data"
        
        # Verify API call
        mock_builder.client._post.assert_called_once()
        call_args = mock_builder.client._post.call_args
        assert call_args[0][0] == "/create-position"
    
    @pytest.mark.asyncio
    async def test_build_create_position_uses_wallet_address(self, mock_builder):
        """Test that wallet address is used in payload."""
        mock_builder.client._post.return_value = {
            "transaction": "dGVzdA==",
            "blockhash": "test_blockhash"
        }
        
        await mock_builder.build_create_position(
            intent_id="test",
            asset=Asset.SOL,
            protocol=Protocol.MARGINFI,
            collateral_amount=1000.0,
            borrow_amount=2000.0,
            collateral_mint="SOL_MINT",
            borrow_mint="USDC_MINT"
        )
        
        # Check owner field in payload
        call_kwargs = mock_builder.client._post.call_args[1]
        payload = call_kwargs.get('json', {})
        assert payload.get('owner') == "test_address"


class TestSignTransaction:
    """Tests for transaction signing."""
    
    @pytest.fixture
    def mock_builder(self):
        """Create mock builder with mocked Privy."""
        with patch('bot.venues.asgard.transactions.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                solana_wallet_address="test_address",
                privy_app_id="test_app",
                privy_app_secret="test_secret",
                privy_auth_key_path="test.pem"
            )
            
            builder = AsgardTransactionBuilder()
            builder.state_machine = MagicMock()
            
            # Mock privy client
            builder._privy = MagicMock()
            builder._privy.wallet.sign_solana_transaction = AsyncMock(
                return_value=MagicMock(
                    signatures=["test_signature_123"],
                    __bytes__=lambda self: b"signed_tx_bytes"
                )
            )
            
            return builder
    
    @pytest.mark.asyncio
    async def test_sign_transaction_success(self, mock_builder):
        """Test successful transaction signing."""
        result = await mock_builder.sign_transaction(
            intent_id="test-intent",
            unsigned_tx=b"unsigned_tx"
        )
        
        assert isinstance(result, SignResult)
        assert result.intent_id == "test-intent"
        assert result.signature == "test_signature_123"
        
        # Verify state transition
        mock_builder.state_machine.transition.assert_called_with(
            "test-intent", mock_builder.state_machine.transition.call_args[0][1], 
            signature="test_signature_123"
        )
    
    @pytest.mark.asyncio
    async def test_sign_transaction_calls_privy(self, mock_builder):
        """Test that signing delegates to Privy."""
        await mock_builder.sign_transaction(
            intent_id="test",
            unsigned_tx=b"test_tx"
        )
        
        # Verify Privy was called
        mock_builder._privy.wallet.sign_solana_transaction.assert_called_once_with(
            wallet_address="test_address",
            transaction=b"test_tx"
        )


class TestBuildClosePosition:
    """Tests for building close position transactions."""
    
    @pytest.fixture
    def mock_builder(self):
        """Create mock builder with mocked dependencies."""
        with patch('bot.venues.asgard.transactions.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                solana_wallet_address="test_address",
                privy_app_id="test_app",
                privy_app_secret="test_secret",
                privy_auth_key_path="test.pem"
            )
            
            builder = AsgardTransactionBuilder()
            builder.client = AsyncMock()
            builder.state_machine = MagicMock()
            
            return builder
    
    @pytest.mark.asyncio
    async def test_build_close_position_success(self, mock_builder):
        """Test successful close position building."""
        mock_builder.client._post.return_value = {
            "transaction": "dGVzdF9jbG9zZQ==",
            "blockhash": "test_blockhash"
        }
        
        result = await mock_builder.build_close_position(
            intent_id="close-intent",
            position_pda="test_pda_123"
        )
        
        assert isinstance(result, BuildResult)
        assert result.intent_id == "close-intent"
        
        # Verify API call
        mock_builder.client._post.assert_called_once_with(
            "/close-position",
            json={
                "intentId": "close-intent",
                "positionPda": "test_pda_123",
                "owner": "test_address"
            }
        )


class TestSubmitTransaction:
    """Tests for transaction submission."""
    
    @pytest.fixture
    def mock_builder(self):
        """Create mock builder with mocked dependencies."""
        with patch('bot.venues.asgard.transactions.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                solana_wallet_address="test_address",
                privy_app_id="test_app",
                privy_app_secret="test_secret",
                privy_auth_key_path="test.pem"
            )
            
            builder = AsgardTransactionBuilder()
            builder.client = AsyncMock()
            builder.state_machine = MagicMock()
            
            return builder
    
    @pytest.mark.asyncio
    async def test_submit_transaction_confirmed(self, mock_builder):
        """Test submitting transaction that is confirmed."""
        mock_builder.client._post.return_value = {
            "signature": "test_sig_123",
            "confirmed": True,
            "slot": 123456789
        }
        
        result = await mock_builder.submit_transaction(
            intent_id="test-intent",
            signed_tx=b"signed_tx_data"
        )
        
        assert isinstance(result, SubmitResult)
        assert result.intent_id == "test-intent"
        assert result.signature == "test_sig_123"
        assert result.confirmed is True
        assert result.slot == 123456789
