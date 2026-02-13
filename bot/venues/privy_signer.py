"""
Shared Privy wallet signing helper.

Wraps the Privy SDK's wallets.rpc() method, providing a simpler interface
for EIP-712 typed data signing (EVM) and Solana transaction signing.

Phase 3 refactor: accepts wallet_id directly from the database,
removing the need for address→wallet_id resolution.  Adds structured
logging, policy-aware error handling, retry with exponential backoff,
and a circuit breaker (N2).
"""
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.config.settings import get_settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Retry configuration
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 1.0  # seconds: 1, 2, 4

# Circuit breaker configuration
CIRCUIT_BREAKER_THRESHOLD = 5   # consecutive failures to trip
CIRCUIT_BREAKER_COOLDOWN = 60   # seconds to pause after tripping

# Metrics retention
METRICS_WINDOW_SECONDS = 86400  # 24h rolling window


@dataclass
class SigningEvent:
    """A single signing event for metrics tracking."""
    timestamp: float
    result: str      # "success", "policy_denied", "error", "circuit_open"
    method: str
    wallet_id: str


class SigningMetrics:
    """Rolling-window metrics for signing activity.

    Thread-safe enough for single-process async (no lock needed).
    Events older than ``window_seconds`` are pruned on read.
    """

    def __init__(self, window_seconds: float = METRICS_WINDOW_SECONDS):
        self._window = window_seconds
        self._events: deque[SigningEvent] = deque()

    def record(self, result: str, method: str, wallet_id: str) -> None:
        self._events.append(SigningEvent(
            timestamp=time.time(),
            result=result,
            method=method,
            wallet_id=wallet_id,
        ))

    def _prune(self) -> None:
        cutoff = time.time() - self._window
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()

    def get_summary(self, window_seconds: Optional[float] = None) -> Dict[str, int]:
        """Return counts by result within the given window (default: full window)."""
        self._prune()
        cutoff = time.time() - (window_seconds or self._window)
        counts: Dict[str, int] = {"success": 0, "policy_denied": 0, "error": 0, "circuit_open": 0}
        for ev in self._events:
            if ev.timestamp >= cutoff:
                counts[ev.result] = counts.get(ev.result, 0) + 1
        return counts

    @property
    def total_last_hour(self) -> int:
        summary = self.get_summary(3600)
        return sum(summary.values())

    @property
    def policy_violations_24h(self) -> int:
        summary = self.get_summary(86400)
        return summary.get("policy_denied", 0)


# Module-level metrics singleton
_signing_metrics = SigningMetrics()


def get_signing_metrics() -> SigningMetrics:
    """Return the module-level signing metrics for health endpoints."""
    return _signing_metrics


class PolicyDeniedError(Exception):
    """Raised when a Privy policy blocks a signing request."""

    def __init__(self, message: str, wallet_id: str, method: str):
        self.wallet_id = wallet_id
        self.method = method
        super().__init__(message)


class SigningError(Exception):
    """Raised when a Privy signing request fails for non-policy reasons."""

    def __init__(self, message: str, wallet_id: str, method: str, retriable: bool = False):
        self.wallet_id = wallet_id
        self.method = method
        self.retriable = retriable
        super().__init__(message)


def _create_privy_client():
    """Create a PrivyAPI client with app credentials."""
    from privy import PrivyAPI

    settings = get_settings()

    # Read PEM file and extract the raw base64 key content.
    # The SDK expects raw base64 (optionally with "wallet-auth:" prefix),
    # NOT a full PEM file with -----BEGIN/END----- headers.
    # Passing full PEM causes the SDK to double-wrap headers, which crashes
    # cryptography.load_pem_private_key() and surfaces as APIConnectionError.
    pem_path = Path(settings.privy_auth_key_path)
    pem_content = pem_path.read_text().strip()
    lines = pem_content.splitlines()
    key_lines = [line for line in lines if not line.startswith("-----")]
    authorization_key = "".join(key_lines)

    return PrivyAPI(
        app_id=settings.privy_app_id,
        app_secret=settings.privy_app_secret,
        authorization_key=authorization_key,
    )


def _is_policy_denial(error: Exception) -> bool:
    """Check if an exception represents a Privy policy denial."""
    s = str(error).lower()
    return any(kw in s for kw in ["policy", "denied", "not allowed", "blocked", "forbidden"])


def _is_retriable(error: Exception) -> bool:
    """Check if an error is transient and worth retrying."""
    s = str(error).lower()
    return any(kw in s for kw in [
        "timeout", "timed out", "connection", "502", "503", "504",
        "temporarily unavailable", "rate limit", "429",
    ])


class SigningCircuitBreaker:
    """Module-level circuit breaker for Privy signing.

    Trips after ``threshold`` consecutive failures across any wallet.
    While tripped, all signing requests are rejected immediately for
    ``cooldown`` seconds.  Resets on any successful signing call.
    """

    def __init__(
        self,
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        cooldown: float = CIRCUIT_BREAKER_COOLDOWN,
    ):
        self.threshold = threshold
        self.cooldown = cooldown
        self._consecutive_failures = 0
        self._tripped_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        """True if circuit is tripped and still in cooldown."""
        if self._tripped_at is None:
            return False
        elapsed = time.monotonic() - self._tripped_at
        if elapsed >= self.cooldown:
            # Cooldown expired — half-open, allow next attempt
            self._tripped_at = None
            self._consecutive_failures = 0
            logger.info("signing_circuit_breaker_reset", cooldown=self.cooldown)
            return False
        return True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        if self._tripped_at is not None:
            self._tripped_at = None
            logger.info("signing_circuit_breaker_reset_on_success")

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.threshold and self._tripped_at is None:
            self._tripped_at = time.monotonic()
            logger.critical(
                "signing_circuit_breaker_tripped",
                consecutive_failures=self._consecutive_failures,
                cooldown_seconds=self.cooldown,
            )


# Singleton circuit breaker shared across all signers
_circuit_breaker = SigningCircuitBreaker()


class PrivyWalletSigner:
    """High-level signing interface backed by Privy's wallets.rpc().

    Accepts a wallet_id directly (loaded from the database by the
    provisioning service).  No address→ID resolution needed.

    Usage::

        signer = PrivyWalletSigner(wallet_id="abc123", wallet_address="0x...")
        sig = signer.sign_typed_data_v4(domain, types, value, primary_type)
        signed_tx = signer.sign_eth_transaction(tx_dict)
        signed_tx = signer.sign_solana_transaction(base64_tx)

    Args:
        wallet_id: Privy wallet ID from the database.
        wallet_address: On-chain address (used for logging / HL identity).
        user_id: Optional user ID for structured logging.

    .. deprecated::
        The ``wallet_address``-only constructor is kept for backward
        compatibility.  New code should always pass ``wallet_id``.
    """

    def __init__(
        self,
        wallet_id: Optional[str] = None,
        wallet_address: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        if wallet_id is None and wallet_address is None:
            raise ValueError("Either wallet_id or wallet_address must be provided")
        self._wallet_id = wallet_id
        self._address = wallet_address or ""
        self._user_id = user_id or ""
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _create_privy_client()
        return self._client

    @property
    def wallet_id(self) -> str:
        if self._wallet_id is None:
            raise ValueError(
                "wallet_id not set. Pass wallet_id to constructor "
                "(address→ID resolution has been removed)."
            )
        return self._wallet_id

    def _log_signing(
        self,
        method: str,
        action: str,
        result: str,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Emit structured log for every signing request."""
        log_data = {
            "user_id": self._user_id,
            "wallet_id": self._wallet_id,
            "wallet_address": self._address[:12] + "..." if self._address else "",
            "chain": "solana" if method == "signTransaction" else "evm",
            "method": method,
            "action": action,
            "result": result,
            "duration_ms": round(duration_ms, 1),
        }
        if error:
            log_data["error"] = error[:200]

        # Record metrics
        _signing_metrics.record(
            result=result,
            method=method,
            wallet_id=self._wallet_id or "",
        )

        if result == "policy_denied":
            logger.warning("signing_policy_denied", **log_data)
        elif result == "error":
            logger.error("signing_failed", **log_data)
        else:
            logger.info("signing_success", **log_data)

    def _call_rpc(self, method: str, params: dict, action: str, **kwargs) -> Any:
        """Call wallets.rpc() with retry, circuit breaker, and error classification.

        Retries up to ``RETRY_MAX_ATTEMPTS`` times with exponential backoff
        for transient errors.  Policy denials are never retried.  The
        module-level circuit breaker rejects all requests when tripped.

        Raises:
            PolicyDeniedError: If the request was blocked by a Privy policy.
            SigningError: For all other failures (after retries exhausted
                or circuit breaker tripped).
        """
        # Circuit breaker check
        if _circuit_breaker.is_open:
            self._log_signing(method, action, "circuit_open", 0.0, "circuit breaker is open")
            raise SigningError(
                "Signing circuit breaker is open — pausing all signing",
                self.wallet_id, method, retriable=True,
            )

        last_error: Optional[Exception] = None
        for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
            start = time.monotonic()
            try:
                response = self.client.wallets.rpc(
                    self.wallet_id,
                    method=method,
                    params=params,
                    **kwargs,
                )
                duration = (time.monotonic() - start) * 1000
                self._log_signing(method, action, "success", duration)
                _circuit_breaker.record_success()
                return response
            except Exception as e:
                duration = (time.monotonic() - start) * 1000

                # Policy denials are never retried
                if _is_policy_denial(e):
                    self._log_signing(method, action, "policy_denied", duration, str(e))
                    raise PolicyDeniedError(str(e), self.wallet_id, method) from e

                last_error = e
                retriable = _is_retriable(e)

                if retriable and attempt < RETRY_MAX_ATTEMPTS:
                    backoff = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "signing_retry",
                        attempt=attempt,
                        max_attempts=RETRY_MAX_ATTEMPTS,
                        backoff_s=backoff,
                        method=method,
                        error=str(e)[:100],
                    )
                    time.sleep(backoff)
                    continue

                # Final failure
                _circuit_breaker.record_failure()
                self._log_signing(method, action, "error", duration, str(e))
                raise SigningError(
                    str(e), self.wallet_id, method, retriable=retriable,
                ) from e

        # Should not reach here, but just in case
        _circuit_breaker.record_failure()
        raise SigningError(
            str(last_error), self.wallet_id, method, retriable=True,
        )

    def sign_typed_data_v4(
        self,
        domain: Dict[str, Any],
        types: Dict[str, Any],
        value: Dict[str, Any],
        primary_type: str,
    ) -> str:
        """Sign EIP-712 typed data and return the hex signature.

        Args:
            domain: EIP-712 domain dict.
            types: EIP-712 types dict (without EIP712Domain).
            value: The message/struct to sign.
            primary_type: Name of the primary type.

        Returns:
            Hex-encoded signature string (0x-prefixed).

        Raises:
            PolicyDeniedError: If blocked by policy.
            SigningError: On API / network failure.
        """
        eip712_types: Dict[str, Any] = {}
        for type_name, fields in types.items():
            eip712_types[type_name] = [
                {"name": f["name"], "type": f["type"]} for f in fields
            ]

        action = f"eip712:{primary_type}"
        response = self._call_rpc(
            method="eth_signTypedData_v4",
            params={
                "typed_data": {
                    "domain": domain,
                    "types": eip712_types,
                    "message": value,
                    "primary_type": primary_type,
                }
            },
            action=action,
        )
        return response.data.signature

    def sign_eth_transaction(self, transaction: Dict[str, Any]) -> str:
        """Sign a raw EVM transaction.

        Args:
            transaction: Transaction dict with to, data, value, gas, etc.

        Returns:
            Hex-encoded signed transaction.

        Raises:
            PolicyDeniedError: If blocked by policy.
            SigningError: On API / network failure.
        """
        # Privy API expects snake_case keys; web3.py uses camelCase
        key_map = {
            "chainId": "chain_id",
            "gasPrice": "gas_price",
            "gas": "gas_limit",
            "maxFeePerGas": "max_fee_per_gas",
            "maxPriorityFeePerGas": "max_priority_fee_per_gas",
        }
        tx_params: Dict[str, Any] = {}
        for key, val in transaction.items():
            mapped_key = key_map.get(key, key)
            if isinstance(val, int):
                tx_params[mapped_key] = hex(val)
            else:
                tx_params[mapped_key] = val

        to_addr = transaction.get("to", "unknown")
        action = f"eth_tx:{to_addr[:10]}..."
        response = self._call_rpc(
            method="eth_signTransaction",
            params={"transaction": tx_params},
            action=action,
        )
        return response.data.signed_transaction

    def sign_solana_transaction(self, unsigned_tx_base64: str) -> str:
        """Sign a Solana transaction.

        Args:
            unsigned_tx_base64: Base64-encoded unsigned transaction.

        Returns:
            Base64-encoded signed transaction.

        Raises:
            PolicyDeniedError: If blocked by policy.
            SigningError: On API / network failure.
        """
        response = self._call_rpc(
            method="signTransaction",
            params={
                "transaction": unsigned_tx_base64,
                "encoding": "base64",
            },
            action="solana_tx",
            chain_type="solana",
        )
        return response.data.signed_transaction
