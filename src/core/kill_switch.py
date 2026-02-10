"""
File-based kill switch for emergency bot shutdown.

The kill switch monitors for a file at /data/emergency.stop.
When detected, it pauses the bot (stops new positions) and logs the event.

IMPORTANT: This does NOT close existing positions. It only prevents NEW positions.
Users must manually close positions via the dashboard or API.

Usage:
    # Trigger kill switch from command line
    touch /data/emergency.stop
    
    # Check status
    cat /data/emergency.stop
    
    # Remove manually (if needed)
    rm /data/emergency.stop
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


class KillSwitchMonitor:
    """
    Monitors for emergency stop file and triggers bot pause.
    
    When kill switch file is detected:
    1. Pauses bot operations (prevents new positions)
    2. Logs the event with details
    3. Removes the file (cleanup)
    4. Reports number of positions still open
    
    Does NOT close existing positions - user must do this manually.
    
    Args:
        kill_switch_path: Path to the kill switch file (default: /data/emergency.stop)
        check_interval: Seconds between checks (default: 5)
    """
    
    DEFAULT_KILL_SWITCH_PATH = "/data/emergency.stop"
    DEFAULT_CHECK_INTERVAL = 5  # seconds
    
    def __init__(
        self,
        kill_switch_path: Optional[str] = None,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
    ):
        self.kill_switch_path = Path(kill_switch_path or self.DEFAULT_KILL_SWITCH_PATH)
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Callbacks
        self._on_triggered: Optional[Callable[[str], None]] = None
        
    def on_triggered(self, callback: Callable[[str], None]):
        """
        Register callback for kill switch trigger.
        
        Args:
            callback: Function called with trigger reason when kill switch activated
        """
        self._on_triggered = callback
        
    async def start(self):
        """Start monitoring for kill switch file."""
        if self._running:
            logger.warning("KillSwitchMonitor already running")
            return
            
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"KillSwitchMonitor started",
            path=str(self.kill_switch_path),
            interval=self.check_interval
        )
        
    async def stop(self):
        """Stop monitoring."""
        if not self._running:
            return
            
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            
        logger.info("KillSwitchMonitor stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_kill_switch()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Kill switch check failed: {e}")
                await asyncio.sleep(self.check_interval)
                
    async def _check_kill_switch(self):
        """Check if kill switch file exists and trigger if so."""
        if not self.kill_switch_path.exists():
            return
            
        # Read file contents for optional reason
        try:
            reason = self.kill_switch_path.read_text().strip()
            if not reason:
                reason = "Kill switch file detected"
        except Exception:
            reason = "Kill switch file detected (could not read contents)"
            
        logger.critical("=" * 60)
        logger.critical("KILL SWITCH ACTIVATED!")
        logger.critical("=" * 60)
        logger.critical(f"Reason: {reason}")
        logger.critical(f"File: {self.kill_switch_path}")
        logger.critical(f"Time: {datetime.utcnow().isoformat()}")
        
        # Remove the file (cleanup)
        try:
            self.kill_switch_path.unlink()
            logger.info("Kill switch file removed (cleanup)")
        except Exception as e:
            logger.error(f"Failed to remove kill switch file: {e}")
            
        # Trigger callback if registered
        if self._on_triggered:
            try:
                await self._async_callback(reason)
            except Exception as e:
                logger.error(f"Kill switch callback failed: {e}")
                
        # Stop monitoring after trigger
        self._running = False
        
    async def _async_callback(self, reason: str):
        """Call the callback (handles both sync and async)."""
        if asyncio.iscoroutinefunction(self._on_triggered):
            await self._on_triggered(reason)
        else:
            self._on_triggered(reason)
            
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running and self._task is not None and not self._task.done()


class KillSwitchTrigger:
    """
    Helper class to trigger the kill switch.
    
    Can be used from scripts, CLI, or other parts of the system.
    
    Example:
        # From Python
        from src.core.kill_switch import KillSwitchTrigger
        KillSwitchTrigger.trigger("Bad market data detected")
        
        # From shell
        echo "API issues" > /data/emergency.stop
    """
    
    @staticmethod
    def trigger(
        reason: str = "Manual trigger",
        kill_switch_path: Optional[str] = None
    ) -> bool:
        """
        Trigger the kill switch by creating the file.
        
        Args:
            reason: Reason for triggering (written to file)
            kill_switch_path: Custom path (default: /data/emergency.stop)
            
        Returns:
            True if file was created successfully
        """
        path = Path(kill_switch_path or KillSwitchMonitor.DEFAULT_KILL_SWITCH_PATH)
        
        try:
            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file with reason
            path.write_text(f"{reason}\nTriggered at: {datetime.utcnow().isoformat()}\n")
            
            logger.info(f"Kill switch triggered: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to trigger kill switch: {e}")
            return False
            
    @staticmethod
    def status(kill_switch_path: Optional[str] = None) -> dict:
        """
        Check kill switch status.
        
        Returns:
            Dict with 'active' (bool) and 'reason' (str or None)
        """
        path = Path(kill_switch_path or KillSwitchMonitor.DEFAULT_KILL_SWITCH_PATH)
        
        if not path.exists():
            return {"active": False, "reason": None}
            
        try:
            content = path.read_text().strip()
            return {"active": True, "reason": content}
        except Exception as e:
            return {"active": True, "reason": f"Error reading: {e}"}
            
    @staticmethod
    def clear(kill_switch_path: Optional[str] = None) -> bool:
        """
        Clear (remove) the kill switch file.
        
        Returns:
            True if file was removed or didn't exist
        """
        path = Path(kill_switch_path or KillSwitchMonitor.DEFAULT_KILL_SWITCH_PATH)
        
        if not path.exists():
            return True
            
        try:
            path.unlink()
            logger.info("Kill switch file cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear kill switch: {e}")
            return False
