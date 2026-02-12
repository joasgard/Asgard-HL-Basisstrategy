"""
Asgard Position Manager.

High-level manager for opening and closing margin positions on Asgard Finance.
Combines market data, transaction building, and state machine for end-to-end
position management.
"""
import asyncio
import uuid
from dataclasses import dataclass
from typing import Optional

from shared.chain.solana import SolanaClient
from shared.config.assets import Asset, get_mint
from shared.config.settings import get_settings, get_risk_limits
from shared.models.common import Protocol, TransactionState
from shared.models.position import AsgardPosition, PositionState
from decimal import Decimal
from bot.state.state_machine import TransactionStateMachine
from shared.utils.logger import get_logger

from .client import AsgardClient
from .market_data import AsgardMarketData, NetCarryResult
from .transactions import AsgardTransactionBuilder, BuildResult, SignResult, SubmitResult

logger = get_logger(__name__)


@dataclass
class OpenPositionResult:
    """Result of opening a position."""
    success: bool
    position: Optional[AsgardPosition] = None
    intent_id: Optional[str] = None
    signature: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ClosePositionResult:
    """Result of closing a position."""
    success: bool
    signature: Optional[str] = None
    error: Optional[str] = None


@dataclass
class HealthStatus:
    """Health status of a position."""
    position_pda: str
    health_factor: float
    is_healthy: bool
    liquidation_proximity: float  # How close to liquidation (0-1)
    
    # Risk thresholds (from spec)
    WARNING_THRESHOLD = 0.20
    EMERGENCY_THRESHOLD = 0.10
    CRITICAL_THRESHOLD = 0.05
    
    @property
    def status(self) -> str:
        """Get human-readable status."""
        if self.health_factor <= self.CRITICAL_THRESHOLD:
            return "CRITICAL"
        elif self.health_factor <= self.EMERGENCY_THRESHOLD:
            return "EMERGENCY"
        elif self.health_factor <= self.WARNING_THRESHOLD:
            return "WARNING"
        return "HEALTHY"


class AsgardPositionManager:
    """
    High-level manager for Asgard margin positions.
    
    Responsibilities:
    - Open long positions with optimal protocol selection
    - Close positions with proper cleanup
    - Monitor position health
    - Handle transaction rebroadcasting for stuck transactions
    
    Usage:
        async with AsgardPositionManager() as manager:
            # Open position
            result = await manager.open_long_position(
                asset=Asset.SOL,
                collateral_usd=50000,
                leverage=3.0
            )
            
            # Monitor health
            health = await manager.monitor_health(result.position.position_pda)
            
            # Close position
            await manager.close_position(result.position.position_pda)
    """
    
    def __init__(
        self,
        client: Optional[AsgardClient] = None,
        market_data: Optional[AsgardMarketData] = None,
        tx_builder: Optional[AsgardTransactionBuilder] = None,
        solana_client: Optional[SolanaClient] = None,
        state_machine: Optional[TransactionStateMachine] = None,
        solana_wallet_address: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """
        Initialize position manager.

        Args:
            client: AsgardClient instance
            market_data: AsgardMarketData instance
            tx_builder: AsgardTransactionBuilder instance
            solana_client: SolanaClient for on-chain queries
            state_machine: TransactionStateMachine for persistence
            solana_wallet_address: Solana wallet address for this user.
                                  If None, falls back to settings.
            user_id: User ID for multi-tenant logging.
        """
        self.client = client or AsgardClient()
        self.market_data = market_data or AsgardMarketData(self.client)
        self.tx_builder = tx_builder
        self.solana_client = solana_client
        self.state_machine = state_machine or TransactionStateMachine()
        self.user_id = user_id

        settings = get_settings()
        self.solana_wallet_address = solana_wallet_address or settings.solana_wallet_address

        # Lazy initialization of tx_builder (needs wallet address)
        if self.tx_builder is None:
            if self.solana_wallet_address and settings.privy_app_id:
                self.tx_builder = AsgardTransactionBuilder(
                    client=self.client,
                    state_machine=self.state_machine,
                    wallet_address=self.solana_wallet_address,
                    user_id=self.user_id,
                )
            else:
                logger.warning("Solana wallet address or Privy not configured, transaction signing disabled")

        # Lazy initialization of solana_client
        if self.solana_client is None:
            if settings.solana_rpc_url:
                self.solana_client = SolanaClient(
                    rpc_url=settings.solana_rpc_url,
                )
    
    async def __aenter__(self) -> "AsgardPositionManager":
        """Async context manager entry."""
        if not self.client._session or self.client._session.closed:
            await self.client._init_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.client.close()
        if self.solana_client:
            await self.solana_client.close()
    
    async def open_long_position(
        self,
        asset: Asset,
        collateral_usd: float,
        leverage: float = 3.0,
        protocol: Optional[Protocol] = None,
    ) -> OpenPositionResult:
        """
        Open a leveraged long position on Asgard.
        
        Args:
            asset: Asset to use as collateral (SOL, jitoSOL, jupSOL, INF)
            collateral_usd: Amount of collateral in USD
            leverage: Leverage multiplier (default 3.0x, max 4.0x)
            protocol: Specific protocol to use. If None, selects best.
            
        Returns:
            OpenPositionResult with position details
        """
        intent_id = str(uuid.uuid4())
        
        try:
            # Validate leverage
            risk_limits = get_risk_limits()
            max_leverage = risk_limits.get("max_leverage", 4.0)
            if leverage > max_leverage:
                raise ValueError(f"Leverage {leverage}x exceeds maximum {max_leverage}x")
            
            # Get asset mint
            collateral_mint = get_mint(asset)
            if not collateral_mint:
                raise ValueError(f"Unknown asset: {asset}")
            
            # USDC mint for borrowing
            usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            
            # Calculate position details
            position_size = collateral_usd * leverage
            borrow_amount = collateral_usd * (leverage - 1)
            
            logger.info(
                f"Opening position: asset={asset.value}, collateral=${collateral_usd:,.0f}, "
                f"leverage={leverage}x, position_size=${position_size:,.0f}"
            )
            
            # Select protocol if not specified
            if protocol is None:
                best_protocol = await self.market_data.select_best_protocol(
                    asset=asset,
                    size_usd=collateral_usd,
                    leverage=leverage,
                )
                
                if best_protocol is None:
                    return OpenPositionResult(
                        success=False,
                        error="No suitable protocol found with sufficient capacity"
                    )
                
                protocol = best_protocol.protocol
                logger.info(f"Selected protocol: {protocol.name}")
            
            # Check if transaction builder is available
            if self.tx_builder is None:
                return OpenPositionResult(
                    success=False,
                    error="Transaction builder not available (missing private key)"
                )
            
            # Step 1: Build transaction
            build_result = await self.tx_builder.build_create_position(
                intent_id=intent_id,
                asset=asset,
                protocol=protocol,
                collateral_amount=collateral_usd,
                borrow_amount=borrow_amount,
                collateral_mint=collateral_mint,
                borrow_mint=usdc_mint,
            )
            
            # Step 2: Sign transaction
            sign_result = await self.tx_builder.sign_transaction(
                intent_id=intent_id,
                unsigned_tx=build_result.unsigned_tx,
            )
            
            # Step 3: Submit transaction
            submit_result = await self.tx_builder.submit_transaction(
                intent_id=intent_id,
                signed_tx=sign_result.signed_tx,
            )
            
            if not submit_result.confirmed:
                # Transaction submitted but not yet confirmed
                # Return with pending status
                return OpenPositionResult(
                    success=True,  # Submission succeeded
                    intent_id=intent_id,
                    signature=submit_result.signature,
                    error="Transaction submitted but pending confirmation"
                )
            
            # Create position object
            position = AsgardPosition(
                position_pda=submit_result.signature[:32],  # Placeholder - real PDA from API
                intent_id=intent_id,
                asset=asset,
                protocol=protocol,
                collateral_usd=Decimal(str(collateral_usd)),
                position_size_usd=Decimal(str(position_size)),
                token_a_amount=Decimal(str(collateral_usd)),  # Approximate
                token_b_borrowed=Decimal(str(borrow_amount)),
                entry_price_token_a=Decimal("0"),  # Will be filled from actual fill
                current_health_factor=Decimal("0.20"),  # Initial health factor
                current_token_a_price=Decimal("0"),  # Will be updated
                leverage=Decimal(str(leverage)),
                create_tx_signature=submit_result.signature,
            )
            
            logger.info(
                f"Position opened: intent={intent_id}, signature={submit_result.signature[:16]}..."
            )
            
            return OpenPositionResult(
                success=True,
                position=position,
                intent_id=intent_id,
                signature=submit_result.signature,
            )
            
        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            return OpenPositionResult(
                success=False,
                intent_id=intent_id,
                error=str(e)
            )
    
    async def close_position(
        self,
        position_pda: str,
    ) -> ClosePositionResult:
        """
        Close a margin position.
        
        Args:
            position_pda: Position PDA address to close
            
        Returns:
            ClosePositionResult with transaction details
        """
        intent_id = str(uuid.uuid4())
        
        try:
            logger.info(f"Closing position: {position_pda}")
            
            if self.tx_builder is None:
                return ClosePositionResult(
                    success=False,
                    error="Transaction builder not available"
                )
            
            # Step 1: Build close transaction
            build_result = await self.tx_builder.build_close_position(
                intent_id=intent_id,
                position_pda=position_pda,
            )
            
            # Step 2: Sign transaction
            sign_result = await self.tx_builder.sign_transaction(
                intent_id=intent_id,
                unsigned_tx=build_result.unsigned_tx,
            )
            
            # Step 3: Submit close transaction
            submit_result = await self.tx_builder.submit_close_transaction(
                intent_id=intent_id,
                signed_tx=sign_result.signed_tx,
            )
            
            logger.info(
                f"Position closed: position={position_pda}, signature={submit_result.signature[:16]}..."
            )
            
            return ClosePositionResult(
                success=True,
                signature=submit_result.signature,
            )
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return ClosePositionResult(
                success=False,
                error=str(e)
            )
    
    async def get_position_state(self, position_pda: str) -> Optional[PositionState]:
        """
        Get current state of a position.
        
        Args:
            position_pda: Position PDA address
            
        Returns:
            PositionState if found, None otherwise
        """
        try:
            response = await self.client._post("/refresh-positions", json={
                "positionPdas": [position_pda]
            })
            
            positions = response.get("positions", [])
            if not positions:
                return None
            
            pos_data = positions[0]
            return PositionState(
                position_pda=position_pda,
                collateral_amount=pos_data.get("collateralAmount", 0),
                borrow_amount=pos_data.get("borrowAmount", 0),
                health_factor=pos_data.get("healthFactor", 0),
            )
            
        except Exception as e:
            logger.error(f"Failed to get position state: {e}")
            return None
    
    async def monitor_health(self, position_pda: str) -> Optional[HealthStatus]:
        """
        Monitor position health factor.
        
        Args:
            position_pda: Position PDA address
            
        Returns:
            HealthStatus with health metrics
        """
        position_state = await self.get_position_state(position_pda)
        
        if position_state is None:
            logger.warning(f"Position not found: {position_pda}")
            return None
        
        health_factor = position_state.health_factor
        
        # Calculate liquidation proximity
        # 0 = liquidated, 1 = infinite health
        liquidation_proximity = max(0.0, 1.0 - (health_factor / HealthStatus.WARNING_THRESHOLD))
        
        is_healthy = health_factor > HealthStatus.WARNING_THRESHOLD
        
        status = HealthStatus(
            position_pda=position_pda,
            health_factor=health_factor,
            is_healthy=is_healthy,
            liquidation_proximity=liquidation_proximity,
        )
        
        # Log warnings
        if status.status == "CRITICAL":
            logger.critical(f"CRITICAL health factor: {health_factor:.2%} for position {position_pda}")
        elif status.status == "EMERGENCY":
            logger.error(f"EMERGENCY health factor: {health_factor:.2%} for position {position_pda}")
        elif status.status == "WARNING":
            logger.warning(f"WARNING health factor: {health_factor:.2%} for position {position_pda}")
        
        return status
    
    async def rebroadcast_if_stuck(
        self,
        intent_id: str,
        timeout_seconds: int = 15,  # noqa: F841 - TODO: Implement timeout
    ) -> bool:
        """
        Rebroadcast a transaction if it's stuck without confirmation.
        
        Per spec 5.1: If transaction stuck >15s without confirmation:
        1. Query getSignatureStatuses to check if landed
        2. If landed: Update state and proceed
        3. If not landed: Assume dropped, rebuild with fresh blockhash
        4. Re-sign with same key (new signature, same intent)
        5. Submit new transaction
        
        Args:
            intent_id: Transaction intent ID
            timeout_seconds: Timeout before considering stuck (default 15s)
            
        Returns:
            True if successfully rebroadcast or confirmed
        """
        # Get current state
        tx_state = self.state_machine.get_state(intent_id)
        
        if tx_state is None:
            logger.warning(f"Transaction not found: {intent_id}")
            return False
        
        if tx_state.state == TransactionState.CONFIRMED:
            logger.debug(f"Transaction already confirmed: {intent_id}")
            return True
        
        if tx_state.state not in (TransactionState.SIGNED, TransactionState.SUBMITTED):
            logger.warning(f"Transaction in wrong state for rebroadcast: {tx_state.state}")
            return False
        
        if not tx_state.signature:
            logger.error(f"Transaction has no signature: {intent_id}")
            return False
        
        logger.info(f"Checking if transaction is stuck: {intent_id}")
        
        # Check if transaction landed on-chain
        if self.solana_client:
            try:
                status = await self.solana_client.get_signature_status(tx_state.signature)
                
                if status and status.get("confirmed"):
                    # Transaction landed! Update state
                    self.state_machine.transition(
                        intent_id,
                        TransactionState.CONFIRMED,
                        signature=tx_state.signature,
                    )
                    logger.info(f"Transaction confirmed on-chain: {intent_id}")
                    return True
                
                # Not confirmed - check if dropped
                if status and status.get("err"):
                    logger.error(f"Transaction failed: {status.get('err')}")
                    self.state_machine.transition(
                        intent_id,
                        TransactionState.FAILED,
                        error=str(status.get("err"))
                    )
                    return False
                    
            except Exception as e:
                logger.warning(f"Failed to check signature status: {e}")
        
        # Transaction appears stuck - need to rebuild
        logger.info(f"Transaction stuck, rebroadcasting: {intent_id}")
        
        # TODO(Phase 5.3): Implement rebuild with fresh blockhash
        # This requires storing the original transaction details in metadata
        # Then: 1) Rebuild with /create-position, 2) Re-sign, 3) Re-submit
        # See spec section 5.1: Transaction Rebroadcasting
        
        logger.warning(f"Rebroadcast not fully implemented yet for: {intent_id}")
        return False
