"""Tests for privy_signer.py — PrivyWalletSigner, circuit breaker, retry, error handling.

Covers:
- PrivyWalletSigner initialization (wallet_id, wallet_address, both, neither)
- wallet_id property (set, not set → ValueError)
- sign_typed_data_v4 happy path + policy denial + signing error
- sign_eth_transaction happy path + int-to-hex conversion
- sign_solana_transaction happy path + chain_type kwarg
- _call_rpc retry behavior (transient errors retried, policy denial not retried)
- _call_rpc circuit breaker integration (open → rejects, success → resets)
- SigningCircuitBreaker (threshold, cooldown, reset on success, half-open)
- _is_policy_denial / _is_retriable helpers
- PolicyDeniedError / SigningError dataclass fields
"""
import time
from unittest.mock import MagicMock, patch

import pytest

from bot.venues.privy_signer import (
    PolicyDeniedError,
    PrivyWalletSigner,
    SigningCircuitBreaker,
    SigningError,
    _is_policy_denial,
    _is_retriable,
)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestIsPolicyDenial:
    """Tests for _is_policy_denial helper."""

    @pytest.mark.parametrize("msg", [
        "Request denied by policy",
        "Policy violation: transfer not allowed",
        "Action not allowed by wallet policy",
        "Transaction blocked by Privy",
        "403 Forbidden: policy check failed",
    ])
    def test_detects_policy_keywords(self, msg):
        assert _is_policy_denial(Exception(msg)) is True

    @pytest.mark.parametrize("msg", [
        "Connection timeout after 30s",
        "502 Bad Gateway",
        "Internal server error",
        "Insufficient funds",
    ])
    def test_rejects_non_policy_errors(self, msg):
        assert _is_policy_denial(Exception(msg)) is False


class TestIsRetriable:
    """Tests for _is_retriable helper."""

    @pytest.mark.parametrize("msg", [
        "Connection refused",
        "Request timed out",
        "502 Bad Gateway",
        "503 Service Temporarily Unavailable",
        "504 Gateway Timeout",
        "429 Too Many Requests — rate limit exceeded",
    ])
    def test_detects_transient_errors(self, msg):
        assert _is_retriable(Exception(msg)) is True

    @pytest.mark.parametrize("msg", [
        "Policy denied: transfer not allowed",
        "Invalid wallet_id",
        "Insufficient funds",
        "400 Bad Request",
    ])
    def test_rejects_permanent_errors(self, msg):
        assert _is_retriable(Exception(msg)) is False


# ---------------------------------------------------------------------------
# Error class tests
# ---------------------------------------------------------------------------

class TestPolicyDeniedError:

    def test_attributes(self):
        err = PolicyDeniedError("denied by policy", wallet_id="w1", method="eth_signTypedData_v4")
        assert str(err) == "denied by policy"
        assert err.wallet_id == "w1"
        assert err.method == "eth_signTypedData_v4"
        assert isinstance(err, Exception)


class TestSigningError:

    def test_attributes_default(self):
        err = SigningError("timeout", wallet_id="w2", method="signTransaction")
        assert err.retriable is False

    def test_attributes_retriable(self):
        err = SigningError("timeout", wallet_id="w2", method="signTransaction", retriable=True)
        assert err.retriable is True
        assert err.wallet_id == "w2"
        assert err.method == "signTransaction"


# ---------------------------------------------------------------------------
# SigningCircuitBreaker tests
# ---------------------------------------------------------------------------

class TestSigningCircuitBreaker:

    def test_starts_closed(self):
        cb = SigningCircuitBreaker(threshold=3, cooldown=10)
        assert cb.is_open is False

    def test_trips_after_threshold_failures(self):
        cb = SigningCircuitBreaker(threshold=3, cooldown=10)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is False
        cb.record_failure()  # 3rd failure → trips
        assert cb.is_open is True

    def test_success_resets_counter(self):
        cb = SigningCircuitBreaker(threshold=3, cooldown=10)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # reset
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is False  # only 2 since last reset

    def test_success_resets_tripped_state(self):
        cb = SigningCircuitBreaker(threshold=2, cooldown=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        cb.record_success()
        assert cb.is_open is False

    def test_cooldown_expires(self):
        cb = SigningCircuitBreaker(threshold=1, cooldown=0.05)
        cb.record_failure()
        assert cb.is_open is True
        time.sleep(0.06)
        assert cb.is_open is False  # half-open after cooldown

    def test_does_not_re_trip_once_already_tripped(self):
        cb = SigningCircuitBreaker(threshold=2, cooldown=60)
        cb.record_failure()
        cb.record_failure()
        tripped_at = cb._tripped_at
        cb.record_failure()  # 3rd failure, already tripped
        assert cb._tripped_at == tripped_at  # timestamp unchanged


# ---------------------------------------------------------------------------
# PrivyWalletSigner — init tests
# ---------------------------------------------------------------------------

class TestPrivyWalletSignerInit:

    def test_init_with_wallet_id(self):
        signer = PrivyWalletSigner(wallet_id="wid123", wallet_address="0xAddr")
        assert signer._wallet_id == "wid123"
        assert signer._address == "0xAddr"

    def test_init_with_wallet_id_only(self):
        signer = PrivyWalletSigner(wallet_id="wid123")
        assert signer._wallet_id == "wid123"
        assert signer._address == ""

    def test_init_with_wallet_address_only(self):
        signer = PrivyWalletSigner(wallet_address="0xAddr")
        assert signer._wallet_id is None
        assert signer._address == "0xAddr"

    def test_init_with_neither_raises(self):
        with pytest.raises(ValueError, match="Either wallet_id or wallet_address"):
            PrivyWalletSigner()

    def test_init_stores_user_id(self):
        signer = PrivyWalletSigner(wallet_id="w", user_id="uid")
        assert signer._user_id == "uid"

    def test_init_user_id_defaults_to_empty(self):
        signer = PrivyWalletSigner(wallet_id="w")
        assert signer._user_id == ""


class TestPrivyWalletSignerWalletIdProperty:

    def test_wallet_id_returns_value(self):
        signer = PrivyWalletSigner(wallet_id="wid123")
        assert signer.wallet_id == "wid123"

    def test_wallet_id_raises_when_none(self):
        signer = PrivyWalletSigner(wallet_address="0xAddr")
        with pytest.raises(ValueError, match="wallet_id not set"):
            _ = signer.wallet_id


# ---------------------------------------------------------------------------
# PrivyWalletSigner — signing methods (happy path)
# ---------------------------------------------------------------------------

class TestSignTypedDataV4:

    def test_happy_path(self):
        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="0xAddr")

        mock_response = MagicMock()
        mock_response.data.signature = "0xsig123"

        mock_client = MagicMock()
        mock_client.wallets.rpc.return_value = mock_response
        signer._client = mock_client

        # Reset circuit breaker
        from bot.venues.privy_signer import _circuit_breaker
        _circuit_breaker.record_success()

        result = signer.sign_typed_data_v4(
            domain={"name": "Exchange", "chainId": 1337},
            types={"Agent": [{"name": "source", "type": "string"}]},
            value={"source": "a"},
            primary_type="Agent",
        )

        assert result == "0xsig123"
        mock_client.wallets.rpc.assert_called_once()
        call_kwargs = mock_client.wallets.rpc.call_args
        assert call_kwargs[0][0] == "wid"
        assert call_kwargs[1]["method"] == "eth_signTypedData_v4"
        # Types should be normalized to list-of-dicts
        typed_data = call_kwargs[1]["params"]["typed_data"]
        assert typed_data["primary_type"] == "Agent"
        assert typed_data["types"]["Agent"] == [{"name": "source", "type": "string"}]


class TestSignEthTransaction:

    def test_happy_path_with_int_conversion(self):
        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="0xAddr")

        mock_response = MagicMock()
        mock_response.data.signed_transaction = "0xsignedtx"

        mock_client = MagicMock()
        mock_client.wallets.rpc.return_value = mock_response
        signer._client = mock_client

        from bot.venues.privy_signer import _circuit_breaker
        _circuit_breaker.record_success()

        result = signer.sign_eth_transaction({
            "to": "0xBridge",
            "value": 0,
            "gas": 21000,
            "data": "0xcalldata",
        })

        assert result == "0xsignedtx"
        call_kwargs = mock_client.wallets.rpc.call_args[1]
        tx_params = call_kwargs["params"]["transaction"]
        assert tx_params["value"] == "0x0"         # int → hex
        assert tx_params["gas_limit"] == "0x5208"  # gas → gas_limit, int → hex
        assert tx_params["data"] == "0xcalldata"   # string unchanged


class TestSignSolanaTransaction:

    def test_happy_path_passes_chain_type(self):
        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="SoLAddr")

        mock_response = MagicMock()
        mock_response.data.signed_transaction = "c2lnbmVk"

        mock_client = MagicMock()
        mock_client.wallets.rpc.return_value = mock_response
        signer._client = mock_client

        from bot.venues.privy_signer import _circuit_breaker
        _circuit_breaker.record_success()

        result = signer.sign_solana_transaction("dW5zaWduZWQ=")

        assert result == "c2lnbmVk"
        call_kwargs = mock_client.wallets.rpc.call_args
        assert call_kwargs[1]["method"] == "signTransaction"
        assert call_kwargs[1]["chain_type"] == "solana"
        assert call_kwargs[1]["params"]["encoding"] == "base64"


# ---------------------------------------------------------------------------
# PrivyWalletSigner — error handling paths
# ---------------------------------------------------------------------------

class TestPolicyDenialPath:

    def test_policy_denied_raises_immediately(self):
        """Policy denial should not be retried."""
        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="0xAddr")

        mock_client = MagicMock()
        mock_client.wallets.rpc.side_effect = Exception("Request denied by policy")
        signer._client = mock_client

        from bot.venues.privy_signer import _circuit_breaker
        _circuit_breaker.record_success()

        with pytest.raises(PolicyDeniedError) as exc_info:
            signer.sign_typed_data_v4(
                domain={}, types={}, value={}, primary_type="Test",
            )

        assert exc_info.value.wallet_id == "wid"
        assert exc_info.value.method == "eth_signTypedData_v4"
        # Should only have been called once (no retry)
        assert mock_client.wallets.rpc.call_count == 1


class TestRetryBehavior:

    @patch("bot.venues.privy_signer.time.sleep")
    def test_transient_error_retries_and_succeeds(self, mock_sleep):
        """Transient errors should be retried with backoff."""
        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="0xAddr")

        mock_response = MagicMock()
        mock_response.data.signed_transaction = "0xok"

        mock_client = MagicMock()
        mock_client.wallets.rpc.side_effect = [
            Exception("503 Service Temporarily Unavailable"),
            Exception("Connection timeout"),
            mock_response,  # 3rd attempt succeeds
        ]
        signer._client = mock_client

        from bot.venues.privy_signer import _circuit_breaker
        _circuit_breaker.record_success()

        result = signer.sign_eth_transaction({"to": "0x1", "value": 0})
        assert result == "0xok"
        assert mock_client.wallets.rpc.call_count == 3
        # Backoff: 1s after 1st fail, 2s after 2nd fail
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0

    @patch("bot.venues.privy_signer.time.sleep")
    def test_transient_error_exhausts_retries(self, mock_sleep):
        """After max retries, should raise SigningError."""
        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="0xAddr")

        mock_client = MagicMock()
        mock_client.wallets.rpc.side_effect = Exception("Connection timeout")
        signer._client = mock_client

        from bot.venues.privy_signer import _circuit_breaker
        _circuit_breaker.record_success()

        with pytest.raises(SigningError) as exc_info:
            signer.sign_eth_transaction({"to": "0x1", "value": 0})

        assert exc_info.value.retriable is True
        assert mock_client.wallets.rpc.call_count == 3

    def test_non_retriable_error_fails_immediately(self):
        """Non-retriable, non-policy errors fail after first attempt."""
        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="0xAddr")

        mock_client = MagicMock()
        mock_client.wallets.rpc.side_effect = Exception("Invalid wallet_id: wid")
        signer._client = mock_client

        from bot.venues.privy_signer import _circuit_breaker
        _circuit_breaker.record_success()

        with pytest.raises(SigningError) as exc_info:
            signer.sign_eth_transaction({"to": "0x1", "value": 0})

        assert exc_info.value.retriable is False
        assert mock_client.wallets.rpc.call_count == 1


class TestCircuitBreakerIntegration:

    def test_open_circuit_rejects_immediately(self):
        """When circuit breaker is open, all requests are rejected."""
        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="0xAddr")
        mock_client = MagicMock()
        signer._client = mock_client

        from bot.venues.privy_signer import _circuit_breaker
        # Force circuit breaker open
        _circuit_breaker._consecutive_failures = 0
        _circuit_breaker._tripped_at = None
        for _ in range(_circuit_breaker.threshold):
            _circuit_breaker.record_failure()

        assert _circuit_breaker.is_open is True

        with pytest.raises(SigningError, match="circuit breaker is open"):
            signer.sign_eth_transaction({"to": "0x1", "value": 0})

        # wallets.rpc should NOT have been called
        mock_client.wallets.rpc.assert_not_called()

        # Clean up
        _circuit_breaker.record_success()

    def test_failure_increments_circuit_breaker(self):
        """Non-retriable failures should increment the circuit breaker."""
        from bot.venues.privy_signer import _circuit_breaker
        _circuit_breaker.record_success()  # reset

        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="0xAddr")
        mock_client = MagicMock()
        mock_client.wallets.rpc.side_effect = Exception("Unknown fatal error")
        signer._client = mock_client

        initial_failures = _circuit_breaker._consecutive_failures

        with pytest.raises(SigningError):
            signer.sign_eth_transaction({"to": "0x1", "value": 0})

        assert _circuit_breaker._consecutive_failures == initial_failures + 1

        # Clean up
        _circuit_breaker.record_success()

    def test_success_resets_circuit_breaker(self):
        """Successful calls should reset the circuit breaker."""
        from bot.venues.privy_signer import _circuit_breaker

        # Accumulate some failures (but below threshold)
        _circuit_breaker.record_success()
        _circuit_breaker.record_failure()
        _circuit_breaker.record_failure()
        assert _circuit_breaker._consecutive_failures == 2

        signer = PrivyWalletSigner(wallet_id="wid", wallet_address="0xAddr")
        mock_response = MagicMock()
        mock_response.data.signature = "0xsig"
        mock_client = MagicMock()
        mock_client.wallets.rpc.return_value = mock_response
        signer._client = mock_client

        signer.sign_typed_data_v4(
            domain={}, types={}, value={}, primary_type="Test",
        )

        assert _circuit_breaker._consecutive_failures == 0


# ---------------------------------------------------------------------------
# UserTradingContext wallet_id flow tests
# ---------------------------------------------------------------------------

class TestUserTradingContextWalletIdFlow:
    """Verify wallet_id flows from UserTradingContext → venues → signers."""

    def test_hl_trader_receives_wallet_id(self):
        from bot.venues.user_context import UserTradingContext

        ctx = UserTradingContext(
            user_id="did:privy:abc",
            evm_address="0xAddr",
            evm_wallet_id="evm_wid",
            solana_address="SoLAddr",
            solana_wallet_id="sol_wid",
        )

        with patch("bot.venues.user_context.HyperliquidTrader") as mock_trader_cls:
            mock_trader_cls.return_value = MagicMock()
            ctx.get_hl_trader()
            mock_trader_cls.assert_called_once()
            call_kwargs = mock_trader_cls.call_args[1]
            assert call_kwargs["wallet_id"] == "evm_wid"
            assert call_kwargs["wallet_address"] == "0xAddr"
            assert call_kwargs["user_id"] == "did:privy:abc"

    def test_asgard_manager_receives_wallet_id(self):
        from bot.venues.user_context import UserTradingContext

        ctx = UserTradingContext(
            user_id="did:privy:abc",
            solana_address="SoLAddr",
            solana_wallet_id="sol_wid",
        )

        with patch("bot.venues.user_context.AsgardPositionManager") as mock_mgr_cls:
            mock_mgr_cls.return_value = MagicMock()
            ctx.get_asgard_manager()
            mock_mgr_cls.assert_called_once_with(
                solana_wallet_address="SoLAddr",
                user_id="did:privy:abc",
                solana_wallet_id="sol_wid",
            )

    def test_hl_depositor_receives_wallet_id(self):
        from bot.venues.user_context import UserTradingContext

        ctx = UserTradingContext(
            user_id="did:privy:abc",
            evm_address="0xAddr",
            evm_wallet_id="evm_wid",
        )

        with patch("bot.venues.user_context.HyperliquidDepositor") as mock_dep_cls, \
             patch("bot.venues.user_context.HyperliquidTrader") as mock_trader_cls, \
             patch("bot.venues.user_context.ArbitrumClient") as mock_arb_cls:
            mock_trader_cls.return_value = MagicMock()
            mock_dep_cls.return_value = MagicMock()
            mock_arb_cls.return_value = MagicMock()
            ctx.get_hl_depositor()
            mock_dep_cls.assert_called_once()
            call_kwargs = mock_dep_cls.call_args[1]
            assert call_kwargs["wallet_id"] == "evm_wid"
            assert call_kwargs["wallet_address"] == "0xAddr"
            assert call_kwargs["user_id"] == "did:privy:abc"
