"""
Pause Controller and Circuit Breakers for Asgard Basis.

Provides emergency pause/resume functionality and automatic circuit breakers
to halt trading when risk conditions are detected.

Circuit Breakers (from spec 8.4):
| Condition | Action | Cooldown |
|-----------|--------|----------|
| Asgard HF < 10% for 20s | Emergency close both | Immediate |
| Hyperliquid MF < 20% for 20s | Close short, then long | Immediate |
| Total APY < 0 | Evaluate exit cost vs bleed | Immediate |
| Price deviation > 2% | Pause new entries | 30 min |
| LST premium > 5% or discount > 2% | Emergency close | Immediate |
| Solana gas > 0.01 SOL | Pause Asgard ops | Until < 0.005 |
| Chain outage detected | Close reachable chain first | Immediate |

Admin Controls:
- pause(): Emergency stop all operations (requires API key)
- resume(): Resume operations (requires API key)
- check_paused(): Check if operations are paused
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, List, Callable, Any

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class CircuitBreakerType(Enum):
    """Types of circuit breakers."""
    ASGARD_HEALTH = "asgard_health"
    HYPERLIQUID_MARGIN = "hyperliquid_margin"
    NEGATIVE_APY = "negative_apy"
    PRICE_DEVIATION = "price_deviation"
    LST_DEPEG = "lst_depeg"
    HIGH_GAS = "high_gas"
    CHAIN_OUTAGE = "chain_outage"
    MANUAL = "manual"


class PauseScope(Enum):
    """Scope of pause operation."""
    ALL = "all"
    ENTRY = "entry"      # No new positions
    EXIT = "exit"        # No position closures
    ASGARD = "asgard"    # Solana operations only
    HYPERLIQUID = "hyperliquid"  # Arbitrum operations only


@dataclass
class CircuitBreakerEvent:
    """Record of a circuit breaker trigger."""
    
    breaker_type: CircuitBreakerType
    triggered_at: datetime
    reason: str
    scope: PauseScope
    
    # Auto-recovery info
    auto_recovery: bool
    recovery_time: Optional[datetime] = None
    cooldown_seconds: Optional[int] = None
    
    # Resolution
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None  # 'auto' or 'manual'
    
    @property
    def is_active(self) -> bool:
        """True if circuit breaker is still active."""
        return self.resolved_at is None
    
    @property
    def age_seconds(self) -> float:
        """Age of the circuit breaker in seconds."""
        return (datetime.utcnow() - self.triggered_at).total_seconds()


@dataclass
class PauseState:
    """Current pause state."""
    
    paused: bool
    scope: PauseScope
    reason: Optional[str] = None
    paused_at: Optional[datetime] = None
    paused_by: Optional[str] = None  # 'admin' or 'circuit_breaker'
    
    # Active circuit breakers
    active_breakers: List[CircuitBreakerType] = field(default_factory=list)


class PauseController:
    """
    Controls pausing and circuit breakers for the trading bot.
    
    Provides both manual admin controls and automatic circuit breakers
    that halt trading when risk conditions are detected.
    
    Manual Controls:
    - pause(api_key, reason): Admin-initiated pause
    - resume(api_key): Resume from pause
    - check_paused(): Check if paused
    - assert_not_paused(): Raise if paused (for use in operations)
    
    Circuit Breakers:
    - trigger_circuit_breaker(type, reason, scope): Auto-trigger
    - resolve_circuit_breaker(type): Resolve a breaker
    - get_active_breakers(): List active breakers
    
    Usage:
        controller = PauseController(admin_api_key="secret_key")
        
        # Manual pause
        controller.pause("secret_key", "Emergency maintenance")
        
        # Check before operation
        if not controller.check_paused():
            await open_position()
        
        # Circuit breaker auto-trigger
        if health_factor < 0.10:
            controller.trigger_circuit_breaker(
                CircuitBreakerType.ASGARD_HEALTH,
                "HF below 10%",
                PauseScope.ALL
            )
    
    Args:
        admin_api_key: API key for admin operations
        default_cooldown_seconds: Default cooldown for circuit breakers (default: 1800)
    """
    
    # Default cooldowns for circuit breakers (from spec 8.4)
    DEFAULT_COOLDOWNS: Dict[CircuitBreakerType, int] = {
        CircuitBreakerType.ASGARD_HEALTH: 0,       # Immediate, requires manual reset
        CircuitBreakerType.HYPERLIQUID_MARGIN: 0,  # Immediate, requires manual reset
        CircuitBreakerType.NEGATIVE_APY: 0,        # Immediate
        CircuitBreakerType.PRICE_DEVIATION: 1800,  # 30 minutes
        CircuitBreakerType.LST_DEPEG: 0,           # Immediate
        CircuitBreakerType.HIGH_GAS: 0,            # Until condition clears
        CircuitBreakerType.CHAIN_OUTAGE: 0,        # Immediate
        CircuitBreakerType.MANUAL: 0,              # Until manually resumed
    }
    
    # High gas threshold (from spec 8.4)
    HIGH_GAS_THRESHOLD_SOL = Decimal("0.01")
    GAS_RECOVERY_THRESHOLD_SOL = Decimal("0.005")
    
    def __init__(
        self,
        admin_api_key: str,
        default_cooldown_seconds: int = 1800,
    ):
        self._admin_api_key = admin_api_key
        self._default_cooldown = default_cooldown_seconds
        
        # Pause state
        self._paused = False
        self._pause_scope: PauseScope = PauseScope.ALL
        self._pause_reason: Optional[str] = None
        self._paused_at: Optional[datetime] = None
        self._paused_by: Optional[str] = None
        
        # Circuit breaker history
        self._circuit_breakers: List[CircuitBreakerEvent] = []
        
        # Callbacks
        self._pause_callbacks: List[Callable[[PauseState], None]] = []
        self._resume_callbacks: List[Callable[[], None]] = []
        
        logger.info("PauseController initialized")
    
    def pause(
        self,
        api_key: str,
        reason: str,
        scope: PauseScope = PauseScope.ALL,
    ) -> bool:
        """
        Manually pause operations (requires admin API key).
        
        Args:
            api_key: Admin API key for authentication
            reason: Reason for pause
            scope: Scope of pause (default: ALL)
            
        Returns:
            True if paused successfully
            
        Raises:
            ValueError: If API key is invalid
        """
        if api_key != self._admin_api_key:
            logger.warning("Invalid API key for pause operation")
            raise ValueError("Invalid API key")
        
        self._paused = True
        self._pause_scope = scope
        self._pause_reason = reason
        self._paused_at = datetime.utcnow()
        self._paused_by = "admin"
        
        # Create circuit breaker event for manual pause
        breaker = CircuitBreakerEvent(
            breaker_type=CircuitBreakerType.MANUAL,
            triggered_at=self._paused_at,
            reason=reason,
            scope=scope,
            auto_recovery=False,
        )
        self._circuit_breakers.append(breaker)
        
        logger.warning(f"Operations PAUSED by admin: {reason} (scope: {scope.value})")
        
        # Trigger callbacks
        state = self.get_pause_state()
        for callback in self._pause_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"Pause callback error: {e}")
        
        return True
    
    def resume(self, api_key: str) -> bool:
        """
        Resume operations (requires admin API key).
        
        Args:
            api_key: Admin API key for authentication
            
        Returns:
            True if resumed successfully
            
        Raises:
            ValueError: If API key is invalid
        """
        if api_key != self._admin_api_key:
            logger.warning("Invalid API key for resume operation")
            raise ValueError("Invalid API key")
        
        was_paused = self._paused
        
        self._paused = False
        self._pause_scope = PauseScope.ALL
        self._pause_reason = None
        self._paused_at = None
        self._paused_by = None
        
        # Resolve manual circuit breaker
        for breaker in self._circuit_breakers:
            if breaker.breaker_type == CircuitBreakerType.MANUAL and breaker.is_active:
                breaker.resolved_at = datetime.utcnow()
                breaker.resolved_by = "manual"
        
        if was_paused:
            logger.info("Operations RESUMED by admin")
            
            # Trigger callbacks
            for callback in self._resume_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Resume callback error: {e}")
        
        return True
    
    def check_paused(self, scope: Optional[PauseScope] = None) -> bool:
        """
        Check if operations are paused.
        
        Args:
            scope: Specific scope to check (checks all if None)
            
        Returns:
            True if paused for the given scope
        """
        if not self._paused:
            return False
        
        if scope is None:
            return self._paused
        
        # Check if the current pause scope affects the requested scope
        if self._pause_scope == PauseScope.ALL:
            return True
        
        return scope == self._pause_scope
    
    def assert_not_paused(self, scope: Optional[PauseScope] = None):
        """
        Raise exception if paused (for use before operations).
        
        Args:
            scope: Scope to check
            
        Raises:
            RuntimeError: If paused for the given scope
        """
        if self.check_paused(scope):
            raise RuntimeError(
                f"Operations paused ({self._pause_scope.value}): {self._pause_reason}"
            )
    
    def can_execute(self, operation: str) -> bool:
        """
        Check if a specific operation can be executed.
        
        Args:
            operation: Operation type ('entry', 'exit', 'asgard', 'hyperliquid')
            
        Returns:
            True if operation is allowed
        """
        if not self._paused:
            return True
        
        scope_map = {
            'entry': [PauseScope.ALL, PauseScope.ENTRY],
            'exit': [PauseScope.ALL, PauseScope.EXIT],
            'asgard': [PauseScope.ALL, PauseScope.ASGARD],
            'hyperliquid': [PauseScope.ALL, PauseScope.HYPERLIQUID],
        }
        
        blocked_scopes = scope_map.get(operation, [PauseScope.ALL])
        return self._pause_scope not in blocked_scopes
    
    def trigger_circuit_breaker(
        self,
        breaker_type: CircuitBreakerType,
        reason: str,
        scope: PauseScope = PauseScope.ALL,
        auto_recovery: bool = False,
        cooldown_seconds: Optional[int] = None,
    ) -> CircuitBreakerEvent:
        """
        Trigger a circuit breaker.
        
        Args:
            breaker_type: Type of circuit breaker
            reason: Reason for trigger
            scope: Scope of pause
            auto_recovery: Whether to auto-recover after cooldown
            cooldown_seconds: Cooldown period (uses default if None)
            
        Returns:
            CircuitBreakerEvent record
        """
        # Use default cooldown if not specified
        if cooldown_seconds is None:
            cooldown_seconds = self.DEFAULT_COOLDOWNS.get(breaker_type, self._default_cooldown)
        
        now = datetime.utcnow()
        recovery_time = None
        if auto_recovery and cooldown_seconds > 0:
            recovery_time = now + timedelta(seconds=cooldown_seconds)
        
        event = CircuitBreakerEvent(
            breaker_type=breaker_type,
            triggered_at=now,
            reason=reason,
            scope=scope,
            auto_recovery=auto_recovery,
            recovery_time=recovery_time,
            cooldown_seconds=cooldown_seconds,
        )
        
        self._circuit_breakers.append(event)
        
        # Set pause state
        self._paused = True
        self._pause_scope = scope
        self._pause_reason = f"Circuit breaker: {breaker_type.value} - {reason}"
        self._paused_at = now
        self._paused_by = "circuit_breaker"
        
        logger.error(
            f"CIRCUIT BREAKER TRIGGERED: {breaker_type.value} - {reason} "
            f"(scope: {scope.value}, auto_recovery: {auto_recovery})"
        )
        
        # Trigger callbacks
        state = self.get_pause_state()
        for callback in self._pause_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"Pause callback error: {e}")
        
        return event
    
    def resolve_circuit_breaker(
        self,
        breaker_type: CircuitBreakerType,
        resolved_by: str = "manual",
    ) -> bool:
        """
        Resolve a circuit breaker.
        
        Args:
            breaker_type: Type to resolve
            resolved_by: Who resolved it ('auto' or 'manual')
            
        Returns:
            True if resolved, False if not found or already resolved
        """
        resolved_any = False
        
        for breaker in self._circuit_breakers:
            if breaker.breaker_type == breaker_type and breaker.is_active:
                breaker.resolved_at = datetime.utcnow()
                breaker.resolved_by = resolved_by
                resolved_any = True
                logger.info(f"Circuit breaker resolved: {breaker_type.value} ({resolved_by})")
        
        # Check if all breakers are resolved
        if resolved_any and not self._has_active_breakers():
            self._paused = False
            self._pause_scope = PauseScope.ALL
            self._pause_reason = None
            
            # Trigger resume callbacks
            for callback in self._resume_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Resume callback error: {e}")
        
        return resolved_any
    
    def check_and_recover(self) -> List[CircuitBreakerType]:
        """
        Check for auto-recovery conditions and recover if met.
        
        Returns:
            List of breaker types that were auto-recovered
        """
        recovered = []
        now = datetime.utcnow()
        
        for breaker in self._circuit_breakers:
            if breaker.is_active and breaker.auto_recovery:
                if breaker.recovery_time and now >= breaker.recovery_time:
                    self.resolve_circuit_breaker(breaker.breaker_type, "auto")
                    recovered.append(breaker.breaker_type)
        
        return recovered
    
    def get_active_breakers(self) -> List[CircuitBreakerEvent]:
        """Get list of active circuit breakers."""
        return [b for b in self._circuit_breakers if b.is_active]
    
    def _has_active_breakers(self) -> bool:
        """Check if any circuit breakers are active."""
        return any(b.is_active for b in self._circuit_breakers)
    
    def get_pause_state(self) -> PauseState:
        """Get current pause state."""
        return PauseState(
            paused=self._paused,
            scope=self._pause_scope,
            reason=self._pause_reason,
            paused_at=self._paused_at,
            paused_by=self._paused_by,
            active_breakers=[b.breaker_type for b in self.get_active_breakers()],
        )
    
    def get_circuit_breaker_history(
        self,
        breaker_type: Optional[CircuitBreakerType] = None,
    ) -> List[CircuitBreakerEvent]:
        """
        Get circuit breaker history.
        
        Args:
            breaker_type: Filter by type (all if None)
            
        Returns:
            List of circuit breaker events
        """
        if breaker_type:
            return [b for b in self._circuit_breakers if b.breaker_type == breaker_type]
        return self._circuit_breakers.copy()
    
    def add_pause_callback(self, callback: Callable[[PauseState], None]):
        """Add callback for pause events."""
        self._pause_callbacks.append(callback)
    
    def add_resume_callback(self, callback: Callable[[], None]):
        """Add callback for resume events."""
        self._resume_callbacks.append(callback)
    
    async def check_user_paused(self, user_id: str, db) -> bool:
        """Check if a specific user is paused (global OR per-user).

        Args:
            user_id: Privy user ID.
            db: Database instance.

        Returns:
            True if the user (or global) is paused.
        """
        # Global pause takes precedence
        if self._paused:
            return True

        # Per-user pause from DB
        row = await db.fetchone(
            "SELECT paused_at FROM users WHERE id = $1",
            (user_id,),
        )
        return row is not None and row.get("paused_at") is not None

    async def pause_user(self, user_id: str, reason: str, db) -> bool:
        """Pause a specific user.

        Args:
            user_id: Privy user ID.
            reason: Reason for pause.
            db: Database instance.

        Returns:
            True if paused successfully.
        """
        await db.execute(
            "UPDATE users SET paused_at = NOW(), paused_reason = $1 WHERE id = $2",
            (reason, user_id),
        )
        logger.warning("user_paused", user_id=user_id, reason=reason)
        return True

    async def resume_user(self, user_id: str, db) -> bool:
        """Resume a specific user.

        Args:
            user_id: Privy user ID.
            db: Database instance.

        Returns:
            True if resumed successfully.
        """
        await db.execute(
            "UPDATE users SET paused_at = NULL, paused_reason = NULL WHERE id = $1",
            (user_id,),
        )
        logger.info("user_resumed", user_id=user_id)
        return True

    def is_high_gas(self, current_gas_sol: Decimal) -> bool:
        """Check if gas price is above threshold."""
        return current_gas_sol > self.HIGH_GAS_THRESHOLD_SOL
    
    def should_recover_from_high_gas(self, current_gas_sol: Decimal) -> bool:
        """Check if gas has dropped below recovery threshold."""
        return current_gas_sol < self.GAS_RECOVERY_THRESHOLD_SOL
