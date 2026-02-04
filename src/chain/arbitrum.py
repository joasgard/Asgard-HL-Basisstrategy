"""
Arbitrum/Web3 client with retry logic.
"""
from typing import Optional, Dict, Any
from decimal import Decimal

from web3 import AsyncWeb3
from web3.types import TxReceipt, TxParams
from eth_account import Account
from eth_account.datastructures import SignedTransaction

from src.config.settings import get_settings
from src.utils.logger import get_logger
from src.utils.retry import retry_rpc

logger = get_logger(__name__)

# Default Arbitrum RPC
DEFAULT_ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"


class ArbitrumClient:
    """
    Async Arbitrum/Web3 client with retry and error handling.
    """
    
    def __init__(self, rpc_url: Optional[str] = None):
        self.settings = get_settings()
        self.rpc_url = rpc_url or self.settings.arbitrum_rpc_url or DEFAULT_ARBITRUM_RPC
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.rpc_url))
        self._account: Optional[Account] = None
    
    @property
    def account(self) -> Account:
        """Lazy-load account from settings."""
        if self._account is None:
            private_key = self.settings.hyperliquid_private_key
            if private_key.startswith("0x"):
                private_key = private_key[2:]
            self._account = Account.from_key(private_key)
        
        return self._account
    
    @property
    def wallet_address(self) -> str:
        """Get wallet address."""
        return self.account.address
    
    @retry_rpc
    async def get_balance(self, address: Optional[str] = None) -> Decimal:
        """
        Get ETH balance on Arbitrum.
        
        Args:
            address: Address to check (default: wallet address)
        
        Returns:
            Balance in ETH
        """
        target = address or self.wallet_address
        balance_wei = await self.w3.eth.get_balance(target)
        return Decimal(self.w3.from_wei(balance_wei, "ether"))
    
    @retry_rpc
    async def get_transaction_count(self, address: Optional[str] = None) -> int:
        """
        Get transaction nonce for an address.
        
        Args:
            address: Address to check (default: wallet address)
        
        Returns:
            Transaction count (next nonce)
        """
        target = address or self.wallet_address
        return await self.w3.eth.get_transaction_count(target)
    
    @retry_rpc
    async def get_gas_price(self) -> int:
        """Get current gas price in wei."""
        return await self.w3.eth.gas_price
    
    @retry_rpc
    async def estimate_gas(self, tx_params: TxParams) -> int:
        """Estimate gas for a transaction."""
        return await self.w3.eth.estimate_gas(tx_params)
    
    def sign_transaction(self, tx_params: TxParams) -> SignedTransaction:
        """
        Sign a transaction.
        
        Args:
            tx_params: Transaction parameters
        
        Returns:
            Signed transaction
        """
        signed = self.account.sign_transaction(tx_params)
        logger.info(
            "transaction_signed",
            tx_hash=signed.hash.hex(),
            from_address=self.wallet_address,
        )
        return signed
    
    @retry_rpc
    async def send_raw_transaction(self, signed_tx: SignedTransaction) -> str:
        """
        Send a signed raw transaction.
        
        Args:
            signed_tx: Signed transaction object
        
        Returns:
            Transaction hash
        """
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        tx_hash_hex = tx_hash.hex()
        
        logger.info("transaction_sent", tx_hash=tx_hash_hex, rpc_url=self.rpc_url)
        
        return tx_hash_hex
    
    @retry_rpc
    async def get_transaction_receipt(self, tx_hash: str) -> Optional[TxReceipt]:
        """
        Get transaction receipt.
        
        Args:
            tx_hash: Transaction hash
        
        Returns:
            Transaction receipt or None if pending
        """
        return await self.w3.eth.get_transaction_receipt(tx_hash)
    
    @retry_rpc
    async def wait_for_transaction_receipt(
        self,
        tx_hash: str,
        timeout: float = 120,
        poll_latency: float = 0.5,
    ) -> TxReceipt:
        """
        Wait for transaction receipt.
        
        Args:
            tx_hash: Transaction hash
            timeout: Maximum wait time in seconds
            poll_latency: Seconds between polls
        
        Returns:
            Transaction receipt
        
        Raises:
            TimeoutError: If transaction not confirmed within timeout
        """
        import asyncio
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            receipt = await self.get_transaction_receipt(tx_hash)
            
            if receipt is not None:
                if receipt["status"] == 1:
                    return receipt
                else:
                    raise Exception(f"Transaction failed: {tx_hash}")
            
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Transaction not confirmed within {timeout}s: {tx_hash}")
            
            await asyncio.sleep(poll_latency)
    
    async def health_check(self) -> bool:
        """
        Quick health check for the RPC connection.
        
        Returns:
            True if healthy
        """
        try:
            block_number = await self.w3.eth.block_number
            return block_number > 0
        except Exception as e:
            logger.warning("arbitrum_health_check_failed", error=str(e))
            return False
    
    async def close(self):
        """Close the client connection."""
        await self.w3.provider.disconnect()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
