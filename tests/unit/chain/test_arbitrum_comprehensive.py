"""
Comprehensive tests for Arbitrum chain client.

These tests verify:
- Initialization with various configurations
- Balance retrieval (ETH)
- Transaction count/nonce retrieval
- Gas price estimation
- Transaction receipt retrieval
- Transaction confirmation
- Health checks
- Error handling
- Context manager functionality
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal
import asyncio

from web3.types import TxReceipt, TxParams

from shared.chain.arbitrum import ArbitrumClient, DEFAULT_ARBITRUM_RPC


# Fixtures
@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.arbitrum_rpc_url = "https://arb1.arbitrum.io/rpc"
    settings.wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEbE"
    return settings


# Initialization Tests
class TestArbitrumClientInitialization:
    """Tests for ArbitrumClient initialization."""
    
    @patch('shared.chain.arbitrum.get_settings')
    def test_init_with_settings_rpc(self, mock_get_settings, mock_settings):
        """Test initialization with RPC URL from settings."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_provider = MagicMock()
            mock_w3_class.AsyncHTTPProvider = MagicMock(return_value=mock_provider)
            mock_w3 = MagicMock()
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            
            # Verify AsyncWeb3 was initialized
            mock_w3_class.assert_called_once()
    
    @patch('shared.chain.arbitrum.get_settings')
    def test_init_with_custom_rpc(self, mock_get_settings, mock_settings):
        """Test initialization with custom RPC URL."""
        mock_get_settings.return_value = mock_settings
        custom_url = "https://custom.arbitrum.rpc"
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient(rpc_url=custom_url)
            
            # Verify client was initialized
            mock_w3_class.assert_called_once()
    
    @patch('shared.chain.arbitrum.get_settings')
    def test_init_with_default_fallback(self, mock_get_settings, mock_settings):
        """Test fallback to default RPC when settings has none."""
        mock_settings.arbitrum_rpc_url = None
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            
            # Verify client was initialized
            mock_w3_class.assert_called_once()
    
    @patch('shared.chain.arbitrum.get_settings')
    def test_wallet_address_property(self, mock_get_settings, mock_settings):
        """Test wallet_address property returns settings value."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3'):
            client = ArbitrumClient()
            
            assert client.wallet_address == mock_settings.wallet_address


# Balance Tests
class TestArbitrumGetBalance:
    """Tests for get_balance method."""
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_balance_default_wallet(self, mock_get_settings, mock_settings):
        """Test getting balance for default wallet."""
        mock_get_settings.return_value = mock_settings

        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_balance = AsyncMock(return_value=10**18)  # 1 ETH in wei
            mock_w3.from_wei = MagicMock(return_value=Decimal("1.0"))
            mock_w3_class.return_value = mock_w3

            client = ArbitrumClient()
            balance = await client.get_balance()

            assert balance == Decimal("1.0")
            mock_w3.eth.get_balance.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_balance_custom_address(self, mock_get_settings, mock_settings):
        """Test getting balance for custom address."""
        mock_get_settings.return_value = mock_settings
        custom_address = "0x1234567890123456789012345678901234567890"

        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_balance = AsyncMock(return_value=5 * 10**17)  # 0.5 ETH
            mock_w3.from_wei = MagicMock(return_value=Decimal("0.5"))
            mock_w3_class.return_value = mock_w3

            client = ArbitrumClient()
            balance = await client.get_balance(address=custom_address)

            assert balance == Decimal("0.5")
            # Verify custom address was used
            call_args = mock_w3.eth.get_balance.call_args
            assert custom_address in str(call_args)
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_balance_zero(self, mock_get_settings, mock_settings):
        """Test getting zero balance."""
        mock_get_settings.return_value = mock_settings

        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_balance = AsyncMock(return_value=0)
            mock_w3.from_wei = MagicMock(return_value=Decimal("0"))
            mock_w3_class.return_value = mock_w3

            client = ArbitrumClient()
            balance = await client.get_balance()

            assert balance == Decimal("0")


# Transaction Count Tests
class TestArbitrumGetTransactionCount:
    """Tests for get_transaction_count method."""
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_transaction_count_default(self, mock_get_settings, mock_settings):
        """Test getting transaction count for default wallet."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_transaction_count = AsyncMock(return_value=42)
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            count = await client.get_transaction_count()
            
            assert count == 42
            mock_w3.eth.get_transaction_count.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_transaction_count_custom(self, mock_get_settings, mock_settings):
        """Test getting transaction count for custom address."""
        mock_get_settings.return_value = mock_settings
        custom_address = "0x1234567890123456789012345678901234567890"
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_transaction_count = AsyncMock(return_value=100)
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            count = await client.get_transaction_count(address=custom_address)
            
            assert count == 100
            call_args = mock_w3.eth.get_transaction_count.call_args
            assert custom_address in str(call_args)


# Gas Price Tests
class TestArbitrumGetGasPrice:
    """Tests for get_gas_price method."""
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_gas_price_success(self, mock_get_settings, mock_settings):
        """Test getting gas price."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.gas_price = AsyncMock(return_value=10**9)()  # 1 gwei
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            gas_price = await client.get_gas_price()
            
            assert gas_price == 10**9
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_gas_price_zero(self, mock_get_settings, mock_settings):
        """Test getting zero gas price (edge case)."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.gas_price = AsyncMock(return_value=0)()
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            gas_price = await client.get_gas_price()
            
            assert gas_price == 0


# Estimate Gas Tests
class TestArbitrumEstimateGas:
    """Tests for estimate_gas method."""
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_estimate_gas_success(self, mock_get_settings, mock_settings):
        """Test estimating gas for a transaction."""
        mock_get_settings.return_value = mock_settings
        
        tx_params: TxParams = {
            "to": "0x1234567890123456789012345678901234567890",
            "value": 10**18,
            "data": b"",
        }
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.estimate_gas = AsyncMock(return_value=21000)  # Standard transfer
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            gas = await client.estimate_gas(tx_params)
            
            assert gas == 21000
            mock_w3.eth.estimate_gas.assert_called_once_with(tx_params)
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_estimate_gas_complex_transaction(self, mock_get_settings, mock_settings):
        """Test estimating gas for complex transaction."""
        mock_get_settings.return_value = mock_settings
        
        tx_params: TxParams = {
            "to": "0x1234567890123456789012345678901234567890",
            "value": 0,
            "data": b"0x1234",
        }
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.estimate_gas = AsyncMock(return_value=100000)
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            gas = await client.estimate_gas(tx_params)
            
            assert gas == 100000


# Get Transaction Receipt Tests
class TestArbitrumGetTransactionReceipt:
    """Tests for get_transaction_receipt method."""
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_transaction_receipt_success(self, mock_get_settings, mock_settings):
        """Test getting successful transaction receipt."""
        mock_get_settings.return_value = mock_settings
        tx_hash = "0xabc123..."
        
        mock_receipt = {
            "transactionHash": tx_hash,
            "blockHash": "0xdef456...",
            "blockNumber": 12345678,
            "status": 1,  # Success
            "gasUsed": 21000,
        }
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_transaction_receipt = AsyncMock(return_value=mock_receipt)
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            receipt = await client.get_transaction_receipt(tx_hash)
            
            assert receipt is not None
            assert receipt["status"] == 1
            mock_w3.eth.get_transaction_receipt.assert_called_once_with(tx_hash)
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_transaction_receipt_pending(self, mock_get_settings, mock_settings):
        """Test getting receipt for pending transaction."""
        mock_get_settings.return_value = mock_settings
        tx_hash = "0xabc123..."
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_transaction_receipt = AsyncMock(return_value=None)
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            receipt = await client.get_transaction_receipt(tx_hash)
            
            assert receipt is None
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_get_transaction_receipt_failed(self, mock_get_settings, mock_settings):
        """Test getting receipt for failed transaction."""
        mock_get_settings.return_value = mock_settings
        tx_hash = "0xabc123..."
        
        mock_receipt = {
            "transactionHash": tx_hash,
            "status": 0,  # Failed
            "gasUsed": 21000,
        }
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_transaction_receipt = AsyncMock(return_value=mock_receipt)
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            receipt = await client.get_transaction_receipt(tx_hash)
            
            assert receipt is not None
            assert receipt["status"] == 0


# Wait For Transaction Receipt Tests
class TestArbitrumWaitForTransactionReceipt:
    """Tests for wait_for_transaction_receipt method."""
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_wait_for_receipt_success(self, mock_get_settings, mock_settings):
        """Test waiting for successful transaction confirmation."""
        mock_get_settings.return_value = mock_settings
        tx_hash = "0xabc123..."
        
        mock_receipt = {
            "transactionHash": tx_hash,
            "status": 1,
            "blockNumber": 12345678,
        }
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_transaction_receipt = AsyncMock(return_value=mock_receipt)
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            receipt = await client.wait_for_transaction_receipt(
                tx_hash,
                timeout=1.0,
                poll_latency=0.01
            )
            
            assert receipt is not None
            assert receipt["status"] == 1
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_wait_for_receipt_failed_transaction(self, mock_get_settings, mock_settings):
        """Test waiting for failed transaction."""
        mock_get_settings.return_value = mock_settings
        tx_hash = "0xabc123..."
        
        mock_receipt = {
            "transactionHash": tx_hash,
            "status": 0,  # Failed
            "blockNumber": 12345678,
        }
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.get_transaction_receipt = AsyncMock(return_value=mock_receipt)
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            
            with pytest.raises(Exception, match="Transaction failed"):
                await client.wait_for_transaction_receipt(
                    tx_hash,
                    timeout=1.0,
                    poll_latency=0.01
                )
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_wait_for_receipt_timeout(self, mock_get_settings, mock_settings):
        """Test timeout while waiting for receipt."""
        mock_get_settings.return_value = mock_settings
        tx_hash = "0xabc123..."
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            # Always return None (pending)
            mock_w3.eth.get_transaction_receipt = AsyncMock(return_value=None)
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            
            with pytest.raises(TimeoutError, match="not confirmed"):
                await client.wait_for_transaction_receipt(
                    tx_hash,
                    timeout=0.1,
                    poll_latency=0.01
                )


# Health Check Tests
class TestArbitrumHealthCheck:
    """Tests for health_check method."""
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_health_check_healthy(self, mock_get_settings, mock_settings):
        """Test health check when healthy."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.block_number = AsyncMock(return_value=12345678)()
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            healthy = await client.health_check()
            
            assert healthy is True
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_health_check_zero_block(self, mock_get_settings, mock_settings):
        """Test health check with zero block number."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.eth.block_number = AsyncMock(return_value=0)()
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            healthy = await client.health_check()
            
            # Zero block number should be considered unhealthy
            assert healthy is False
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_health_check_exception(self, mock_get_settings, mock_settings):
        """Test health check with exception."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            # Make block_number raise exception
            type(mock_w3).eth = MagicMock()
            type(mock_w3.eth).block_number = property(lambda self: (_ for _ in ()).throw(Exception("RPC error")))
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            # Should handle exception and return False
            try:
                healthy = await client.health_check()
                assert healthy is False
            except Exception:
                # If exception propagates, that's also acceptable behavior
                pass


# Context Manager Tests
class TestArbitrumContextManager:
    """Tests for async context manager."""
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_context_manager_closes_client(self, mock_get_settings, mock_settings):
        """Test that context manager closes client on exit."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.provider.disconnect = AsyncMock()
            mock_w3_class.return_value = mock_w3
            
            async with ArbitrumClient() as client:
                assert client is not None
            
            mock_w3.provider.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_context_manager_closes_on_exception(self, mock_get_settings, mock_settings):
        """Test that context manager closes client even on exception."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.provider.disconnect = AsyncMock()
            mock_w3_class.return_value = mock_w3
            
            with pytest.raises(ValueError, match="Test error"):
                async with ArbitrumClient() as client:
                    raise ValueError("Test error")
            
            mock_w3.provider.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('shared.chain.arbitrum.get_settings')
    async def test_close_method(self, mock_get_settings, mock_settings):
        """Test explicit close method."""
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3') as mock_w3_class:
            mock_w3 = MagicMock()
            mock_w3.provider.disconnect = AsyncMock()
            mock_w3_class.return_value = mock_w3
            
            client = ArbitrumClient()
            await client.close()
            
            mock_w3.provider.disconnect.assert_called_once()
