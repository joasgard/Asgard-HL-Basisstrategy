"""
Pytest configuration and shared fixtures.

This module mocks the Privy library for testing since it's an external
service dependency that shouldn't be called in unit tests.
"""
import sys
from unittest.mock import MagicMock, AsyncMock

# Create mock privy module
mock_privy = MagicMock()

# Create mock PrivyClient class
mock_privy_client_class = MagicMock
mock_privy_client_instance = MagicMock()
mock_privy_client_instance.wallet.sign_typed_data = AsyncMock(return_value="0xmocksignature")
mock_privy_client_instance.wallet.sign_solana_transaction = AsyncMock(return_value=MagicMock(
    signatures=["mock_signature_123"]
))
mock_privy_client_class.return_value = mock_privy_client_instance
mock_privy.PrivyClient = mock_privy_client_class

# Register mock in sys.modules before any imports
sys.modules['privy'] = mock_privy
