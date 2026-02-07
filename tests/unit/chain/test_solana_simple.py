"""Simple tests for Solana chain client - avoiding retry decorator issues."""
import pytest
from unittest.mock import MagicMock, patch

from src.chain.solana import SolanaClient


class TestSolanaClientInit:
    """Tests for SolanaClient initialization."""
    
    @patch('src.chain.solana.get_settings')
    def test_init_uses_settings_rpc_url(self, mock_get_settings):
        """Test that client uses RPC URL from settings."""
        mock_settings = MagicMock()
        mock_settings.solana_rpc_url = "https://test.solana.com"
        mock_settings.solana_wallet_address = "test_wallet_address"
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient') as mock_async_client:
            client = SolanaClient()
            
            mock_async_client.assert_called_once()
            call_args = mock_async_client.call_args
            assert "https://test.solana.com" in str(call_args)
    
    @patch('src.chain.solana.get_settings')
    def test_init_accepts_custom_rpc_url(self, mock_get_settings):
        """Test that client accepts custom RPC URL."""
        mock_settings = MagicMock()
        mock_settings.solana_wallet_address = "test_wallet_address"
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient') as mock_async_client:
            client = SolanaClient(rpc_url="https://custom.solana.com")
            
            mock_async_client.assert_called_once()
            call_args = mock_async_client.call_args
            assert "https://custom.solana.com" in str(call_args)
    
    @patch('src.chain.solana.get_settings')
    def test_wallet_address_property(self, mock_get_settings):
        """Test wallet_address property returns address from settings."""
        mock_settings = MagicMock()
        mock_settings.solana_wallet_address = "HN7cAB5L9j8rBZKF"
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient'):
            client = SolanaClient()
            
            assert client.wallet_address == "HN7cAB5L9j8rBZKF"


class TestSolanaClientMethods:
    """Tests for SolanaClient methods (without retry decorator)."""
    
    @patch('src.chain.solana.get_settings')
    def test_client_has_required_methods(self, mock_get_settings):
        """Test that client has all required methods."""
        mock_settings = MagicMock()
        mock_settings.solana_rpc_url = "https://test.solana.com"
        mock_settings.solana_wallet_address = "test_address"
        mock_get_settings.return_value = mock_settings
        
        with patch('src.chain.solana.AsyncClient'):
            client = SolanaClient()
            
            # Check methods exist
            assert hasattr(client, 'get_balance')
            assert hasattr(client, 'get_latest_blockhash')
            assert hasattr(client, 'get_signature_status')
            assert hasattr(client, 'send_transaction')
            assert hasattr(client, 'health_check')
            assert hasattr(client, 'close')
            
            # Check async methods
            import asyncio
            coroutines = [
                client.get_balance,
                client.get_latest_blockhash,
                client.get_signature_status,
                client.send_transaction,
                client.health_check,
                client.close,
            ]
            for coro in coroutines:
                assert asyncio.iscoroutinefunction(coro)



