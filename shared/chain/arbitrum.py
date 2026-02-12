"""
Arbitrum/Web3 client with retry logic.
"""
from typing import Optional, Dict, Any, List
from decimal import Decimal

from web3 import AsyncWeb3
from web3.types import TxReceipt, TxParams
from shared.config.settings import get_settings
from shared.utils.logger import get_logger
from shared.utils.retry import retry_rpc

logger = get_logger(__name__)

# Default Arbitrum RPC
DEFAULT_ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"

# Native USDC on Arbitrum (NOT bridged USDC.e)
NATIVE_USDC_ARBITRUM = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"

# Minimal ERC-20 ABI for balance reads
ERC20_BALANCE_OF_ABI: List[Dict[str, Any]] = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    }
]


class ArbitrumClient:
    """
    Async Arbitrum/Web3 client with retry and error handling.
    
    Note: This client is for read-only operations. All signing is done via Privy.
    """
    
    def __init__(self, rpc_url: Optional[str] = None):
        self.settings = get_settings()
        self.rpc_url = rpc_url or self.settings.arbitrum_rpc_url or DEFAULT_ARBITRUM_RPC
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.rpc_url))
    
    @property
    def wallet_address(self) -> str:
        """Get wallet address from settings."""
        return self.settings.wallet_address
    
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
    
    @retry_rpc
    async def send_raw_transaction(self, signed_tx_bytes: bytes) -> str:
        """
        Send a signed raw transaction.

        Args:
            signed_tx_bytes: Raw signed transaction bytes

        Returns:
            Transaction hash
        """
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx_bytes)
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
    
    @retry_rpc
    async def get_erc20_balance(
        self,
        token_address: str,
        owner_address: Optional[str] = None,
        decimals: int = 18,
    ) -> Decimal:
        """
        Get ERC-20 token balance for an address.

        Args:
            token_address: ERC-20 contract address
            owner_address: Address to check (default: wallet address)
            decimals: Token decimals for conversion

        Returns:
            Token balance in human-readable units
        """
        target = owner_address or self.wallet_address
        checksum_token = self.w3.to_checksum_address(token_address)
        checksum_owner = self.w3.to_checksum_address(target)

        contract = self.w3.eth.contract(
            address=checksum_token,
            abi=ERC20_BALANCE_OF_ABI,
        )
        raw_balance = await contract.functions.balanceOf(checksum_owner).call()
        return Decimal(raw_balance) / Decimal(10 ** decimals)

    async def get_usdc_balance(self, address: Optional[str] = None) -> Decimal:
        """
        Get native USDC balance on Arbitrum.

        Args:
            address: Address to check (default: wallet address)

        Returns:
            USDC balance (human-readable, 6 decimals)
        """
        return await self.get_erc20_balance(
            token_address=NATIVE_USDC_ARBITRUM,
            owner_address=address,
            decimals=6,
        )

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
