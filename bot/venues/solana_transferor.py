"""
Solana token/SOL transferor — sends SOL or SPL tokens from the server wallet.

Used for user-initiated withdrawals from the Solana server wallet to an
external address.  All signing goes through Privy's server wallet API.

Flow (SOL):
  1. Check SOL balance (need amount + rent-exempt reserve)
  2. Build SystemProgram.transfer instruction
  3. Sign via Privy
  4. Submit and confirm

Flow (USDC):
  1. Check USDC token balance
  2. Derive source/dest ATAs
  3. Optionally create dest ATA
  4. Build SPL TransferChecked instruction
  5. Sign via Privy
  6. Submit and confirm
"""
import base64
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from solders.hash import Hash
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
from spl.token.instructions import (
    TransferCheckedParams,
    transfer_checked,
    get_associated_token_address,
    create_associated_token_account,
)

from shared.chain.solana import SolanaClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

USDC_SOLANA_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
USDC_DECIMALS = 6

# Minimum SOL to keep for rent + future gas
MIN_SOL_RESERVE = Decimal("0.01")


@dataclass
class SolTransferResult:
    """Result of a SOL or SPL token transfer on Solana."""
    success: bool
    signature: Optional[str] = None
    amount: Optional[Decimal] = None
    error: Optional[str] = None


class SolanaTransferor:
    """Transfers SOL or SPL tokens from the server Solana wallet.

    Args:
        sol_client: SolanaClient for RPC operations.
        wallet_address: Solana public key of the server wallet.
        wallet_id: Privy wallet ID for signing.
        user_id: Optional user ID for logging.
    """

    def __init__(
        self,
        sol_client: SolanaClient,
        wallet_address: str,
        wallet_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.sol_client = sol_client
        self.wallet_address = wallet_address
        self.wallet_id = wallet_id
        self.user_id = user_id
        self._privy = None

        logger.info(
            "SolanaTransferor initialized",
            wallet=wallet_address,
            wallet_id=wallet_id,
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

    async def transfer_sol_to(
        self, destination: str, amount_sol: float
    ) -> SolTransferResult:
        """Transfer native SOL to a destination address.

        Args:
            destination: Solana public key of the recipient.
            amount_sol: Amount of SOL to send (e.g. 0.5).

        Returns:
            SolTransferResult with signature and status.
        """
        amount = Decimal(str(amount_sol))
        lamports = int(amount * Decimal("1_000_000_000"))

        logger.info(f"Starting SOL transfer: {amount_sol} SOL → {destination}")

        # Check balance (need amount + reserve for rent/gas)
        balance = Decimal(str(await self.sol_client.get_balance(self.wallet_address)))
        if balance < amount + MIN_SOL_RESERVE:
            return SolTransferResult(
                success=False,
                error=f"Insufficient SOL: {balance} (need {amount} + {MIN_SOL_RESERVE} reserve)",
            )

        sender = Pubkey.from_string(self.wallet_address)
        recipient = Pubkey.from_string(destination)

        ix = transfer(TransferParams(
            from_pubkey=sender,
            to_pubkey=recipient,
            lamports=lamports,
        ))

        try:
            sig = await self._build_sign_send([ix], sender)
            logger.info(f"SOL transfer confirmed: {sig}")
        except Exception as e:
            return SolTransferResult(
                success=False,
                error=f"SOL transfer failed: {e}",
            )

        return SolTransferResult(
            success=True,
            signature=sig,
            amount=amount,
        )

    async def transfer_usdc_to(
        self, destination: str, amount_usdc: float
    ) -> SolTransferResult:
        """Transfer USDC (SPL) to a destination address.

        Creates the recipient's associated token account if it doesn't exist.

        Args:
            destination: Solana public key of the recipient.
            amount_usdc: Amount of USDC to send (e.g. 100.0).

        Returns:
            SolTransferResult with signature and status.
        """
        amount = Decimal(str(amount_usdc))
        raw_amount = int(amount * Decimal("1_000_000"))  # 6 decimals

        logger.info(f"Starting USDC transfer: {amount_usdc} USDC → {destination}")

        # Check USDC balance
        usdc_balance = Decimal(
            str(await self.sol_client.get_token_balance(
                str(USDC_SOLANA_MINT), self.wallet_address
            ))
        )
        if usdc_balance < amount:
            return SolTransferResult(
                success=False,
                error=f"Insufficient USDC on Solana: {usdc_balance} < {amount}",
            )

        # Check SOL for tx fees
        sol_balance = Decimal(
            str(await self.sol_client.get_balance(self.wallet_address))
        )
        if sol_balance < MIN_SOL_RESERVE:
            return SolTransferResult(
                success=False,
                error=f"Insufficient SOL for fees: {sol_balance} < {MIN_SOL_RESERVE}",
            )

        sender = Pubkey.from_string(self.wallet_address)
        recipient = Pubkey.from_string(destination)

        source_ata = get_associated_token_address(sender, USDC_SOLANA_MINT)
        dest_ata = get_associated_token_address(recipient, USDC_SOLANA_MINT)

        instructions = []

        # Check if dest ATA exists; if not, create it (payer = sender)
        dest_ata_balance = await self.sol_client.get_token_balance(
            str(USDC_SOLANA_MINT), destination
        )
        if dest_ata_balance == 0.0:
            # May not exist — try to create (idempotent if already exists)
            create_ix = create_associated_token_account(
                payer=sender,
                owner=recipient,
                mint=USDC_SOLANA_MINT,
            )
            instructions.append(create_ix)

        transfer_ix = transfer_checked(TransferCheckedParams(
            program_id=Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"),
            source=source_ata,
            mint=USDC_SOLANA_MINT,
            dest=dest_ata,
            owner=sender,
            amount=raw_amount,
            decimals=USDC_DECIMALS,
        ))
        instructions.append(transfer_ix)

        try:
            sig = await self._build_sign_send(instructions, sender)
            logger.info(f"USDC transfer confirmed: {sig}")
        except Exception as e:
            return SolTransferResult(
                success=False,
                error=f"USDC transfer failed: {e}",
            )

        return SolTransferResult(
            success=True,
            signature=sig,
            amount=amount,
        )

    async def _build_sign_send(self, instructions: list, payer: Pubkey) -> str:
        """Build a v0 transaction, sign via Privy, submit, and confirm.

        Returns the transaction signature string.
        """
        blockhash_str = await self.sol_client.get_latest_blockhash()
        recent_blockhash = Hash.from_string(blockhash_str)

        msg = MessageV0.try_compile(
            payer=payer,
            instructions=instructions,
            address_lookup_table_accounts=[],
            recent_blockhash=recent_blockhash,
        )

        # Create an unsigned VersionedTransaction (empty signatures)
        unsigned_tx = VersionedTransaction(msg, [])
        tx_bytes = bytes(unsigned_tx)
        tx_b64 = base64.b64encode(tx_bytes).decode("utf-8")

        # Sign via Privy
        signer = self._get_privy_signer()
        signed_b64 = signer.sign_solana_transaction(tx_b64)
        signed_bytes = base64.b64decode(signed_b64)

        # Deserialize signed tx and send
        signed_tx = VersionedTransaction.from_bytes(signed_bytes)
        signature = await self.sol_client.send_transaction(signed_tx)

        # Wait for confirmation
        confirmed = await self.sol_client.confirm_transaction(signature)
        if not confirmed:
            raise Exception(f"Transaction not confirmed within timeout: {signature}")

        return signature
