"""
Chain health monitoring and outage detection.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum

from src.chain.solana import SolanaClient
from src.chain.arbitrum import ArbitrumClient
from src.models.common import Chain, ChainStatus
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ChainHealth:
    """Health status for a single chain."""
    chain: Chain
    status: ChainStatus
    last_check: datetime
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None
    error_message: Optional[str] = None
    latency_ms: Optional[float] = None


class OutageDetector:
    """
    Detects chain outages based on consecutive failures.
    
    Spec requirements:
    - MAX_CONSECUTIVE_FAILURES = 3
    - FAILURE_WINDOW_SECONDS = 15
    """
    
    MAX_CONSECUTIVE_FAILURES = 3
    FAILURE_WINDOW_SECONDS = 15
    CHECK_INTERVAL_SECONDS = 5
    
    def __init__(self):
        self._health_status: Dict[Chain, ChainHealth] = {}
        self._failure_timestamps: Dict[Chain, List[datetime]] = {}
        self._callbacks: List[Callable[[Chain, ChainStatus], None]] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Initialize status for both chains
        for chain in [Chain.SOLANA, Chain.ARBITRUM]:
            self._health_status[chain] = ChainHealth(
                chain=chain,
                status=ChainStatus.HEALTHY,
                last_check=datetime.utcnow(),
            )
            self._failure_timestamps[chain] = []
    
    def register_callback(self, callback: Callable[[Chain, ChainStatus], None]):
        """Register a callback for status changes."""
        self._callbacks.append(callback)
    
    def _notify_callbacks(self, chain: Chain, status: ChainStatus):
        """Notify all registered callbacks of status change."""
        for callback in self._callbacks:
            try:
                callback(chain, status)
            except Exception as e:
                logger.error("callback_error", chain=chain.value, error=str(e))
    
    async def check_chain_health(self, chain: Chain) -> ChainHealth:
        """
        Check health of a specific chain.
        
        Args:
            chain: Chain to check
        
        Returns:
            Updated ChainHealth
        """
        start_time = datetime.utcnow()
        
        try:
            if chain == Chain.SOLANA:
                async with SolanaClient() as client:
                    healthy = await client.health_check()
            else:  # ARBITRUM
                async with ArbitrumClient() as client:
                    healthy = await client.health_check()
            
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if healthy:
                return self._record_success(chain, latency)
            else:
                return self._record_failure(chain, "Health check returned false")
        
        except Exception as e:
            return self._record_failure(chain, str(e))
    
    def _record_success(self, chain: Chain, latency_ms: float) -> ChainHealth:
        """Record a successful health check."""
        old_status = self._health_status[chain].status
        
        self._health_status[chain] = ChainHealth(
            chain=chain,
            status=ChainStatus.HEALTHY,
            last_check=datetime.utcnow(),
            consecutive_failures=0,
            last_success=datetime.utcnow(),
            latency_ms=latency_ms,
        )
        
        # Clear failure timestamps on success
        self._failure_timestamps[chain] = []
        
        # Notify if recovering from outage
        if old_status == ChainStatus.OUTAGE:
            logger.info("chain_recovered", chain=chain.value)
            self._notify_callbacks(chain, ChainStatus.HEALTHY)
        
        return self._health_status[chain]
    
    def _record_failure(self, chain: Chain, error: str) -> ChainHealth:
        """Record a failed health check."""
        now = datetime.utcnow()
        old_status = self._health_status[chain].status
        
        # Track failure timestamp
        self._failure_timestamps[chain].append(now)
        
        # Clean old failures outside window
        window_start = now - timedelta(seconds=self.FAILURE_WINDOW_SECONDS)
        self._failure_timestamps[chain] = [
            ts for ts in self._failure_timestamps[chain] if ts > window_start
        ]
        
        # Count consecutive failures in window
        failures_in_window = len(self._failure_timestamps[chain])
        
        # Determine status
        if failures_in_window >= self.MAX_CONSECUTIVE_FAILURES:
            new_status = ChainStatus.OUTAGE
        elif failures_in_window > 0:
            new_status = ChainStatus.DEGRADED
        else:
            new_status = ChainStatus.HEALTHY
        
        self._health_status[chain] = ChainHealth(
            chain=chain,
            status=new_status,
            last_check=now,
            consecutive_failures=failures_in_window,
            error_message=error,
        )
        
        # Notify on status change
        if new_status != old_status:
            logger.warning(
                "chain_status_changed",
                chain=chain.value,
                from_status=old_status.value,
                to_status=new_status.value,
                failures=failures_in_window,
                error=error,
            )
            self._notify_callbacks(chain, new_status)
        
        return self._health_status[chain]
    
    def get_status(self, chain: Chain) -> ChainHealth:
        """Get current health status for a chain."""
        return self._health_status[chain]
    
    def is_healthy(self, chain: Chain) -> bool:
        """Check if a chain is healthy."""
        return self._health_status[chain].status == ChainStatus.HEALTHY
    
    def is_outage(self, chain: Chain) -> bool:
        """Check if a chain is in outage."""
        return self._health_status[chain].status == ChainStatus.OUTAGE
    
    async def start_monitoring(self):
        """Start continuous monitoring loop."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("outage_detector_started")
    
    async def stop_monitoring(self):
        """Stop monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("outage_detector_stopped")
    
    async def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                for chain in [Chain.SOLANA, Chain.ARBITRUM]:
                    await self.check_chain_health(chain)
                
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("monitor_loop_error", error=str(e))
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
    
    async def __aenter__(self):
        await self.start_monitoring()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop_monitoring()


# Singleton instance
_detector: Optional[OutageDetector] = None
