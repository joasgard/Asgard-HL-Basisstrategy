"""
ETH gas funding service for server EVM wallets.

Server wallets need ETH on Arbitrum for gas (approve + bridge ≈ $0.10–0.50).
This service periodically checks each active user's server EVM wallet and
sends a small ETH top-up from an admin "gas funder" wallet if balance is low.

Config (env vars / secrets):
    GAS_FUNDER_PRIVATE_KEY  — hex private key of the funder wallet
    GAS_TOP_UP_AMOUNT       — ETH to send per top-up (default 0.005)
    GAS_MIN_BALANCE         — threshold below which to top up (default 0.002)
    GAS_CHECK_INTERVAL      — seconds between check cycles (default 3600)
"""
import asyncio
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from eth_account import Account
from web3 import AsyncWeb3

from shared.config.settings import get_settings, SECRETS_DIR
from shared.db.database import Database
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Defaults
DEFAULT_TOP_UP_AMOUNT = Decimal("0.005")   # ETH (~$10)
DEFAULT_MIN_BALANCE = Decimal("0.002")     # ETH
DEFAULT_CHECK_INTERVAL = 3600              # 1 hour
DEFAULT_ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"


def _load_funder_key() -> Optional[str]:
    """Load gas funder private key from secrets."""
    key_path = SECRETS_DIR / "gas_funder_private_key.txt"
    if key_path.exists():
        return key_path.read_text().strip()
    return None


class GasFunder:
    """Checks and tops up ETH on Arbitrum for server EVM wallets.

    Args:
        private_key: Hex-encoded private key of the funder wallet.
        rpc_url: Arbitrum RPC endpoint.
        top_up_amount: ETH to send per top-up.
        min_balance: Threshold below which to top up.
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        rpc_url: Optional[str] = None,
        top_up_amount: Decimal = DEFAULT_TOP_UP_AMOUNT,
        min_balance: Decimal = DEFAULT_MIN_BALANCE,
    ):
        self._key = private_key or _load_funder_key()
        if not self._key:
            raise ValueError(
                "Gas funder private key not found. "
                "Set GAS_FUNDER_PRIVATE_KEY or create secrets/gas_funder_private_key.txt"
            )

        settings = get_settings()
        self._rpc_url = rpc_url or settings.arbitrum_rpc_url or DEFAULT_ARBITRUM_RPC
        self._top_up = top_up_amount
        self._min_balance = min_balance

        self._account = Account.from_key(self._key)
        self._w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._rpc_url))
        self._chain_id = 42161  # Arbitrum One

        logger.info(
            "gas_funder_init",
            funder_address=self._account.address,
            top_up_eth=str(self._top_up),
            min_balance_eth=str(self._min_balance),
        )

    @property
    def funder_address(self) -> str:
        return self._account.address

    async def get_funder_balance(self) -> Decimal:
        """Get funder wallet ETH balance."""
        raw = await self._w3.eth.get_balance(self._account.address)
        return Decimal(raw) / Decimal(10**18)

    async def get_balance(self, address: str) -> Decimal:
        """Get ETH balance for any address."""
        raw = await self._w3.eth.get_balance(self._w3.to_checksum_address(address))
        return Decimal(raw) / Decimal(10**18)

    async def send_eth(self, to_address: str, amount_eth: Decimal) -> str:
        """Send ETH from funder to a target address.

        Returns:
            Transaction hash hex string.
        """
        to_addr = self._w3.to_checksum_address(to_address)
        nonce = await self._w3.eth.get_transaction_count(self._account.address)
        gas_price = await self._w3.eth.gas_price

        tx = {
            "to": to_addr,
            "value": int(amount_eth * Decimal(10**18)),
            "gas": 21000,
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": self._chain_id,
        }

        signed = self._account.sign_transaction(tx)
        tx_hash = await self._w3.eth.send_raw_transaction(signed.raw_transaction)
        hex_hash = tx_hash.hex()

        logger.info(
            "gas_top_up_sent",
            to=to_address,
            amount_eth=str(amount_eth),
            tx_hash=hex_hash,
        )
        return hex_hash

    async def check_and_fund_users(self, db: Database) -> dict:
        """Check all server EVM wallets and top up if needed.

        Returns:
            Summary dict with counts.
        """
        rows = await db.fetchall(
            """SELECT id, server_evm_address
               FROM users
               WHERE server_evm_address IS NOT NULL"""
        )

        funder_balance = await self.get_funder_balance()
        logger.info(
            "gas_funder_check_start",
            user_count=len(rows),
            funder_balance_eth=str(funder_balance),
        )

        if funder_balance < self._top_up:
            logger.warning(
                "gas_funder_low_balance",
                funder_balance_eth=str(funder_balance),
                top_up_amount=str(self._top_up),
            )
            return {"checked": len(rows), "funded": 0, "skipped": 0, "error": "funder low balance"}

        checked = 0
        funded = 0
        errors = 0

        for row in rows:
            user_id = row["id"]
            address = row["server_evm_address"]
            checked += 1

            try:
                balance = await self.get_balance(address)

                if balance < self._min_balance:
                    # Check funder still has enough
                    current_funder = await self.get_funder_balance()
                    if current_funder < self._top_up + Decimal("0.001"):
                        logger.warning(
                            "gas_funder_insufficient",
                            remaining_eth=str(current_funder),
                        )
                        break

                    tx_hash = await self.send_eth(address, self._top_up)
                    logger.info(
                        "gas_top_up_complete",
                        user_id=user_id,
                        address=address,
                        balance_before=str(balance),
                        amount_eth=str(self._top_up),
                        tx_hash=tx_hash,
                    )
                    funded += 1
                else:
                    logger.debug(
                        "gas_balance_sufficient",
                        user_id=user_id,
                        balance_eth=str(balance),
                    )
            except Exception as e:
                errors += 1
                logger.error(
                    "gas_top_up_failed",
                    user_id=user_id,
                    address=address,
                    error=str(e),
                )

        summary = {"checked": checked, "funded": funded, "errors": errors}
        logger.info("gas_funder_check_complete", **summary)
        return summary


async def run_gas_funder_loop(
    check_interval: int = DEFAULT_CHECK_INTERVAL,
) -> None:
    """Background loop that periodically checks and funds server wallets.

    Designed to be launched via ``asyncio.create_task()`` during bot startup.
    Runs indefinitely until cancelled.
    """
    try:
        funder = GasFunder()
    except ValueError as e:
        logger.warning("gas_funder_disabled", reason=str(e))
        return

    db = Database()
    await db.connect()

    logger.info("gas_funder_loop_started", interval_seconds=check_interval)

    try:
        while True:
            try:
                await funder.check_and_fund_users(db)
            except Exception as e:
                logger.error("gas_funder_loop_error", error=str(e))
            await asyncio.sleep(check_interval)
    finally:
        await db.close()
