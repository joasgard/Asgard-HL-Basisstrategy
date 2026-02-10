"""
Solana RPC client with retry logic.
"""
from typing import Optional, Dict, Any

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction

from src.config.settings import get_settings
from src.utils.logger import get_logger
from src.utils.retry import retry_rpc

logger = get_logger(__name__)


class SolanaClient:
    """
    Async Solana RPC client with retry and error handling.
    """
    
    def __init__(self, rpc_url: Optional[str] = None):
        self.settings = get_settings()
        self.rpc_url = rpc_url or self.settings.solana_rpc_url
        self.client = AsyncClient(self.rpc_url, commitment=Confirmed)
        
    @property
    def wallet_address(self) -> str:
        """Get wallet public key as string from settings."""
        return self.settings.solana_wallet_address
    
    @retry_rpc
    async def get_balance(self, pubkey: Optional[str] = None) -> float:
        """
        Get SOL balance for a pubkey.
        
        Args:
            pubkey: Public key to check (default: wallet address)
        
        Returns:
            Balance in SOL
        """
        target = Pubkey.from_string(pubkey) if pubkey else Pubkey.from_string(self.wallet_address)
        
        resp = await self.client.get_balance(target)
        if resp.value is None:
            raise Exception(f"Failed to get balance for {target}")
        
        return resp.value / 1e9  # Convert lamports to SOL
    
    @retry_rpc
    async def get_token_balance(self, mint: str, owner: Optional[str] = None) -> float:
        """
        Get SPL token balance.
        
        Args:
            mint: Token mint address
            owner: Token account owner (default: wallet)
        
        Returns:
            Token balance in UI units
        """
        owner_pubkey = Pubkey.from_string(owner) if owner else Pubkey.from_string(self.wallet_address)
        mint_pubkey = Pubkey.from_string(mint)
        
        # Get token account
        resp = await self.client.get_token_accounts_by_owner(
            owner_pubkey,
            {"mint": mint_pubkey},
            commitment=Confirmed,
        )
        
        if not resp.value:
            return 0.0
        
        # Get balance from first account
        token_account = resp.value[0]
        balance_resp = await self.client.get_token_account_balance(
            Pubkey.from_string(str(token_account.pubkey))
        )
        
        if balance_resp.value is None:
            return 0.0
        
        # Parse amount based on decimals
        amount = int(balance_resp.value.amount)
        decimals = balance_resp.value.decimals
        
        return amount / (10 ** decimals)
    
    @retry_rpc
    async def get_latest_blockhash(self) -> str:
        """Get latest blockhash for transaction construction."""
        resp = await self.client.get_latest_blockhash()
        if resp.value is None:
            raise Exception("Failed to get latest blockhash")
        
        return str(resp.value.blockhash)
    
    @retry_rpc
    async def get_signature_status(
        self, 
        signature: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check status of a transaction signature.
        
        Returns:
            Status dict with 'confirmed', 'err', etc. or None if not found
        """
        sig = Signature.from_string(signature)
        resp = await self.client.get_signature_statuses([sig])
        
        if not resp.value or not resp.value[0]:
            return None
        
        status = resp.value[0]
        return {
            "confirmed": status.confirmation_status is not None,
            "err": status.err,
            "slot": status.slot,
        }
    
    @retry_rpc
    async def send_transaction(
        self,
        transaction: VersionedTransaction,
        opts: Optional[TxOpts] = None,
    ) -> str:
        """
        Send a signed transaction.
        
        Args:
            transaction: Signed versioned transaction
            opts: Transaction options
        
        Returns:
            Transaction signature
        """
        if opts is None:
            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
        
        resp = await self.client.send_transaction(transaction, opts=opts)
        
        if resp.value is None:
            raise Exception("Failed to send transaction")
        
        signature = str(resp.value)
        logger.info("transaction_sent", signature=signature, rpc_url=self.rpc_url)
        
        return signature
    
    @retry_rpc
    async def confirm_transaction(
        self,
        signature: str,
        max_retries: int = 60,
        retry_interval: float = 0.5,
    ) -> bool:
        """
        Wait for transaction confirmation.
        
        Args:
            signature: Transaction signature
            max_retries: Maximum confirmation attempts
            retry_interval: Seconds between attempts
        
        Returns:
            True if confirmed, False if timeout
        """
        import asyncio
        
        for i in range(max_retries):
            status = await self.get_signature_status(signature)
            
            if status is None:
                await asyncio.sleep(retry_interval)
                continue
            
            if status.get("err") is not None:
                raise Exception(f"Transaction failed: {status['err']}")
            
            if status.get("confirmed"):
                return True
            
            await asyncio.sleep(retry_interval)
        
        return False
    
    async def health_check(self) -> bool:
        """
        Quick health check for the RPC connection.
        
        Returns:
            True if healthy
        """
        try:
            resp = await self.client.get_health()
            return resp.value == "ok"
        except Exception as e:
            logger.warning("solana_health_check_failed", error=str(e))
            return False
    
    async def close(self):
        """Close the client connection."""
        await self.client.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
