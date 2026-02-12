"""
Main Bot Runner for Asgard Basis.

This is the main orchestration layer that coordinates all components:
- Asgard (Solana) for long positions
- Hyperliquid (Arbitrum) for short positions
- Opportunity detection and execution
- Position monitoring and risk management
- State persistence and recovery

The bot runs a main event loop with aligned 30-second polling for both chains.

Usage:
    bot = DeltaNeutralBot()
    await bot.run()  # Start main loop
    
    # Or with context manager
    async with DeltaNeutralBot() as bot:
        await bot.run()

Main Loop:
    1. Initialize all clients and components
    2. Recover state from previous run (if any)
    3. Start monitoring and scanning loops
    4. On opportunity detected:
       - Run pre-flight checks
       - Open Asgard long first
       - Open Hyperliquid short
       - Validate fills
       - Save position state
    5. On exit trigger:
       - Close Hyperliquid short first
       - Close Asgard long
       - Update state
"""
import asyncio
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any

from shared.chain.solana import SolanaClient
from shared.chain.arbitrum import ArbitrumClient
from shared.config.assets import Asset
from shared.config.settings import get_settings
from bot.core.kill_switch import KillSwitchMonitor, KillSwitchTrigger
from bot.core.opportunity_detector import OpportunityDetector
from bot.core.pause_controller import PauseController, PauseScope, CircuitBreakerType
from bot.core.position_manager import PositionManager
from bot.core.position_sizer import PositionSizer
from bot.core.risk_engine import RiskEngine, ExitDecision, ExitReason
from shared.models.opportunity import ArbitrageOpportunity
from shared.models.position import CombinedPosition
from bot.state.persistence import StatePersistence
from shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BotStats:
    """Bot runtime statistics."""
    
    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    
    # Counters
    opportunities_found: int = 0
    positions_opened: int = 0
    positions_closed: int = 0
    
    # Errors
    errors: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def uptime_seconds(self) -> float:
        """Calculate uptime in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.stop_time or datetime.utcnow()
        return (end - self.start_time).total_seconds()
    
    @property
    def uptime_formatted(self) -> str:
        """Get formatted uptime string."""
        seconds = int(self.uptime_seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@dataclass
class BotConfig:
    """Bot configuration."""
    
    # Timing
    poll_interval_seconds: int = 30
    scan_interval_seconds: int = 60
    
    # Execution
    max_concurrent_positions: int = 5
    min_opportunity_apy: Decimal = Decimal("0.01")  # 1%
    
    # Risk
    enable_auto_exit: bool = True
    enable_circuit_breakers: bool = True
    
    # Admin
    admin_api_key: Optional[str] = None


class DeltaNeutralBot:
    """
    Main bot for Asgard Basis funding rate arbitrage.
    
    This class orchestrates the entire trading strategy:
    1. Detects arbitrage opportunities
    2. Opens delta-neutral positions
    3. Monitors positions for risk
    4. Exits positions when conditions warrant
    
    The bot uses a 30-second aligned polling interval for both chains
    to ensure synchronized monitoring.
    
    Usage:
        config = BotConfig(admin_api_key="secret")
        bot = DeltaNeutralBot(config)
        
        # Run until stopped
        await bot.run()
        
        # Or with timeout
        await bot.run_for(duration_seconds=3600)  # 1 hour
    
    Args:
        config: Bot configuration
        state_persistence: State persistence layer (created if None)
    """
    
    # Timing constants
    POLL_INTERVAL_SECONDS = 30
    SCAN_INTERVAL_SECONDS = 60
    MAX_SINGLE_LEG_EXPOSURE_SECONDS = 120
    
    def __init__(
        self,
        config: Optional[BotConfig] = None,
        state_persistence: Optional[StatePersistence] = None,
    ):
        self.config = config or BotConfig()
        self._state = state_persistence
        
        # Components (initialized in setup)
        self._opportunity_detector: Optional[OpportunityDetector] = None
        self._position_manager: Optional[PositionManager] = None
        self._risk_engine: Optional[RiskEngine] = None
        self._pause_controller: Optional[PauseController] = None
        self._position_sizer: Optional[PositionSizer] = None
        self._solana_client: Optional[SolanaClient] = None
        self._arbitrum_client: Optional[ArbitrumClient] = None
        self._kill_switch: Optional[KillSwitchMonitor] = None
        
        # State
        self._running = False
        self._shutdown_event = asyncio.Event()
        # User-scoped positions: user_id -> {position_id -> CombinedPosition}
        self._positions: Dict[str, Dict[str, CombinedPosition]] = {}
        self._stats = BotStats()
        
        # Callbacks
        self._opportunity_callbacks: List[Callable[[ArbitrageOpportunity], None]] = []
        self._position_opened_callbacks: List[Callable[[CombinedPosition], None]] = []
        self._position_closed_callbacks: List[Callable[[CombinedPosition, str], None]] = []
        
        logger.info("DeltaNeutralBot initialized")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.setup()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()
    
    async def setup(self):
        """Initialize all components."""
        logger.info("Setting up bot components...")
        
        # Initialize state persistence
        if self._state is None:
            self._state = StatePersistence()
        await self._state.setup()
        
        # Initialize clients
        self._solana_client = SolanaClient()
        self._arbitrum_client = ArbitrumClient()
        
        # Initialize core components
        self._risk_engine = RiskEngine()
        self._position_sizer = PositionSizer()
        
        # Initialize pause controller
        api_key = self.config.admin_api_key or get_settings().admin_api_key
        if not api_key:
            import warnings
            warnings.warn(
                "ADMIN_API_KEY not configured. Bot pause/resume controls will not work. "
                "Set ADMIN_API_KEY environment variable or admin_api_key in config.",
                RuntimeWarning
            )
            # Generate a temporary key for this session only (won't persist)
            import secrets
            api_key = f"temp_{secrets.token_hex(16)}"
        self._pause_controller = PauseController(admin_api_key=api_key)
        
        # Initialize position manager (with async context)
        self._position_manager = PositionManager(
            solana_client=self._solana_client,
            arbitrum_client=self._arbitrum_client,
        )
        await self._position_manager.__aenter__()
        
        # Initialize kill switch monitor
        self._kill_switch = KillSwitchMonitor()
        self._kill_switch.on_triggered(self._on_kill_switch_triggered)
        await self._kill_switch.start()
        
        # Initialize opportunity detector
        # Get the market data and oracle from position manager if available
        from bot.venues.asgard.market_data import AsgardMarketData
        from bot.venues.hyperliquid.funding_oracle import HyperliquidFundingOracle
        
        asgard_market_data = None
        hyperliquid_oracle = None
        
        if self._position_manager.asgard_manager:
            asgard_market_data = AsgardMarketData(self._position_manager.asgard_manager.client)
        if self._position_manager.hyperliquid_trader:
            hyperliquid_oracle = HyperliquidFundingOracle(self._position_manager.hyperliquid_trader.client)
        
        self._opportunity_detector = OpportunityDetector(
            asgard_market_data=asgard_market_data,
            hyperliquid_oracle=hyperliquid_oracle,
        )
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        logger.info("Bot setup complete")
    
    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down bot...")
        self._running = False
        self._shutdown_event.set()
        
        # Stop kill switch monitor
        if self._kill_switch:
            await self._kill_switch.stop()
        
        # Close position manager
        if self._position_manager:
            await self._position_manager.__aexit__(None, None, None)
        
        # Close state persistence
        if self._state:
            await self._state.close()
        
        self._stats.stop_time = datetime.utcnow()
        
        logger.info(f"Bot stopped. Uptime: {self._stats.uptime_formatted}")
    
    async def _on_kill_switch_triggered(self, reason: str):
        """
        Handle kill switch trigger.
        
        Pauses the bot (stops new positions) but does NOT close existing positions.
        Users must manually close positions via dashboard or API.
        """
        logger.critical("=" * 60)
        logger.critical("KILL SWITCH TRIGGERED - PAUSING BOT")
        logger.critical("=" * 60)
        
        # Pause the bot (stop new positions)
        api_key = self.config.admin_api_key or get_settings().admin_api_key
        if api_key and self._pause_controller:
            try:
                self._pause_controller.pause(
                    api_key=api_key,
                    reason=f"Kill switch: {reason}",
                    scope=PauseScope.ALL
                )
                
                # Get open positions count (all users)
                open_count = sum(len(user_positions) for user_positions in self._positions.values())
                
                logger.critical(f"Bot PAUSED. {open_count} positions STILL OPEN.")
                logger.critical("Positions remain open and continue earning funding.")
                logger.critical("Use dashboard or API to close positions manually.")
                logger.critical("=" * 60)
                
            except Exception as e:
                logger.error(f"Failed to pause bot after kill switch: {e}")
        else:
            logger.error("Cannot pause: admin_api_key or pause_controller not available")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    async def run(self):
        """
        Run the main bot loop.
        
        This starts the monitoring and scanning loops and runs until
        shutdown is triggered (via signal or shutdown()).
        """
        if self._running:
            raise RuntimeError("Bot is already running")
        
        self._running = True
        self._stats.start_time = datetime.utcnow()
        
        logger.info("Starting main bot loop...")
        
        # Recover state from previous run
        await self._recover_state()
        
        # Start main loops
        try:
            await asyncio.gather(
                self._monitor_loop(),
                self._scan_loop(),
            )
        except asyncio.CancelledError:
            logger.info("Main loops cancelled")
        finally:
            await self.shutdown()
    
    async def run_for(self, duration_seconds: float):
        """
        Run the bot for a specific duration.
        
        Args:
            duration_seconds: How long to run before auto-shutdown
        """
        logger.info(f"Running bot for {duration_seconds} seconds...")
        
        # Create shutdown task
        async def shutdown_timer():
            await asyncio.sleep(duration_seconds)
            logger.info("Auto-shutdown timer expired")
            await self.shutdown()
        
        # Run bot with timer
        await asyncio.gather(
            self.run(),
            shutdown_timer(),
            return_exceptions=True,
        )
    
    async def _monitor_loop(self):
        """
        Monitor loop - checks positions and risk conditions.
        
        Runs every POLL_INTERVAL_SECONDS (30 seconds aligned).
        """
        logger.info(f"Starting monitor loop ({self.POLL_INTERVAL_SECONDS}s interval)")
        
        while self._running:
            try:
                await self._monitor_cycle()
            except Exception as e:
                logger.error(f"Monitor cycle error: {e}")
                self._stats.errors.append({
                    "time": datetime.utcnow().isoformat(),
                    "cycle": "monitor",
                    "error": str(e),
                })
            
            # Wait for next interval
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.POLL_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass  # Normal - continue to next cycle
    
    async def _scan_loop(self):
        """
        Scan loop - looks for new opportunities.
        
        Runs every SCAN_INTERVAL_SECONDS (60 seconds).
        """
        logger.info(f"Starting scan loop ({self.SCAN_INTERVAL_SECONDS}s interval)")
        
        while self._running:
            try:
                await self._scan_cycle()
            except Exception as e:
                logger.error(f"Scan cycle error: {e}")
                self._stats.errors.append({
                    "time": datetime.utcnow().isoformat(),
                    "cycle": "scan",
                    "error": str(e),
                })
            
            # Wait for next interval
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.SCAN_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass  # Normal - continue to next cycle
    
    async def _monitor_cycle(self):
        """Single monitoring cycle."""
        # Check pause state
        if self._pause_controller.check_paused():
            logger.debug("Bot paused, skipping monitor cycle")
            return
        
        # Check circuit breakers
        self._pause_controller.check_and_recover()
        
        # Monitor each position (all users)
        all_positions = self.get_positions()
        for position_id, position in list(all_positions.items()):
            try:
                await self._monitor_position(position)
            except Exception as e:
                logger.error(f"Error monitoring position {position_id}: {e}")
    
    async def _monitor_position(self, position: CombinedPosition):
        """Monitor a single position for risk conditions."""
        # Get current state
        current_apy = await self._calculate_current_apy(position)
        
        # Evaluate exit triggers
        exit_decision = self._risk_engine.evaluate_exit_trigger(
            position,
            current_apy=current_apy,
            # Additional parameters would come from live data
        )
        
        if exit_decision.should_exit and self.config.enable_auto_exit:
            logger.warning(
                f"Exit trigger fired for {position.position_id}: "
                f"{exit_decision.reason.value}"
            )
            
            # Trigger circuit breaker for critical exits
            if exit_decision.reason in [
                ExitReason.ASGARD_HEALTH_FACTOR,
                ExitReason.HYPERLIQUID_MARGIN,
            ]:
                breaker_type = {
                    ExitReason.ASGARD_HEALTH_FACTOR: CircuitBreakerType.ASGARD_HEALTH,
                    ExitReason.HYPERLIQUID_MARGIN: CircuitBreakerType.HYPERLIQUID_MARGIN,
                }.get(exit_decision.reason)
                
                if breaker_type:
                    self._pause_controller.trigger_circuit_breaker(
                        breaker_type,
                        f"Exit triggered: {exit_decision.reason.value}",
                    )
            
            # Execute exit
            await self._execute_exit(position, exit_decision.reason.value)
    
    async def _scan_cycle(self):
        """Single scanning cycle."""
        # Check pause state (allow scanning when only entry paused)
        if self._pause_controller.check_paused(PauseScope.ALL):
            logger.debug("Bot fully paused, skipping scan cycle")
            return
        
        if not self._pause_controller.can_execute("entry"):
            logger.debug("Entry paused, skipping opportunity scan")
            return
        
        # Check if we have capacity for new positions (all users)
        total_positions = sum(len(user_positions) for user_positions in self._positions.values())
        if total_positions >= self.config.max_concurrent_positions:
            logger.debug("Max positions reached, skipping scan")
            return
        
        # Scan for opportunities
        logger.debug("Scanning for opportunities...")
        
        async with self._opportunity_detector as detector:
            opportunities = await detector.scan_opportunities()
        
        if not opportunities:
            logger.debug("No opportunities found")
            return
        
        self._stats.opportunities_found += len(opportunities)
        
        # Get best opportunity
        best = opportunities[0]
        
        # Check minimum APY
        if best.total_expected_apy < self.config.min_opportunity_apy:
            logger.debug(f"Best opportunity APY {best.total_expected_apy} below minimum")
            return
        
        logger.info(f"Found opportunity: {best.asset.value} @ {float(best.total_expected_apy):.2%} APY")
        
        # Trigger callbacks
        for callback in self._opportunity_callbacks:
            try:
                callback(best)
            except Exception as e:
                logger.error(f"Opportunity callback error: {e}")
        
        # Execute entry
        await self._execute_entry(best)
    
    async def _execute_entry(self, opportunity: ArbitrageOpportunity):
        """Execute position entry."""
        logger.info(f"Executing entry for {opportunity.asset.value}")
        
        try:
            # Get balances for sizing
            sol_balance = await self._solana_client.get_balance()
            hl_balance = await self._arbitrum_client.get_balance()
            
            # Calculate position size
            sizing_result = self._position_sizer.calculate_position_size(
                solana_balance_usd=Decimal(str(sol_balance)),
                hyperliquid_balance_usd=Decimal(str(hl_balance)),
            )
            
            if not sizing_result.success:
                logger.error(f"Position sizing failed: {sizing_result.error}")
                return
            
            # Open position
            result = await self._position_manager.open_position(
                opportunity=opportunity,
                capital_deployment=sizing_result.size,
            )
            
            if result.success and result.position:
                position = result.position
                # Store in user-scoped dict
                user_id = position.user_id or "default"
                if user_id not in self._positions:
                    self._positions[user_id] = {}
                self._positions[user_id][position.position_id] = position
                self._stats.positions_opened += 1
                
                # Save state
                await self._state.save_position(position)
                
                # Trigger callbacks
                for callback in self._position_opened_callbacks:
                    try:
                        callback(position)
                    except Exception as e:
                        logger.error(f"Position opened callback error: {e}")
                
                logger.info(f"Position opened: {position.position_id}")
            else:
                logger.error(f"Failed to open position: {result.error}")
                
        except Exception as e:
            logger.error(f"Entry execution error: {e}")
    
    async def _execute_exit(self, position: CombinedPosition, reason: str):
        """Execute position exit."""
        logger.info(f"Executing exit for {position.position_id}: {reason}")
        
        try:
            result = await self._position_manager.close_position(position.position_id)
            
            if result:
                user_id = position.user_id or "default"
                if user_id in self._positions and position.position_id in self._positions[user_id]:
                    del self._positions[user_id][position.position_id]
                    # Clean up empty user entries
                    if not self._positions[user_id]:
                        del self._positions[user_id]
                self._stats.positions_closed += 1
                
                # Update state
                await self._state.delete_position(position.position_id)
                await self._state.log_action({
                    "type": "position_closed",
                    "position_id": position.position_id,
                    "reason": reason,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
                # Trigger callbacks
                for callback in self._position_closed_callbacks:
                    try:
                        callback(position, reason)
                    except Exception as e:
                        logger.error(f"Position closed callback error: {e}")
                
                logger.info(f"Position closed: {position.position_id}")
            else:
                logger.error(f"Failed to close position: {position.position_id}")
                
        except Exception as e:
            logger.error(f"Exit execution error: {e}")
    
    async def _calculate_current_apy(self, position: CombinedPosition) -> Decimal:
        """Calculate current APY for a position."""
        # This would query live data
        # For now, return the expected APY from opportunity
        return position.expected_apy if hasattr(position, 'expected_apy') else Decimal("0")
    
    async def _recover_state(self, user_id: Optional[str] = None):
        """
        Recover state from previous run.
        
        Args:
            user_id: Optional user ID to filter recovery (None for all users)
        """
        logger.info("Recovering state from previous run...")
        
        positions = await self._state.load_positions(user_id=user_id)
        recovered_count = 0
        for position in positions:
            if not position.is_closed:
                pid = position.user_id or user_id or "default"
                if pid not in self._positions:
                    self._positions[pid] = {}
                self._positions[pid][position.position_id] = position
                recovered_count += 1
                logger.info(f"Recovered position: {position.position_id} (user: {pid})")
        
        total_positions = sum(len(user_positions) for user_positions in self._positions.values())
        logger.info(f"Recovered {total_positions} active positions")
    
    # Public API
    
    def get_stats(self) -> BotStats:
        """Get bot statistics."""
        return self._stats
    
    def get_positions(self, user_id: Optional[str] = None) -> Dict[str, CombinedPosition]:
        """
        Get current positions.
        
        Args:
            user_id: Filter by user ID (None for all positions in single-tenant mode)
            
        Returns:
            Dict of position_id -> CombinedPosition
        """
        if user_id:
            # Return positions for specific user
            return self._positions.get(user_id, {}).copy()
        else:
            # Flatten all positions (single-tenant compatibility)
            all_positions = {}
            for user_positions in self._positions.values():
                all_positions.update(user_positions)
            return all_positions
    
    def add_opportunity_callback(self, callback: Callable[[ArbitrageOpportunity], None]):
        """Add callback for opportunity detection."""
        self._opportunity_callbacks.append(callback)
    
    def add_position_opened_callback(self, callback: Callable[[CombinedPosition], None]):
        """Add callback for position opened."""
        self._position_opened_callbacks.append(callback)
    
    def add_position_closed_callback(self, callback: Callable[[CombinedPosition, str], None]):
        """Add callback for position closed."""
        self._position_closed_callbacks.append(callback)
    
    async def pause(self, api_key: str, reason: str, scope: PauseScope = PauseScope.ALL):
        """Pause bot operations."""
        return self._pause_controller.pause(api_key, reason, scope)
    
    async def resume(self, api_key: str):
        """Resume bot operations."""
        return self._pause_controller.resume(api_key)
