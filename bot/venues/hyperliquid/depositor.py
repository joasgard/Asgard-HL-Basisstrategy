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

TRANSFER_ABI: List[Dict[str, Any]] = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "success", "type": "bool"}],
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


@dataclass
class WithdrawResult:
    """Result of an HL → Arbitrum withdrawal."""
    success: bool
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
        wallet_id: Optional[str] = None,
    ):
        self.arb_client = arb_client
        self.wallet_address = wallet_address
        self.user_id = user_id
        self.wallet_id = wallet_id
        self.hl_trader = hl_trader

        settings = get_settings()
        self.bridge_contract = bridge_contract or settings.hl_bridge_contract

        # Lazy Privy client
        self._privy = None

        logger.info(
            "HyperliquidDepositor initialized",
            wallet=wallet_address,
            wallet_id=wallet_id,
            bridge=self.bridge_contract,
        )

    def _get_privy_signer(self):
        """Lazy-init Privy wallet signer."""
        if self._privy is None:
            from bot.venues.privy_signer import PrivyWalletSigner
            self._privy = PrivyWalletSigner(
                wallet_id=self.wallet_id,
                wallet_address=self.wallet_address,
                user_id=self.user_id,
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

        # ---- 3. Transfer USDC to bridge ----
        # Bridge2 uses batchedDepositWithPermit internally, but the simplest
        # deposit method is a direct USDC transfer to the bridge address.
        # HL validators detect the Transfer event and credit the sender.
        approve_tx_hash = None  # no separate approve needed
        try:
            deposit_tx_hash = await self._send_transfer_tx(
                checksum_usdc, checksum_bridge, raw_amount, checksum_wallet
            )
            logger.info(f"USDC transfer to bridge confirmed: {deposit_tx_hash}")
        except Exception as e:
            return DepositResult(
                success=False,
                error=f"Bridge transfer tx failed: {e}",
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

    async def withdraw(self, amount_usdc: float) -> WithdrawResult:
        """
        Withdraw USDC from HL clearinghouse to Arbitrum wallet.

        Uses HL's withdraw3 API action, signed via EIP-712 through the
        HyperliquidSigner (accessed via hl_trader.signer). HL processes
        withdrawals in batches; funds typically arrive on Arbitrum within
        a few minutes.

        Args:
            amount_usdc: Amount of USDC to withdraw (human-readable, e.g. 500.0)

        Returns:
            WithdrawResult with status
        """
        amount = Decimal(str(amount_usdc))
        raw_amount = str(int(amount * Decimal("1_000_000")))  # 6 decimals, as string

        logger.info(f"Starting HL → Arbitrum withdrawal: {amount_usdc} USDC")

        if self.hl_trader is None:
            return WithdrawResult(
                success=False,
                error="No HL trader configured — cannot submit withdrawal",
            )

        signer = getattr(self.hl_trader, "signer", None)
        client = getattr(self.hl_trader, "client", None)

        if signer is None or client is None:
            return WithdrawResult(
                success=False,
                error="HL trader missing signer or client — cannot submit withdrawal",
            )

        # Check HL balance
        try:
            hl_balance = await self.hl_trader.get_deposited_balance()
            if hl_balance < float(amount):
                return WithdrawResult(
                    success=False,
                    error=f"Insufficient HL balance: {hl_balance} < {amount}",
                )
        except Exception as e:
            return WithdrawResult(
                success=False,
                error=f"Failed to check HL balance: {e}",
            )

        # Build withdraw3 action
        import time
        nonce = int(time.time() * 1000)

        action = {
            "type": "withdraw3",
            "hyperliquidChain": "Arbitrum",
            "signatureChainId": "0xa4b1",
            "amount": raw_amount,
            "time": nonce,
            "destination": self.wallet_address,
        }

        types = {
            "HyperliquidTransaction:Withdraw": [
                {"name": "hyperliquidChain", "type": "string"},
                {"name": "destination", "type": "string"},
                {"name": "amount", "type": "string"},
                {"name": "time", "type": "uint64"},
            ],
        }

        value = {
            "hyperliquidChain": "Arbitrum",
            "destination": self.wallet_address,
            "amount": raw_amount,
            "time": nonce,
        }

        # Sign and submit
        try:
            signed = await signer.sign_user_action(
                action=action,
                types=types,
                primary_type="HyperliquidTransaction:Withdraw",
                value=value,
                nonce=nonce,
            )

            payload = {
                "action": signed.action,
                "nonce": signed.nonce,
                "signature": signed.signature,
            }

            response = await client.exchange(payload)
            logger.info(f"Withdrawal submitted: {response}")

        except Exception as e:
            return WithdrawResult(
                success=False,
                error=f"Withdrawal submission failed: {e}",
            )

        # Poll for Arbitrum USDC balance increase
        credited = await self._poll_arb_credit(amount)

        if not credited:
            logger.warning(
                "Withdrawal submitted but Arbitrum credit not detected within timeout. "
                "HL processes withdrawals in batches — funds may arrive shortly."
            )

        return WithdrawResult(
            success=True,
            amount_usdc=amount,
        )

    async def _poll_arb_credit(self, expected_amount: Decimal) -> bool:
        """Poll Arbitrum USDC balance until the withdrawal shows up."""
        try:
            balance_before = await self.arb_client.get_usdc_balance(self.wallet_address)
        except Exception:
            logger.warning("Could not read Arbitrum balance — skipping poll")
            return True

        target = float(balance_before) + float(expected_amount) * 0.95

        elapsed = 0.0
        while elapsed < POLL_TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

            try:
                current_balance = float(
                    await self.arb_client.get_usdc_balance(self.wallet_address)
                )
            except Exception:
                continue

            if current_balance >= target:
                logger.info(
                    f"Arbitrum credit confirmed: balance {current_balance:.2f} USDC "
                    f"(was {float(balance_before):.2f})"
                )
                return True

            logger.debug(
                f"Waiting for Arbitrum credit... {current_balance:.2f} / {target:.2f} "
                f"({elapsed:.0f}s elapsed)"
            )

        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_transfer_tx(
        self, usdc_address: str, bridge_address: str, raw_amount: int, sender: str
    ) -> str:
        """Build, sign via Privy, and submit a USDC transfer to the bridge."""
        w3 = self.arb_client.w3

        usdc_contract = w3.eth.contract(address=usdc_address, abi=TRANSFER_ABI)
        tx_data = usdc_contract.functions.transfer(bridge_address, raw_amount)
        nonce = await self.arb_client.get_transaction_count(sender)
        base_fee = await self.arb_client.get_gas_price()

        tx = await tx_data.build_transaction({
            "from": sender,
            "nonce": nonce,
            "maxFeePerGas": base_fee * 2,
            "maxPriorityFeePerGas": base_fee // 5,
            "gas": 80_000,  # USDC transfer
            "chainId": 42161,  # Arbitrum One
        })

        signed_bytes = await self._sign_tx(tx)
        tx_hash = await self.arb_client.send_raw_transaction(signed_bytes)
        await self.arb_client.wait_for_transaction_receipt(tx_hash)
        return tx_hash

    async def _sign_tx(self, tx: dict) -> bytes:
        """Sign a raw EVM transaction via Privy."""
        signer = self._get_privy_signer()
        signed_hex = signer.sign_eth_transaction(tx)
        return bytes.fromhex(signed_hex.removeprefix("0x"))

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
