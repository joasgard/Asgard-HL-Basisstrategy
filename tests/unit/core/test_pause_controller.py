"""Tests for Pause Controller and Circuit Breakers."""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from bot.core.pause_controller import (
    PauseController,
    CircuitBreakerType,
    PauseScope,
    CircuitBreakerEvent,
    PauseState,
)


@pytest.fixture
def controller():
    """Create a PauseController instance."""
    return PauseController(admin_api_key="test_secret_key")


class TestPauseControllerInitialization:
    """Test PauseController initialization."""
    
    def test_initialization(self):
        """Test PauseController initialization."""
        controller = PauseController(admin_api_key="my_secret")
        
        assert controller._admin_api_key == "my_secret"
        assert controller._paused is False
        assert controller.check_paused() is False


class TestManualPauseResume:
    """Test manual pause and resume functionality."""
    
    def test_pause_success(self, controller):
        """Test successful pause."""
        result = controller.pause("test_secret_key", "Emergency maintenance")
        
        assert result is True
        assert controller.check_paused() is True
        assert controller._pause_reason == "Emergency maintenance"
        assert controller._paused_by == "admin"
    
    def test_pause_invalid_key(self, controller):
        """Test pause with invalid API key."""
        with pytest.raises(ValueError, match="Invalid API key"):
            controller.pause("wrong_key", "Test")
        
        assert controller.check_paused() is False
    
    def test_pause_with_scope(self, controller):
        """Test pause with specific scope."""
        controller.pause("test_secret_key", "Test", scope=PauseScope.ENTRY)
        
        assert controller.check_paused() is True
        assert controller.check_paused(PauseScope.ENTRY) is True
        assert controller._pause_scope == PauseScope.ENTRY
    
    def test_resume_success(self, controller):
        """Test successful resume."""
        controller.pause("test_secret_key", "Test")
        assert controller.check_paused() is True
        
        result = controller.resume("test_secret_key")
        
        assert result is True
        assert controller.check_paused() is False
    
    def test_resume_invalid_key(self, controller):
        """Test resume with invalid API key."""
        controller.pause("test_secret_key", "Test")
        
        with pytest.raises(ValueError, match="Invalid API key"):
            controller.resume("wrong_key")
        
        assert controller.check_paused() is True  # Still paused
    
    def test_resume_when_not_paused(self, controller):
        """Test resume when not paused."""
        result = controller.resume("test_secret_key")
        
        assert result is True  # Still succeeds
        assert controller.check_paused() is False


class TestCheckPaused:
    """Test pause checking functionality."""
    
    def test_check_paused_all_scope(self, controller):
        """Test check paused with ALL scope."""
        controller.pause("test_secret_key", "Test", scope=PauseScope.ALL)
        
        assert controller.check_paused() is True
        assert controller.check_paused(PauseScope.ENTRY) is True
        assert controller.check_paused(PauseScope.EXIT) is True
        assert controller.check_paused(PauseScope.ASGARD) is True
        assert controller.check_paused(PauseScope.HYPERLIQUID) is True
    
    def test_check_paused_entry_scope(self, controller):
        """Test check paused with ENTRY scope."""
        controller.pause("test_secret_key", "Test", scope=PauseScope.ENTRY)
        
        assert controller.check_paused() is True
        assert controller.check_paused(PauseScope.ENTRY) is True
        assert controller.check_paused(PauseScope.EXIT) is False
        assert controller.check_paused(PauseScope.ASGARD) is False


class TestAssertNotPaused:
    """Test assert_not_paused method."""
    
    def test_assert_not_paused_when_not_paused(self, controller):
        """Test assert when not paused (should not raise)."""
        controller.assert_not_paused()  # Should not raise
    
    def test_assert_not_paused_when_paused(self, controller):
        """Test assert when paused (should raise)."""
        controller.pause("test_secret_key", "Test pause")
        
        with pytest.raises(RuntimeError, match="Operations paused"):
            controller.assert_not_paused()


class TestCanExecute:
    """Test operation permission checking."""
    
    def test_can_execute_when_not_paused(self, controller):
        """Test can_execute when not paused."""
        assert controller.can_execute("entry") is True
        assert controller.can_execute("exit") is True
        assert controller.can_execute("asgard") is True
        assert controller.can_execute("hyperliquid") is True
    
    def test_can_execute_all_paused(self, controller):
        """Test can_execute when ALL paused."""
        controller.pause("test_secret_key", "Test", scope=PauseScope.ALL)
        
        assert controller.can_execute("entry") is False
        assert controller.can_execute("exit") is False
    
    def test_can_execute_entry_paused(self, controller):
        """Test can_execute when ENTRY paused."""
        controller.pause("test_secret_key", "Test", scope=PauseScope.ENTRY)
        
        assert controller.can_execute("entry") is False
        assert controller.can_execute("exit") is True
    
    def test_can_execute_asgard_paused(self, controller):
        """Test can_execute when ASGARD paused."""
        controller.pause("test_secret_key", "Test", scope=PauseScope.ASGARD)
        
        assert controller.can_execute("asgard") is False
        assert controller.can_execute("hyperliquid") is True


class TestCircuitBreakers:
    """Test circuit breaker functionality."""
    
    def test_trigger_circuit_breaker(self, controller):
        """Test triggering a circuit breaker."""
        event = controller.trigger_circuit_breaker(
            CircuitBreakerType.ASGARD_HEALTH,
            "HF below threshold",
            PauseScope.ALL,
        )
        
        assert event.breaker_type == CircuitBreakerType.ASGARD_HEALTH
        assert event.reason == "HF below threshold"
        assert event.is_active is True
        assert controller.check_paused() is True
    
    def test_circuit_breaker_with_auto_recovery(self, controller):
        """Test circuit breaker with auto-recovery."""
        event = controller.trigger_circuit_breaker(
            CircuitBreakerType.PRICE_DEVIATION,
            "Price deviation high",
            PauseScope.ENTRY,
            auto_recovery=True,
            cooldown_seconds=1,  # 1 second for testing
        )
        
        assert event.auto_recovery is True
        assert event.cooldown_seconds == 1
        assert event.recovery_time is not None
    
    def test_resolve_circuit_breaker(self, controller):
        """Test resolving a circuit breaker."""
        controller.trigger_circuit_breaker(
            CircuitBreakerType.LST_DEPEG,
            "LST depeg detected",
        )
        
        result = controller.resolve_circuit_breaker(CircuitBreakerType.LST_DEPEG)
        
        assert result is True
        assert controller.check_paused() is False  # All resolved
        
        active = controller.get_active_breakers()
        assert len(active) == 0
    
    def test_get_active_breakers(self, controller):
        """Test getting active breakers."""
        controller.trigger_circuit_breaker(
            CircuitBreakerType.HIGH_GAS,
            "Gas too high",
        )
        controller.trigger_circuit_breaker(
            CircuitBreakerType.CHAIN_OUTAGE,
            "Chain down",
        )
        
        active = controller.get_active_breakers()
        
        assert len(active) == 2
        assert all(b.is_active for b in active)
    
    def test_check_and_recover(self, controller):
        """Test auto-recovery check."""
        controller.trigger_circuit_breaker(
            CircuitBreakerType.PRICE_DEVIATION,
            "Price dev",
            auto_recovery=True,
            cooldown_seconds=0,  # Immediate recovery
        )
        
        # Set recovery time to past
        for breaker in controller._circuit_breakers:
            breaker.recovery_time = datetime.utcnow() - timedelta(seconds=1)
        
        recovered = controller.check_and_recover()
        
        assert len(recovered) == 1
        assert controller.check_paused() is False


class TestCircuitBreakerHistory:
    """Test circuit breaker history tracking."""
    
    def test_get_circuit_breaker_history(self, controller):
        """Test getting full history."""
        controller.trigger_circuit_breaker(
            CircuitBreakerType.ASGARD_HEALTH,
            "HF low",
        )
        controller.resolve_circuit_breaker(CircuitBreakerType.ASGARD_HEALTH)
        
        history = controller.get_circuit_breaker_history()
        
        assert len(history) == 1
        assert history[0].breaker_type == CircuitBreakerType.ASGARD_HEALTH
        assert history[0].resolved_at is not None
    
    def test_get_history_filtered(self, controller):
        """Test getting filtered history."""
        controller.trigger_circuit_breaker(
            CircuitBreakerType.ASGARD_HEALTH,
            "HF low",
        )
        controller.trigger_circuit_breaker(
            CircuitBreakerType.HIGH_GAS,
            "Gas high",
        )
        
        history = controller.get_circuit_breaker_history(CircuitBreakerType.HIGH_GAS)
        
        assert len(history) == 1
        assert history[0].breaker_type == CircuitBreakerType.HIGH_GAS


class TestPauseState:
    """Test pause state functionality."""
    
    def test_get_pause_state_when_paused(self, controller):
        """Test getting pause state when paused."""
        controller.pause("test_secret_key", "Test", scope=PauseScope.ENTRY)
        
        state = controller.get_pause_state()
        
        assert state.paused is True
        assert state.scope == PauseScope.ENTRY
        assert state.reason == "Test"
        assert state.paused_by == "admin"
        assert state.paused_at is not None
    
    def test_get_pause_state_when_not_paused(self, controller):
        """Test getting pause state when not paused."""
        state = controller.get_pause_state()
        
        assert state.paused is False
        assert state.reason is None


class TestCallbacks:
    """Test callback functionality."""
    
    def test_pause_callback(self, controller):
        """Test pause callback is triggered."""
        callback = MagicMock()
        controller.add_pause_callback(callback)
        
        controller.pause("test_secret_key", "Test")
        
        callback.assert_called_once()
        assert callback.call_args[0][0].paused is True
    
    def test_resume_callback(self, controller):
        """Test resume callback is triggered."""
        callback = MagicMock()
        controller.add_resume_callback(callback)
        
        controller.pause("test_secret_key", "Test")
        controller.resume("test_secret_key")
        
        callback.assert_called_once()


class TestGasThresholds:
    """Test gas price threshold checking."""
    
    def test_is_high_gas_true(self, controller):
        """Test high gas detection."""
        assert controller.is_high_gas(Decimal("0.015")) is True
        assert controller.is_high_gas(Decimal("0.01")) is False  # Exactly at threshold
    
    def test_is_high_gas_false(self, controller):
        """Test normal gas detection."""
        assert controller.is_high_gas(Decimal("0.005")) is False
    
    def test_should_recover_from_high_gas(self, controller):
        """Test gas recovery threshold."""
        assert controller.should_recover_from_high_gas(Decimal("0.004")) is True
        assert controller.should_recover_from_high_gas(Decimal("0.005")) is False  # At threshold


class TestCircuitBreakerEvent:
    """Test CircuitBreakerEvent properties."""
    
    def test_is_active_property(self):
        """Test is_active property."""
        active = CircuitBreakerEvent(
            breaker_type=CircuitBreakerType.ASGARD_HEALTH,
            triggered_at=datetime.utcnow(),
            reason="Test",
            scope=PauseScope.ALL,
            auto_recovery=False,
        )
        assert active.is_active is True
        
        resolved = CircuitBreakerEvent(
            breaker_type=CircuitBreakerType.ASGARD_HEALTH,
            triggered_at=datetime.utcnow(),
            reason="Test",
            scope=PauseScope.ALL,
            auto_recovery=False,
            resolved_at=datetime.utcnow(),
        )
        assert resolved.is_active is False
    
    def test_age_seconds_property(self):
        """Test age_seconds property."""
        event = CircuitBreakerEvent(
            breaker_type=CircuitBreakerType.ASGARD_HEALTH,
            triggered_at=datetime.utcnow() - timedelta(seconds=30),
            reason="Test",
            scope=PauseScope.ALL,
            auto_recovery=False,
        )
        
        assert event.age_seconds >= 30


class TestDefaultCooldowns:
    """Test default cooldown configurations."""
    
    def test_asgard_health_cooldown(self, controller):
        """Test Asgard health has immediate cooldown."""
        cooldown = controller.DEFAULT_COOLDOWNS[CircuitBreakerType.ASGARD_HEALTH]
        assert cooldown == 0  # Immediate, manual reset
    
    def test_price_deviation_cooldown(self, controller):
        """Test price deviation has 30 min cooldown."""
        cooldown = controller.DEFAULT_COOLDOWNS[CircuitBreakerType.PRICE_DEVIATION]
        assert cooldown == 1800  # 30 minutes
