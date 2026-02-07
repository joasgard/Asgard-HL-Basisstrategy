"""
Comprehensive tests for Solana chain client.

These tests verify:
- Initialization with various configurations
- Balance retrieval (SOL and tokens)
- Blockhash retrieval
- Transaction status checking
- Transaction confirmation
- Health checks
- Error handling
- Context manager functionality
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction

from src.chain.solana import SolanaClient


# Patch tenacity retry to disable retries during tests
@pytest.fixture(autouse=True, scope="module")
def disable_retries():
    """Disable tenacity retries for all chain tests."""
    with patch('src.utils.retry.tenacity_retry', lambda **kwargs: lambda f: f):
        with patch('src.utils.retry.before_sleep_log', lambda *args, **kwargs: None):
            yield


# Fixtures
@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.solana_rpc_url = "https://api.mainnet-beta.solana.com"
    settings.solana_wallet_address = "687wkSEuqffp39b8gvScpUAGNejjgVzabkUoEnUS3Xt5"  # Valid Solana address
    return settings


@pytest.fixture
def mock_async_client():
    """Create mock AsyncClient."""
    client = MagicMock()
    return client


# Initialization Tests
class TestSolanaClientInitialization:
    """Tests for SolanaClient initialization."""
    
    @patch('src.chain.solana.get_settings')
    def test_init_with_default_rpc(self, mock_get_settings, mock_settings):
        """Test initialization with default RPC URL from settings."""
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            client = SolanaClient()
            
            mock_client_class.assert_called_once()
            call_args = mock_client_class.call_args
            assert mock_settings.solana_rpc_url in str(call_args)
    
    @patch('src.chain.solana.get_settings')
    def test_init_with_custom_rpc(self, mock_get_settings, mock_settings):
        """Test initialization with custom RPC URL."""
        mock_get_settings.return_value = mock_settings
        custom_url = "https://custom.rpc.com"
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            client = SolanaClient(rpc_url=custom_url)
            
            mock_client_class.assert_called_once()
            call_args = mock_client_class.call_args
            assert custom_url in str(call_args)
    
    @patch('src.chain.solana.get_settings')
    def test_wallet_address_property(self, mock_get_settings, mock_settings):
        """Test wallet_address property returns settings value."""
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient'):
            client = SolanaClient()
            
            assert client.wallet_address == mock_settings.solana_wallet_address


# Balance Tests
class TestSolanaGetBalance:
    """Tests for get_balance method."""
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_balance_default_wallet(self, mock_get_settings, mock_settings):
        """Test getting balance for default wallet."""
        mock_get_settings.return_value = mock_settings
        
        mock_response = MagicMock()
        mock_response.value = 1_000_000_000  # 1 SOL in lamports
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_balance = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            balance = await client.get_balance()
            
            assert balance == 1.0  # 1 SOL
            mock_client.get_balance.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_balance_custom_pubkey(self, mock_get_settings, mock_settings):
        """Test getting balance for custom pubkey."""
        mock_get_settings.return_value = mock_settings
        custom_pubkey = "11111111111111111111111111111111"
        
        mock_response = MagicMock()
        mock_response.value = 500_000_000  # 0.5 SOL
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_balance = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            balance = await client.get_balance(pubkey=custom_pubkey)
            
            assert balance == 0.5
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_balance_zero(self, mock_get_settings, mock_settings):
        """Test getting zero balance."""
        mock_get_settings.return_value = mock_settings
        
        mock_response = MagicMock()
        mock_response.value = 0
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_balance = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            balance = await client.get_balance()
            
            assert balance == 0.0
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_balance_none_response(self, mock_get_settings, mock_settings):
        """Test handling None response value."""
        mock_get_settings.return_value = mock_settings
        
        mock_response = MagicMock()
        mock_response.value = None
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_balance = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            
            with pytest.raises(Exception, match="Failed to get balance"):
                await client.get_balance()


# Token Balance Tests
class TestSolanaGetTokenBalance:
    """Tests for get_token_balance method."""
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_token_balance_success(self, mock_get_settings, mock_settings):
        """Test getting token balance successfully."""
        mock_get_settings.return_value = mock_settings
        mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC mint
        
        # Mock token account response
        mock_token_account = MagicMock()
        mock_token_account.pubkey = Pubkey.from_string("TokenAccount1111111111111111111111111111111")
        
        mock_accounts_response = MagicMock()
        mock_accounts_response.value = [mock_token_account]
        
        # Mock balance response
        mock_balance_response = MagicMock()
        mock_balance_response.value = MagicMock()
        mock_balance_response.value.amount = "1000000"
        mock_balance_response.value.decimals = 6
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_token_accounts_by_owner = AsyncMock(return_value=mock_accounts_response)
            mock_client.get_token_account_balance = AsyncMock(return_value=mock_balance_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            balance = await client.get_token_balance(mint)
            
            assert balance == 1.0  # 1 USDC (6 decimals)
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_token_balance_no_account(self, mock_get_settings, mock_settings):
        """Test getting token balance when no account exists."""
        mock_get_settings.return_value = mock_settings
        mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        mock_accounts_response = MagicMock()
        mock_accounts_response.value = []  # No accounts
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_token_accounts_by_owner = AsyncMock(return_value=mock_accounts_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            balance = await client.get_token_balance(mint)
            
            assert balance == 0.0
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_token_balance_custom_owner(self, mock_get_settings, mock_settings):
        """Test getting token balance for custom owner."""
        mock_get_settings.return_value = mock_settings
        mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        owner = "11111111111111111111111111111111"
        
        mock_accounts_response = MagicMock()
        mock_accounts_response.value = []
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_token_accounts_by_owner = AsyncMock(return_value=mock_accounts_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            await client.get_token_balance(mint, owner=owner)
            
            # Verify custom owner was used
            call_args = mock_client.get_token_accounts_by_owner.call_args
            assert owner in str(call_args)


# Blockhash Tests
class TestSolanaGetLatestBlockhash:
    """Tests for get_latest_blockhash method."""
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_latest_blockhash_success(self, mock_get_settings, mock_settings):
        """Test getting latest blockhash."""
        mock_get_settings.return_value = mock_settings
        
        mock_blockhash_value = MagicMock()
        mock_blockhash_value.blockhash = "EET5P9x6iE5z1T7vQ6T6v6T6v6T6v6T6v6T6v6T6v6T"
        
        mock_response = MagicMock()
        mock_response.value = mock_blockhash_value
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_latest_blockhash = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            blockhash = await client.get_latest_blockhash()
            
            assert blockhash == "EET5P9x6iE5z1T7vQ6T6v6T6v6T6v6T6v6T6v6T6v6T"
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_latest_blockhash_none_response(self, mock_get_settings, mock_settings):
        """Test handling None response."""
        mock_get_settings.return_value = mock_settings
        
        mock_response = MagicMock()
        mock_response.value = None
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_latest_blockhash = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            
            with pytest.raises(Exception, match="Failed to get latest blockhash"):
                await client.get_latest_blockhash()


# Signature Status Tests
class TestSolanaGetSignatureStatus:
    """Tests for get_signature_status method."""
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_signature_status_confirmed(self, mock_get_settings, mock_settings):
        """Test getting status for confirmed transaction."""
        mock_get_settings.return_value = mock_settings
        # Use a valid signature format (88 chars base58)
        # Valid signature format (88 chars base58)
        signature = "2KtEN8azUhSKGK7ZEfGG2Lv41bg7sMhrQeuc3Pk9FXn6zFMjVFUW7NCuBzfDwT2btVDCRCCVnWok6259J3JiKKFp"
        
        mock_status = MagicMock()
        mock_status.confirmation_status = "confirmed"
        mock_status.err = None
        mock_status.slot = 123456789
        
        mock_response = MagicMock()
        mock_response.value = [mock_status]
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_signature_statuses = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            status = await client.get_signature_status(signature)
            
            assert status["confirmed"] is True
            assert status["err"] is None
            assert status["slot"] == 123456789
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_signature_status_failed(self, mock_get_settings, mock_settings):
        """Test getting status for failed transaction."""
        mock_get_settings.return_value = mock_settings
        signature = "2KtEN8azUhSKGK7ZEfGG2Lv41bg7sMhrQeuc3Pk9FXn6zFMjVFUW7NCuBzfDwT2btVDCRCCVnWok6259J3JiKKFp"
        
        mock_status = MagicMock()
        mock_status.confirmation_status = "confirmed"
        mock_status.err = {"InstructionError": [0, "Custom"]}
        mock_status.slot = 123456789
        
        mock_response = MagicMock()
        mock_response.value = [mock_status]
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_signature_statuses = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            status = await client.get_signature_status(signature)
            
            assert status["confirmed"] is True
            assert status["err"] is not None
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_signature_status_not_found(self, mock_get_settings, mock_settings):
        """Test getting status for non-existent signature."""
        mock_get_settings.return_value = mock_settings
        signature = "2KtEN8azUhSKGK7ZEfGG2Lv41bg7sMhrQeuc3Pk9FXn6zFMjVFUW7NCuBzfDwT2btVDCRCCVnWok6259J3JiKKFp"
        
        mock_response = MagicMock()
        mock_response.value = [None]  # Not found
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_signature_statuses = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            status = await client.get_signature_status(signature)
            
            assert status is None
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_get_signature_status_empty_response(self, mock_get_settings, mock_settings):
        """Test handling empty response."""
        mock_get_settings.return_value = mock_settings
        signature = "2KtEN8azUhSKGK7ZEfGG2Lv41bg7sMhrQeuc3Pk9FXn6zFMjVFUW7NCuBzfDwT2btVDCRCCVnWok6259J3JiKKFp"
        
        mock_response = MagicMock()
        mock_response.value = []  # Empty
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_signature_statuses = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            status = await client.get_signature_status(signature)
            
            assert status is None


# Transaction Confirmation Tests
class TestSolanaConfirmTransaction:
    """Tests for confirm_transaction method."""
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_confirm_transaction_success(self, mock_get_settings, mock_settings):
        """Test confirming a successful transaction."""
        mock_get_settings.return_value = mock_settings
        signature = "2KtEN8azUhSKGK7ZEfGG2Lv41bg7sMhrQeuc3Pk9FXn6zFMjVFUW7NCuBzfDwT2btVDCRCCVnWok6259J3JiKKFp"
        
        mock_status = MagicMock()
        mock_status.confirmation_status = "confirmed"
        mock_status.err = None
        mock_status.slot = 123456789
        
        mock_response = MagicMock()
        mock_response.value = [mock_status]
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_signature_statuses = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            confirmed = await client.confirm_transaction(
                signature,
                max_retries=5,
                retry_interval=0.01
            )
            
            assert confirmed is True
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_confirm_transaction_failed(self, mock_get_settings, mock_settings):
        """Test confirming a failed transaction."""
        mock_get_settings.return_value = mock_settings
        signature = "2KtEN8azUhSKGK7ZEfGG2Lv41bg7sMhrQeuc3Pk9FXn6zFMjVFUW7NCuBzfDwT2btVDCRCCVnWok6259J3JiKKFp"
        
        mock_status = MagicMock()
        mock_status.confirmation_status = "confirmed"
        mock_status.err = {"InstructionError": [0, "Custom"]}
        mock_status.slot = 123456789
        
        mock_response = MagicMock()
        mock_response.value = [mock_status]
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_signature_statuses = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            
            with pytest.raises(Exception, match="Transaction failed"):
                await client.confirm_transaction(
                    signature,
                    max_retries=1,
                    retry_interval=0.01
                )
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_confirm_transaction_timeout(self, mock_get_settings, mock_settings):
        """Test transaction confirmation timeout."""
        mock_get_settings.return_value = mock_settings
        signature = "2KtEN8azUhSKGK7ZEfGG2Lv41bg7sMhrQeuc3Pk9FXn6zFMjVFUW7NCuBzfDwT2btVDCRCCVnWok6259J3JiKKFp"
        
        # Always return None (pending)
        mock_response = MagicMock()
        mock_response.value = [None]
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_signature_statuses = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            confirmed = await client.confirm_transaction(
                signature,
                max_retries=2,
                retry_interval=0.01
            )
            
            assert confirmed is False


# Health Check Tests
class TestSolanaHealthCheck:
    """Tests for health_check method."""
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_health_check_healthy(self, mock_get_settings, mock_settings):
        """Test health check when healthy."""
        mock_get_settings.return_value = mock_settings
        
        mock_response = MagicMock()
        mock_response.value = "ok"
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_health = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            healthy = await client.health_check()
            
            assert healthy is True
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_health_check_unhealthy(self, mock_get_settings, mock_settings):
        """Test health check when unhealthy."""
        mock_get_settings.return_value = mock_settings
        
        mock_response = MagicMock()
        mock_response.value = "behind"
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_health = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            healthy = await client.health_check()
            
            assert healthy is False
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_health_check_exception(self, mock_get_settings, mock_settings):
        """Test health check with exception."""
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_health = AsyncMock(side_effect=Exception("RPC error"))
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            healthy = await client.health_check()
            
            assert healthy is False


# Context Manager Tests
class TestSolanaContextManager:
    """Tests for async context manager."""
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_context_manager_closes_client(self, mock_get_settings, mock_settings):
        """Test that context manager closes client on exit."""
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client
            
            async with SolanaClient() as client:
                assert client is not None
            
            mock_client.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_context_manager_closes_on_exception(self, mock_get_settings, mock_settings):
        """Test that context manager closes client even on exception."""
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client
            
            with pytest.raises(ValueError, match="Test error"):
                async with SolanaClient() as client:
                    raise ValueError("Test error")
            
            mock_client.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_close_method(self, mock_get_settings, mock_settings):
        """Test explicit close method."""
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            await client.close()
            
            mock_client.close.assert_called_once()


# Send Transaction Tests
class TestSolanaSendTransaction:
    """Tests for send_transaction method."""
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_send_transaction_success(self, mock_get_settings, mock_settings):
        """Test sending transaction successfully."""
        mock_get_settings.return_value = mock_settings
        
        mock_response = MagicMock()
        mock_response.value = Signature.from_string("2KtEN8azUhSKGK7ZEfGG2Lv41bg7sMhrQeuc3Pk9FXn6zFMjVFUW7NCuBzfDwT2btVDCRCCVnWok6259J3JiKKFp")
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.send_transaction = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            
            # Mock transaction
            mock_tx = MagicMock(spec=VersionedTransaction)
            
            signature = await client.send_transaction(mock_tx)
            
            assert signature is not None
            mock_client.send_transaction.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('src.chain.solana.get_settings')
    async def test_send_transaction_none_response(self, mock_get_settings, mock_settings):
        """Test handling None response."""
        mock_get_settings.return_value = mock_settings
        
        mock_response = MagicMock()
        mock_response.value = None
        
        with patch('src.chain.solana.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.send_transaction = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            client = SolanaClient()
            mock_tx = MagicMock(spec=VersionedTransaction)
            
            with pytest.raises(Exception, match="Failed to send transaction"):
                await client.send_transaction(mock_tx)
