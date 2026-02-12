"""
Tests for get_user_wallet_addresses — reading wallet addresses from
Privy user linked_accounts.

Wallets are created by the frontend Privy SDK (createOnLogin: 'all-users').
The backend only reads them.
"""
import pytest
from unittest.mock import AsyncMock, patch

from backend.dashboard.privy_client import PrivyClient


@pytest.fixture
def privy_client():
    """Create a PrivyClient with mocked credentials."""
    with patch.object(PrivyClient, '_load_secret', return_value="mock_secret"):
        client = PrivyClient(app_id="mock_app_id", app_secret="mock_app_secret")
    return client


class TestGetUserWalletAddresses:
    """Tests for PrivyClient.get_user_wallet_addresses()."""

    @pytest.mark.asyncio
    async def test_both_wallets_found(self, privy_client):
        """When user has both wallets in linked_accounts."""
        privy_client.get_user = AsyncMock(return_value={
            "id": "did:privy:user_123",
            "email": "test@example.com",
            "solana_address": "SoLaNa111",
            "ethereum_address": "0xEvm222",
        })

        result = await privy_client.get_user_wallet_addresses("did:privy:user_123")

        assert result["solana_address"] == "SoLaNa111"
        assert result["ethereum_address"] == "0xEvm222"

    @pytest.mark.asyncio
    async def test_only_ethereum(self, privy_client):
        """When user only has Ethereum wallet."""
        privy_client.get_user = AsyncMock(return_value={
            "id": "did:privy:user_123",
            "email": "test@example.com",
            "solana_address": None,
            "ethereum_address": "0xEvm222",
        })

        result = await privy_client.get_user_wallet_addresses("did:privy:user_123")

        assert result["solana_address"] is None
        assert result["ethereum_address"] == "0xEvm222"

    @pytest.mark.asyncio
    async def test_no_wallets(self, privy_client):
        """When user has no wallets yet."""
        privy_client.get_user = AsyncMock(return_value={
            "id": "did:privy:user_123",
            "email": "test@example.com",
            "solana_address": None,
            "ethereum_address": None,
        })

        result = await privy_client.get_user_wallet_addresses("did:privy:user_123")

        assert result["solana_address"] is None
        assert result["ethereum_address"] is None

    @pytest.mark.asyncio
    async def test_user_not_found(self, privy_client):
        """When Privy user doesn't exist."""
        privy_client.get_user = AsyncMock(return_value=None)

        result = await privy_client.get_user_wallet_addresses("did:privy:nonexistent")

        assert result["solana_address"] is None
        assert result["ethereum_address"] is None

    @pytest.mark.asyncio
    async def test_api_error(self, privy_client):
        """When Privy API call fails."""
        privy_client.get_user = AsyncMock(side_effect=Exception("API down"))

        result = await privy_client.get_user_wallet_addresses("did:privy:user_123")

        assert result["solana_address"] is None
        assert result["ethereum_address"] is None
