"""
Hyperliquid USDC Depositor — bridges USDC from Arbitrum to HL clearinghouse.

Flow:
1. Check USDC + ETH balances on Arbitrum
2. Approve USDC spend on bridge contract (if needed)
3. Call bridge deposit()
4. Poll HL clearinghouse until funds are credited

Signing is done via Privy's raw EVM tx signing (NOT EIP-712).
"""
import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from shared.chain.arbitrum import ArbitrumClient, NATIVE_USDC_ARBITRUM
from shared.config.settings import get_settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Minimal ABIs
ERC20_ABI: List[Dict[str, Any]] = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "remaining", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "success", "type": "bool"}],
        "type": "function",
    },
]

BRIDGE_DEPOSIT_ABI: List[Dict[str, Any]] = [
    {
        "constant": False,
        "inputs": [
            {"name": "amount", "type": "uint256"},
        ],
        "name": "deposit",
        "outputs": [],
        "type": "function",
    },
]

# Gas / polling defaults
MIN_ETH_FOR_BRIDGE = Decimal("0.002")  # ~2 txs worth of gas
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class DepositResult:
    """Result of an Arbitrum → HL bridge deposit."""
    success: bool
    approve_tx_hash: Optional[str] = None
    deposit_tx_hash: Optional[str] = None
    amount_usdc: Optional[Decimal] = None
    error: Optional[str] = None


class HyperliquidDepositor:
    """
    Bridges USDC from Arbitrum into the Hyperliquid clearinghouse.

    Uses the HL bridge contract on Arbitrum. Signing is via Privy
    raw transaction signing (same embedded wallet as HyperliquidSigner).

    Args:
        arb_client: ArbitrumClient for RPC reads
        wallet_address: EVM wallet address (Privy embedded wallet)
        user_id: Optional user ID for multi-tenant mode
        hl_trader: Optional HyperliquidTrader for clearinghouse balance polling
        bridge_contract: Override bridge contract address (default from settings)
    """

    def __init__(
        self,
        arb_client: ArbitrumClient,
        wallet_address: str,
        user_id: Optional[str] = None,
        hl_trader: Optional[Any] = None,
        bridge_contract: Optional[str] = None,
    ):
        self.arb_client = arb_client
        self.wallet_address = wallet_address
        self.user_id = user_id
        self.hl_trader = hl_trader

        settings = get_settings()
        self.bridge_contract = bridge_contract or settings.hl_bridge_contract

        # Lazy Privy client
        self._privy = None

        logger.info(
            "HyperliquidDepositor initialized",
            wallet=wallet_address,
            bridge=self.bridge_contract,
        )

    def _get_privy(self):
        """Lazy-init Privy client (same credentials as HyperliquidSigner)."""
        if self._privy is None:
            from privy import PrivyClient

            settings = get_settings()
            self._privy = PrivyClient(
                app_id=settings.privy_app_id,
                app_secret=settings.privy_app_secret,
                authorization_private_key_path=settings.privy_auth_key_path,
            )
        return self._privy

    async def deposit(self, amount_usdc: float) -> DepositResult:
        """
        Bridge USDC from Arbitrum wallet to Hyperliquid clearinghouse.

        Steps:
        1. Check USDC balance on Arbitrum (must cover amount)
        2. Check ETH balance on Arbitrum (need gas for ~2 txs)
        3. If current allowance < amount, submit approve tx
        4. Submit bridge deposit tx
        5. Poll HL clearinghouse balance until credited

        Args:
            amount_usdc: Amount of USDC to bridge (human-readable, e.g. 500.0)

        Returns:
            DepositResult with tx hashes and status
        """
        amount = Decimal(str(amount_usdc))
        raw_amount = int(amount * Decimal("1_000_000"))  # 6 decimals

        logger.info(f"Starting Arbitrum → HL bridge deposit: {amount_usdc} USDC")

        w3 = self.arb_client.w3
        checksum_wallet = w3.to_checksum_address(self.wallet_address)
        checksum_usdc = w3.to_checksum_address(NATIVE_USDC_ARBITRUM)
        checksum_bridge = w3.to_checksum_address(self.bridge_contract)

        # ---- 1. Check USDC balance ----
        usdc_balance = await self.arb_client.get_usdc_balance(self.wallet_address)
        if usdc_balance < amount:
            return DepositResult(
                success=False,
                error=f"Insufficient USDC on Arbitrum: {usdc_balance} < {amount}",
            )

        # ---- 2. Check ETH balance for gas ----
        eth_balance = await self.arb_client.get_balance(self.wallet_address)
        if eth_balance < MIN_ETH_FOR_BRIDGE:
            return DepositResult(
                success=False,
                error=f"Insufficient ETH for gas: {eth_balance} < {MIN_ETH_FOR_BRIDGE}",
            )

        # ---- 3. Approve if needed ----
        approve_tx_hash = None
        usdc_contract = w3.eth.contract(address=checksum_usdc, abi=ERC20_ABI)

        current_allowance = await usdc_contract.functions.allowance(
            checksum_wallet, checksum_bridge
        ).call()

        if current_allowance < raw_amount:
            logger.info("Approving USDC spend on bridge contract")
            try:
                approve_tx_hash = await self._send_approve_tx(
                    usdc_contract, checksum_bridge, raw_amount, checksum_wallet
                )
                logger.info(f"Approve tx confirmed: {approve_tx_hash}")
            except Exception as e:
                return DepositResult(
                    success=False,
                    error=f"Approve tx failed: {e}",
                )

        # ---- 4. Bridge deposit ----
        try:
            deposit_tx_hash = await self._send_deposit_tx(
                checksum_bridge, raw_amount, checksum_wallet
            )
            logger.info(f"Bridge deposit tx confirmed: {deposit_tx_hash}")
        except Exception as e:
            return DepositResult(
                success=False,
                approve_tx_hash=approve_tx_hash,
                error=f"Bridge deposit tx failed: {e}",
            )

        # ---- 5. Poll HL clearinghouse ----
        credited = await self._poll_hl_credit(amount)

        if not credited:
            logger.warning(
                "Bridge deposit tx succeeded but HL credit not detected within timeout. "
                "Funds may still arrive shortly."
            )

        return DepositResult(
            success=True,
            approve_tx_hash=approve_tx_hash,
            deposit_tx_hash=deposit_tx_hash,
            amount_usdc=amount,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_approve_tx(
        self, usdc_contract, spender: str, raw_amount: int, sender: str
    ) -> str:
        """Build, sign via Privy, and submit an ERC-20 approve tx."""
        w3 = self.arb_client.w3

        tx_data = usdc_contract.functions.approve(spender, raw_amount)
        nonce = await self.arb_client.get_transaction_count(sender)
        gas_price = await self.arb_client.get_gas_price()

        tx = tx_data.build_transaction({
            "from": sender,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 60_000,  # approve is cheap
            "chainId": 42161,  # Arbitrum One
        })

        signed_bytes = await self._sign_tx(tx)
        tx_hash = await self.arb_client.send_raw_transaction(signed_bytes)
        await self.arb_client.wait_for_transaction_receipt(tx_hash)
        return tx_hash

    async def _send_deposit_tx(
        self, bridge_address: str, raw_amount: int, sender: str
    ) -> str:
        """Build, sign via Privy, and submit a bridge deposit tx."""
        w3 = self.arb_client.w3

        bridge_contract = w3.eth.contract(
            address=bridge_address, abi=BRIDGE_DEPOSIT_ABI
        )

        tx_data = bridge_contract.functions.deposit(raw_amount)
        nonce = await self.arb_client.get_transaction_count(sender)
        gas_price = await self.arb_client.get_gas_price()

        tx = tx_data.build_transaction({
            "from": sender,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 150_000,  # bridge interactions need more gas
            "chainId": 42161,
        })

        signed_bytes = await self._sign_tx(tx)
        tx_hash = await self.arb_client.send_raw_transaction(signed_bytes)
        await self.arb_client.wait_for_transaction_receipt(tx_hash)
        return tx_hash

    async def _sign_tx(self, tx: dict) -> bytes:
        """Sign a raw EVM transaction via Privy."""
        privy = self._get_privy()
        signed = await privy.wallet.sign_transaction(
            wallet_address=self.wallet_address,
            transaction=tx,
        )
        return signed

    async def _poll_hl_credit(self, expected_amount: Decimal) -> bool:
        """Poll HL clearinghouse until the deposit shows up."""
        if self.hl_trader is None:
            logger.warning("No HL trader provided — skipping credit poll")
            return True  # Assume OK

        balance_before = await self.hl_trader.get_deposited_balance()
        target = float(balance_before) + float(expected_amount) * 0.95  # 5% tolerance

        elapsed = 0.0
        while elapsed < POLL_TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

            current_balance = await self.hl_trader.get_deposited_balance()
            if current_balance >= target:
                logger.info(
                    f"HL credit confirmed: balance {current_balance:.2f} USDC "
                    f"(was {balance_before:.2f})"
                )
                return True

            logger.debug(
                f"Waiting for HL credit... {current_balance:.2f} / {target:.2f} "
                f"({elapsed:.0f}s elapsed)"
            )

        return False
