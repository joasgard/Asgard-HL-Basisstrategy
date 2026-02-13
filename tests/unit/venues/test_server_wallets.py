"""
Tests for ServerWalletService — per-user server wallet provisioning.

Covers:
- ServerWallets dataclass properties
- get_user_wallets: existing user, user not found
- ensure_wallets_for_user: fresh provisioning, idempotent (already exists),
  partial recovery (EVM exists, Solana missing), user not in DB
- _create_evm_wallet: policy attachment
- _create_solana_wallet: policy attachment, missing solana policy
- Policy IDs loading: success, missing file
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from bot.venues.server_wallets import (
    ServerWallets,
    ServerWalletService,
    _load_policy_ids,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

USER_ID = "did:privy:test_user_123"


@pytest.fixture(autouse=True)
def reset_policy_cache():
    """Reset the module-level policy ID cache between tests."""
    import bot.venues.server_wallets as mod
    original = mod._policy_ids
    mod._policy_ids = None
    yield
    mod._policy_ids = original


@pytest.fixture
def policy_ids():
    return {
        "evm_policy_id": "evm_pol_123",
        "solana_policy_id": "sol_pol_456",
    }


@pytest.fixture
def mock_db():
    """Mock Database with transaction support."""
    db = MagicMock()

    # Transaction context manager
    tx = MagicMock()
    tx.execute = AsyncMock()
    tx.fetchone = AsyncMock()

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=tx)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db.transaction.return_value = ctx

    db.fetchone = AsyncMock()
    db.execute = AsyncMock()

    # Expose tx for test assertions
    db._tx = tx
    return db


@pytest.fixture
def mock_privy_client():
    """Mock Privy API client."""
    client = MagicMock()

    # wallets.create returns an object with .id and .address
    evm_wallet = MagicMock()
    evm_wallet.id = "evm_wallet_id_1"
    evm_wallet.address = "0xEvmAddress1"

    sol_wallet = MagicMock()
    sol_wallet.id = "sol_wallet_id_1"
    sol_wallet.address = "SolAddress1"

    client.wallets.create.side_effect = [evm_wallet, sol_wallet]
    client.wallets.update = MagicMock()

    return client


@pytest.fixture
def service(mock_db, mock_privy_client, policy_ids):
    """Create ServerWalletService with mocked deps."""
    with patch(
        "bot.venues.server_wallets._load_policy_ids",
        return_value=policy_ids,
    ):
        svc = ServerWalletService(mock_db)
        svc._client = mock_privy_client
        return svc


# ---------------------------------------------------------------------------
# ServerWallets dataclass tests
# ---------------------------------------------------------------------------


class TestServerWallets:
    def test_is_complete_all_set(self):
        w = ServerWallets(
            evm_wallet_id="e1", evm_address="0xA",
            solana_wallet_id="s1", solana_address="SolB",
        )
        assert w.is_complete is True
        assert w.is_partial is False

    def test_is_complete_empty(self):
        w = ServerWallets()
        assert w.is_complete is False
        assert w.is_partial is False

    def test_is_partial_evm_only(self):
        w = ServerWallets(evm_wallet_id="e1", evm_address="0xA")
        assert w.is_complete is False
        assert w.is_partial is True

    def test_is_partial_solana_only(self):
        w = ServerWallets(solana_wallet_id="s1", solana_address="SolB")
        assert w.is_complete is False
        assert w.is_partial is True


# ---------------------------------------------------------------------------
# get_user_wallets tests
# ---------------------------------------------------------------------------


class TestGetUserWallets:
    @pytest.mark.asyncio
    async def test_user_with_wallets(self, service, mock_db):
        mock_db.fetchone.return_value = {
            "server_evm_wallet_id": "e1",
            "server_evm_address": "0xA",
            "server_solana_wallet_id": "s1",
            "server_solana_address": "SolB",
        }
        wallets = await service.get_user_wallets(USER_ID)
        assert wallets.is_complete
        assert wallets.evm_wallet_id == "e1"
        assert wallets.solana_address == "SolB"

    @pytest.mark.asyncio
    async def test_user_not_found(self, service, mock_db):
        mock_db.fetchone.return_value = None
        wallets = await service.get_user_wallets(USER_ID)
        assert not wallets.is_complete
        assert wallets.evm_wallet_id is None

    @pytest.mark.asyncio
    async def test_user_with_no_wallets(self, service, mock_db):
        mock_db.fetchone.return_value = {
            "server_evm_wallet_id": None,
            "server_evm_address": None,
            "server_solana_wallet_id": None,
            "server_solana_address": None,
        }
        wallets = await service.get_user_wallets(USER_ID)
        assert not wallets.is_complete
        assert not wallets.is_partial


# ---------------------------------------------------------------------------
# ensure_wallets_for_user tests
# ---------------------------------------------------------------------------


class TestEnsureWalletsForUser:
    @pytest.mark.asyncio
    async def test_fast_path_already_complete(self, service, mock_db):
        """If wallets already exist, skip transaction entirely."""
        mock_db.fetchone.return_value = {
            "server_evm_wallet_id": "e1",
            "server_evm_address": "0xA",
            "server_solana_wallet_id": "s1",
            "server_solana_address": "SolB",
        }
        wallets = await service.ensure_wallets_for_user(USER_ID)
        assert wallets.is_complete
        # Transaction should NOT have been entered
        mock_db.transaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_fresh_provisioning(self, service, mock_db, mock_privy_client, policy_ids):
        """Create both wallets when user has none."""
        # Fast path: no wallets
        mock_db.fetchone.return_value = {
            "server_evm_wallet_id": None,
            "server_evm_address": None,
            "server_solana_wallet_id": None,
            "server_solana_address": None,
        }
        # Under lock: same result
        tx = mock_db._tx
        tx.fetchone.return_value = {
            "server_evm_wallet_id": None,
            "server_evm_address": None,
            "server_solana_wallet_id": None,
            "server_solana_address": None,
        }

        with patch("bot.venues.server_wallets._load_policy_ids", return_value=policy_ids):
            wallets = await service.ensure_wallets_for_user(USER_ID)

        assert wallets.is_complete
        assert wallets.evm_wallet_id == "evm_wallet_id_1"
        assert wallets.solana_wallet_id == "sol_wallet_id_1"

        # Verify advisory lock was acquired
        tx.execute.assert_any_call(
            "SELECT pg_advisory_xact_lock(hashtext($1))",
            (f"provision:{USER_ID}",),
        )

        # Verify Privy API calls
        assert mock_privy_client.wallets.create.call_count == 2

        # Verify policy attachment
        mock_privy_client.wallets.update.assert_any_call(
            "evm_wallet_id_1", policy_ids=["evm_pol_123"]
        )
        mock_privy_client.wallets.update.assert_any_call(
            "sol_wallet_id_1", policy_ids=["sol_pol_456"]
        )

        # Verify DB updates (2 UPDATE calls for EVM and Solana)
        assert tx.execute.call_count >= 3  # lock + 2 updates

    @pytest.mark.asyncio
    async def test_idempotent_under_lock(self, service, mock_db):
        """If wallets created by another request while waiting for lock."""
        # Fast path: no wallets
        mock_db.fetchone.return_value = {
            "server_evm_wallet_id": None,
            "server_evm_address": None,
            "server_solana_wallet_id": None,
            "server_solana_address": None,
        }
        # Under lock: wallets now exist (created by concurrent request)
        tx = mock_db._tx
        tx.fetchone.return_value = {
            "server_evm_wallet_id": "existing_evm",
            "server_evm_address": "0xExisting",
            "server_solana_wallet_id": "existing_sol",
            "server_solana_address": "SolExisting",
        }

        wallets = await service.ensure_wallets_for_user(USER_ID)
        assert wallets.is_complete
        assert wallets.evm_wallet_id == "existing_evm"
        # No Privy API calls should have been made
        service._client.wallets.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_recovery_evm_exists(self, service, mock_db, mock_privy_client, policy_ids):
        """If EVM wallet exists but Solana doesn't, only create Solana."""
        mock_db.fetchone.return_value = {
            "server_evm_wallet_id": "existing_evm",
            "server_evm_address": "0xExisting",
            "server_solana_wallet_id": None,
            "server_solana_address": None,
        }
        tx = mock_db._tx
        tx.fetchone.return_value = {
            "server_evm_wallet_id": "existing_evm",
            "server_evm_address": "0xExisting",
            "server_solana_wallet_id": None,
            "server_solana_address": None,
        }

        # Only one wallet.create call needed (Solana)
        sol_wallet = MagicMock()
        sol_wallet.id = "new_sol_id"
        sol_wallet.address = "NewSolAddr"
        mock_privy_client.wallets.create.side_effect = [sol_wallet]

        with patch("bot.venues.server_wallets._load_policy_ids", return_value=policy_ids):
            wallets = await service.ensure_wallets_for_user(USER_ID)

        assert wallets.is_complete
        assert wallets.evm_wallet_id == "existing_evm"
        assert wallets.solana_wallet_id == "new_sol_id"

        # Only one create call (for Solana)
        assert mock_privy_client.wallets.create.call_count == 1
        mock_privy_client.wallets.create.assert_called_once_with(chain_type="solana")

    @pytest.mark.asyncio
    async def test_user_not_in_database(self, service, mock_db):
        """Raise ValueError if user not found in DB under lock."""
        mock_db.fetchone.return_value = {
            "server_evm_wallet_id": None,
            "server_evm_address": None,
            "server_solana_wallet_id": None,
            "server_solana_address": None,
        }
        tx = mock_db._tx
        tx.fetchone.return_value = None  # user not found under lock

        with pytest.raises(ValueError, match="not found in database"):
            await service.ensure_wallets_for_user(USER_ID)

    @pytest.mark.asyncio
    async def test_evm_creation_failure_no_solana_attempted(self, service, mock_db, mock_privy_client, policy_ids):
        """If EVM wallet creation fails, Solana is not attempted."""
        mock_db.fetchone.return_value = {
            "server_evm_wallet_id": None,
            "server_evm_address": None,
            "server_solana_wallet_id": None,
            "server_solana_address": None,
        }
        tx = mock_db._tx
        tx.fetchone.return_value = {
            "server_evm_wallet_id": None,
            "server_evm_address": None,
            "server_solana_wallet_id": None,
            "server_solana_address": None,
        }
        mock_privy_client.wallets.create.side_effect = RuntimeError("Privy API down")

        with patch("bot.venues.server_wallets._load_policy_ids", return_value=policy_ids):
            with pytest.raises(RuntimeError, match="Privy API down"):
                await service.ensure_wallets_for_user(USER_ID)


# ---------------------------------------------------------------------------
# _create_evm_wallet / _create_solana_wallet tests
# ---------------------------------------------------------------------------


class TestCreateWallets:
    def test_create_evm_wallet(self, service, mock_privy_client, policy_ids):
        evm_wallet = MagicMock()
        evm_wallet.id = "evm_w"
        evm_wallet.address = "0xAddr"
        mock_privy_client.wallets.create.side_effect = [evm_wallet]

        with patch("bot.venues.server_wallets._load_policy_ids", return_value=policy_ids):
            result = service._create_evm_wallet()

        assert result == {"wallet_id": "evm_w", "address": "0xAddr"}
        mock_privy_client.wallets.create.assert_called_once_with(chain_type="ethereum")
        mock_privy_client.wallets.update.assert_called_once_with(
            "evm_w", policy_ids=["evm_pol_123"]
        )

    def test_create_solana_wallet(self, service, mock_privy_client, policy_ids):
        sol_wallet = MagicMock()
        sol_wallet.id = "sol_w"
        sol_wallet.address = "SolAddr"
        mock_privy_client.wallets.create.side_effect = [sol_wallet]

        with patch("bot.venues.server_wallets._load_policy_ids", return_value=policy_ids):
            result = service._create_solana_wallet()

        assert result == {"wallet_id": "sol_w", "address": "SolAddr"}
        mock_privy_client.wallets.create.assert_called_once_with(chain_type="solana")
        mock_privy_client.wallets.update.assert_called_once_with(
            "sol_w", policy_ids=["sol_pol_456"]
        )

    def test_create_solana_wallet_no_policy(self, service, mock_privy_client):
        """If solana_policy_id is missing, wallet is created without policy."""
        sol_wallet = MagicMock()
        sol_wallet.id = "sol_w"
        sol_wallet.address = "SolAddr"
        mock_privy_client.wallets.create.side_effect = [sol_wallet]

        no_sol_policy = {"evm_policy_id": "evm_pol_123"}
        with patch("bot.venues.server_wallets._load_policy_ids", return_value=no_sol_policy):
            result = service._create_solana_wallet()

        assert result == {"wallet_id": "sol_w", "address": "SolAddr"}
        # update should NOT be called (no policy to attach)
        mock_privy_client.wallets.update.assert_not_called()


# ---------------------------------------------------------------------------
# _load_policy_ids tests
# ---------------------------------------------------------------------------


class TestLoadPolicyIds:
    def test_load_success(self, tmp_path, reset_policy_cache):
        policy_file = tmp_path / "policy_ids.json"
        policy_file.write_text(json.dumps({"evm_policy_id": "x", "solana_policy_id": "y"}))

        with patch("bot.venues.server_wallets.SECRETS_DIR", tmp_path):
            import bot.venues.server_wallets as mod
            mod._policy_ids = None  # reset cache
            result = _load_policy_ids()

        assert result["evm_policy_id"] == "x"
        assert result["solana_policy_id"] == "y"

    def test_load_missing_file(self, tmp_path, reset_policy_cache):
        with patch("bot.venues.server_wallets.SECRETS_DIR", tmp_path):
            import bot.venues.server_wallets as mod
            mod._policy_ids = None
            with pytest.raises(FileNotFoundError, match="Policy IDs not found"):
                _load_policy_ids()
