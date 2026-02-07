"""Tests for Privy client module."""
import pytest
from unittest.mock import MagicMock, patch

from src.venues.privy_client import get_privy_client


class TestGetPrivyClient:
    """Tests for get_privy_client function."""
    
    @patch('src.venues.privy_client.get_settings')
    @patch('privy.PrivyClient')
    def test_get_privy_client_returns_configured_client(self, mock_privy_class, mock_get_settings):
        """Test that get_privy_client returns a configured PrivyClient."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.privy_app_id = "test-app-id"
        mock_settings.privy_app_secret = "test-secret"
        mock_settings.privy_auth_key_path = "test_auth.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock PrivyClient instance
        mock_client = MagicMock()
        mock_privy_class.return_value = mock_client
        
        # Clear cache if any
        get_privy_client.cache_clear()
        
        # Get client
        client = get_privy_client()
        
        # Verify PrivyClient was created with correct args
        mock_privy_class.assert_called_once_with(
            app_id="test-app-id",
            app_secret="test-secret",
            authorization_private_key_path="test_auth.pem"
        )
        assert client == mock_client
    
    @patch('src.venues.privy_client.get_settings')
    @patch('privy.PrivyClient')
    def test_get_privy_client_is_singleton(self, mock_privy_class, mock_get_settings):
        """Test that get_privy_client returns same instance (singleton)."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.privy_app_id = "test-app-id"
        mock_settings.privy_app_secret = "test-secret"
        mock_settings.privy_auth_key_path = "test_auth.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock PrivyClient instance
        mock_client = MagicMock()
        mock_privy_class.return_value = mock_client
        
        # Clear cache
        get_privy_client.cache_clear()
        
        # Get client twice
        client1 = get_privy_client()
        client2 = get_privy_client()
        
        # Verify only one instance created
        mock_privy_class.assert_called_once()
        assert client1 == client2
