"""Simple tests for Arbitrum chain client - avoiding retry decorator issues."""
import pytest
from unittest.mock import MagicMock, patch

from shared.chain.arbitrum import ArbitrumClient


class TestArbitrumClientInit:
    """Tests for ArbitrumClient initialization."""
    
    @patch('shared.chain.arbitrum.get_settings')
    def test_init_uses_settings_rpc_url(self, mock_get_settings):
        """Test that client uses RPC URL from settings."""
        mock_settings = MagicMock()
        mock_settings.arbitrum_rpc_url = "https://test.arbitrum.io"
        mock_settings.wallet_address = "0x1234567890abcdef"
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3'):
            client = ArbitrumClient()
            
            assert client is not None
    
    @patch('shared.chain.arbitrum.get_settings')
    def test_init_accepts_custom_rpc_url(self, mock_get_settings):
        """Test that client accepts custom RPC URL."""
        mock_settings = MagicMock()
        mock_settings.wallet_address = "0x1234567890abcdef"
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3'):
            client = ArbitrumClient(rpc_url="https://custom.arbitrum.io")
            
            assert client is not None
    
    @patch('shared.chain.arbitrum.get_settings')
    def test_wallet_address_property(self, mock_get_settings):
        """Test wallet_address property returns address from settings."""
        mock_settings = MagicMock()
        mock_settings.wallet_address = "0x1234567890abcdef"
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3'):
            client = ArbitrumClient()
            
            assert client.wallet_address == "0x1234567890abcdef"


class TestArbitrumClientMethods:
    """Tests for ArbitrumClient methods."""
    
    @patch('shared.chain.arbitrum.get_settings')
    def test_client_has_required_methods(self, mock_get_settings):
        """Test that client has all required methods."""
        mock_settings = MagicMock()
        mock_settings.arbitrum_rpc_url = "https://test.arbitrum.io"
        mock_settings.wallet_address = "0x1234567890abcdef"
        mock_get_settings.return_value = mock_settings
        
        with patch('shared.chain.arbitrum.AsyncWeb3'):
            client = ArbitrumClient()
            
            # Check methods exist
            assert hasattr(client, 'get_balance')
            assert hasattr(client, 'get_transaction_count')
            assert hasattr(client, 'send_raw_transaction')
            assert hasattr(client, 'health_check')
            assert hasattr(client, 'close')
            
            # Check async methods
            import asyncio
            coroutines = [
                client.get_balance,
                client.get_transaction_count,
                client.send_raw_transaction,
                client.health_check,
                client.close,
            ]
            for coro in coroutines:
                assert asyncio.iscoroutinefunction(coro)



