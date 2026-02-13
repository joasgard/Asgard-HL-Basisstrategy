"""
Asgard Transaction Builder and Submitter.

This module handles the 3-step transaction flow:
1. BUILD: Call /create-position to get unsigned transaction
2. SIGN: Sign the transaction with Solana keypair
3. SUBMIT: Submit signed transaction via /submit-create-position-tx

Recovery mechanisms:
- SIGNED but not SUBMITTED: Rebuild with fresh blockhash, re-sign
- SUBMITTED but not CONFIRMED: Poll for confirmation, check on-chain
"""
import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from shared.config.assets import Asset
from shared.config.settings import get_settings
from shared.models.common import Protocol, TransactionState
from bot.state.state_machine import TransactionStateMachine
from shared.utils.logger import get_logger

from .client import AsgardClient, AsgardAPIError

logger = get_logger(__name__)


@dataclass
class BuildResult:
    """Result of building a transaction."""
    intent_id: str
    unsigned_tx: bytes
    blockhash: str
    protocol: Protocol
    
    
@dataclass
class SignResult:
    """Result of signing a transaction."""
    intent_id: str
    signed_tx: bytes
    signature: str
    

@dataclass
class SubmitResult:
    """Result of submitting a transaction."""
    intent_id: str
    signature: str
    confirmed: bool
    slot: Optional[int] = None


class AsgardTransactionBuilder:
    """
    Builder for Asgard margin position transactions.
    
    Implements the 3-step flow:
    1. Call /create-position to get unsigned transaction
    2. Sign with Solana keypair
    3. Submit via /submit-create-position-tx
    """
    
    def __init__(
        self,
        client: Optional[AsgardClient] = None,
        state_machine: Optional[TransactionStateMachine] = None,
        wallet_address: Optional[str] = None,
        user_id: Optional[str] = None,
        wallet_id: Optional[str] = None,
    ):
        """Initialize transaction builder.

        Args:
            client: AsgardClient instance.
            state_machine: TransactionStateMachine for persistence.
            wallet_address: Solana wallet address. If None, falls back to settings.
            user_id: User ID for multi-tenant logging.
            wallet_id: Privy wallet ID (from server wallets DB).
        """
        self.client = client or AsgardClient()
        self.state_machine = state_machine or TransactionStateMachine()
        self.user_id = user_id
        self.wallet_id = wallet_id

        settings = get_settings()
        self.wallet_address = wallet_address or settings.solana_wallet_address

        # Lazy-init Privy wallet signer
        self._privy_signer = None

    @property
    def privy_signer(self):
        """Lazy load Privy wallet signer for testing compatibility."""
        if self._privy_signer is None:
            from bot.venues.privy_signer import PrivyWalletSigner
            self._privy_signer = PrivyWalletSigner(
                wallet_id=self.wallet_id,
                wallet_address=self.wallet_address,
                user_id=self.user_id,
            )
        return self._privy_signer
    
    async def build_create_position(
        self,
        intent_id: str,
        asset: Asset,
        protocol: Protocol,
        collateral_amount: float,
        borrow_amount: float,
        collateral_mint: str,
        borrow_mint: str,
    ) -> BuildResult:
        """
        Build a create position transaction.
        
        Args:
            intent_id: Unique identifier for this transaction intent
            asset: Asset being used as collateral
            protocol: Lending protocol to use
            collateral_amount: Amount of collateral to deposit
            borrow_amount: Amount to borrow
            collateral_mint: SPL token mint of collateral
            borrow_mint: SPL token mint of borrow currency (usually USDC)
            
        Returns:
            BuildResult with unsigned transaction
            
        Raises:
            AsgardAPIError: If API call fails
        """
        logger.info(f"Building create position: intent={intent_id}, asset={asset.value}, protocol={protocol.name}")
        
        # Transition to BUILDING
        self.state_machine.transition(intent_id, TransactionState.BUILDING)
        
        try:
            # Build request payload
            payload = {
                "intentId": intent_id,
                "protocol": protocol.value,
                "tokenAMint": collateral_mint,
                "tokenBMint": borrow_mint,
                "tokenAAmount": collateral_amount,
                "tokenBAmount": borrow_amount,
                "owner": self.wallet_address,
            }
            
            # Call Asgard API to build transaction
            response = await self.client._post("/create-position", json=payload)
            
            # Extract unsigned transaction
            unsigned_tx_b64 = response.get("transaction")
            if not unsigned_tx_b64:
                raise AsgardAPIError("No transaction in response", response_data=response)
            
            unsigned_tx = base64.b64decode(unsigned_tx_b64)
            blockhash = response.get("blockhash", "")
            
            result = BuildResult(
                intent_id=intent_id,
                unsigned_tx=unsigned_tx,
                blockhash=blockhash,
                protocol=protocol,
            )
            
            # Transition to BUILT
            self.state_machine.transition(
                intent_id,
                TransactionState.BUILT,
                metadata=json.dumps({
                    "asset": asset.value,
                    "protocol": protocol.value,
                    "collateral_amount": collateral_amount,
                    "borrow_amount": borrow_amount,
                })
            )
            
            logger.info(f"Built transaction: intent={intent_id}, blockhash={blockhash[:16]}...")
            return result
            
        except Exception as e:
            logger.error(f"Failed to build transaction: {e}")
            self.state_machine.transition(
                intent_id,
                TransactionState.FAILED,
                error=str(e)
            )
            raise
    
    async def sign_transaction(
        self,
        intent_id: str,
        unsigned_tx: bytes,
    ) -> SignResult:
        """
        Sign a versioned transaction via Privy.
        
        Args:
            intent_id: Transaction intent ID
            unsigned_tx: Serialized unsigned transaction bytes
            
        Returns:
            SignResult with signed transaction and signature
        """
        logger.info(f"Signing transaction: intent={intent_id}")
        
        # Transition to SIGNING
        self.state_machine.transition(intent_id, TransactionState.SIGNING)
        
        try:
            # Sign via Privy — send base64-encoded unsigned transaction
            import base64 as b64
            unsigned_tx_b64 = b64.b64encode(unsigned_tx).decode("utf-8")

            signed_response_b64 = self.privy_signer.sign_solana_transaction(
                unsigned_tx_b64
            )

            # Response contains the signed transaction (base64-encoded)
            signed_tx_bytes = b64.b64decode(signed_response_b64)
            signature = intent_id  # Use intent_id as reference; real sig is in the tx

            result = SignResult(
                intent_id=intent_id,
                signed_tx=signed_tx_bytes,
                signature=signature,
            )
            
            self.state_machine.transition(
                intent_id,
                TransactionState.SIGNED,
                signature=signature
            )
            
            logger.info(f"Signed transaction: intent={intent_id}, signature={signature[:16]}...")
            return result
            
        except Exception as e:
            logger.error(f"Failed to sign transaction: {e}")
            self.state_machine.transition(
                intent_id,
                TransactionState.FAILED,
                error=str(e)
            )
            raise
    
    async def submit_transaction(
        self,
        intent_id: str,
        signed_tx: bytes,
    ) -> SubmitResult:
        """
        Submit a signed transaction.
        
        Args:
            intent_id: Transaction intent ID
            signed_tx: Serialized signed transaction bytes
            
        Returns:
            SubmitResult with confirmation status
        """
        logger.info(f"Submitting transaction: intent={intent_id}")
        
        # Transition to SUBMITTING
        self.state_machine.transition(intent_id, TransactionState.SUBMITTING)
        
        try:
            # Encode signed transaction
            signed_tx_b64 = base64.b64encode(signed_tx).decode("utf-8")
            
            # Submit to Asgard API
            payload = {
                "intentId": intent_id,
                "signedTransaction": signed_tx_b64,
            }
            
            response = await self.client._post("/submit-create-position-tx", json=payload)
            
            signature = response.get("signature", "")
            confirmed = response.get("confirmed", False)
            slot = response.get("slot")
            
            result = SubmitResult(
                intent_id=intent_id,
                signature=signature,
                confirmed=confirmed,
                slot=slot,
            )
            
            # Transition to SUBMITTED (or CONFIRMED if already confirmed)
            if confirmed:
                self.state_machine.transition(
                    intent_id,
                    TransactionState.CONFIRMED,
                    signature=signature,
                    metadata=json.dumps({"slot": slot})
                )
                logger.info(f"Transaction confirmed: intent={intent_id}, signature={signature[:16]}...")
            else:
                self.state_machine.transition(
                    intent_id,
                    TransactionState.SUBMITTED,
                    signature=signature
                )
                logger.info(f"Transaction submitted: intent={intent_id}, signature={signature[:16]}...")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to submit transaction: {e}")
            self.state_machine.transition(
                intent_id,
                TransactionState.FAILED,
                error=str(e)
            )
            raise
    
    async def build_close_position(
        self,
        intent_id: str,
        position_pda: str,
    ) -> BuildResult:
        """
        Build a close position transaction.
        
        Args:
            intent_id: Unique identifier
            position_pda: Position PDA address to close
            
        Returns:
            BuildResult with unsigned transaction
        """
        logger.info(f"Building close position: intent={intent_id}, position={position_pda}")
        
        self.state_machine.transition(intent_id, TransactionState.BUILDING)
        
        try:
            payload = {
                "intentId": intent_id,
                "positionPda": position_pda,
                "owner": self.wallet_address,
            }
            
            response = await self.client._post("/close-position", json=payload)
            
            unsigned_tx_b64 = response.get("transaction")
            if not unsigned_tx_b64:
                raise AsgardAPIError("No transaction in response", response_data=response)
            
            unsigned_tx = base64.b64decode(unsigned_tx_b64)
            blockhash = response.get("blockhash", "")
            
            result = BuildResult(
                intent_id=intent_id,
                unsigned_tx=unsigned_tx,
                blockhash=blockhash,
                protocol=Protocol.MARGINFI,  # Protocol not relevant for close
            )
            
            self.state_machine.transition(
                intent_id,
                TransactionState.BUILT,
                metadata=json.dumps({"position_pda": position_pda, "action": "close"})
            )
            
            logger.info(f"Built close transaction: intent={intent_id}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to build close transaction: {e}")
            self.state_machine.transition(
                intent_id,
                TransactionState.FAILED,
                error=str(e)
            )
            raise
    
    async def submit_close_transaction(
        self,
        intent_id: str,
        signed_tx: bytes,
    ) -> SubmitResult:
        """
        Submit a signed close position transaction.
        
        Args:
            intent_id: Transaction intent ID
            signed_tx: Serialized signed transaction bytes
            
        Returns:
            SubmitResult with confirmation status
        """
        logger.info(f"Submitting close transaction: intent={intent_id}")
        
        self.state_machine.transition(intent_id, TransactionState.SUBMITTING)
        
        try:
            signed_tx_b64 = base64.b64encode(signed_tx).decode("utf-8")
            
            payload = {
                "intentId": intent_id,
                "signedTransaction": signed_tx_b64,
            }
            
            response = await self.client._post("/submit-close-position-tx", json=payload)
            
            signature = response.get("signature", "")
            confirmed = response.get("confirmed", False)
            slot = response.get("slot")
            
            result = SubmitResult(
                intent_id=intent_id,
                signature=signature,
                confirmed=confirmed,
                slot=slot,
            )
            
            if confirmed:
                self.state_machine.transition(
                    intent_id,
                    TransactionState.CONFIRMED,
                    signature=signature,
                    metadata=json.dumps({"slot": slot})
                )
                logger.info(f"Close transaction confirmed: intent={intent_id}")
            else:
                self.state_machine.transition(
                    intent_id,
                    TransactionState.SUBMITTED,
                    signature=signature
                )
                logger.info(f"Close transaction submitted: intent={intent_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to submit close transaction: {e}")
            self.state_machine.transition(
                intent_id,
                TransactionState.FAILED,
                error=str(e)
            )
            raise
