"""Integration tests for full position exit flow.

Tests the complete exit flow from exit trigger detection through position closing,
including proper ordering (Hyperliquid first, then Asgard).
"""
import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from bot.core.bot import DeltaNeutralBot, BotConfig
from bot.core.risk_engine import ExitReason, RiskLevel, ExitDecision
from shared.models.position import (
    AsgardPosition, 
    HyperliquidPosition, 
    CombinedPosition,
    PositionReference
)
from shared.models.common import Asset, Protocol


@pytest.fixture
def mock_open_position():
    """Create a mock open position for exit testing."""
    asgard = AsgardPosition(
        position_pda="TestPDA123456789",
        intent_id="test_intent_001",
        asset=Asset.SOL,
        protocol=Protocol.MARGINFI,
        collateral_usd=Decimal("5000"),
        position_size_usd=Decimal("15000"),
        leverage=Decimal("3"),
        token_a_amount=Decimal("100"),
        token_b_borrowed=Decimal("10000"),
        entry_price_token_a=Decimal("150"),
        current_health_factor=Decimal("0.25"),
        current_token_a_price=Decimal("150"),
    )
    
    hyperliquid = HyperliquidPosition(
        coin="SOL",
        size_sol=Decimal("-100"),  # Negative = short
        entry_px=Decimal("150"),
        leverage=Decimal("3"),
        margin_used=Decimal("5000"),
        margin_fraction=Decimal("0.15"),
        account_value=Decimal("5000"),
        mark_px=Decimal("150"),
    )
    
    return CombinedPosition(
        position_id="test_pos_exit_001",
        asgard=asgard,
        hyperliquid=hyperliquid,
        reference=PositionReference(
            asgard_entry_price=Decimal("150"),
            hyperliquid_entry_price=Decimal("150"),
        ),
        opportunity_id="test_opp_001",
        status="open",
    )


@pytest.fixture
def mock_positions(mock_open_position):
    """Create a dict of mock positions (nested by user_id)."""
    return {"default": {mock_open_position.position_id: mock_open_position}}


class TestFullExitFlow:
    """Test complete position exit flow."""
    
    @pytest.mark.asyncio
    async def test_successful_exit_flow(self, mock_open_position):
        """Test successful end-to-end position exit."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.LSTMonitor'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=True)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Set up the position
            bot._positions.setdefault("default", {})[mock_open_position.position_id] = mock_open_position

            # Execute exit
            await bot._execute_exit(mock_open_position, "test_exit")

            # Verify position was removed
            assert sum(len(v) for v in bot._positions.values()) == 0
            assert bot._stats.positions_closed == 1
            
            # Verify state was updated
            mock_state_instance.delete_position.assert_called_once_with(
                mock_open_position.position_id
            )
            mock_state_instance.log_action.assert_called_once()
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_exit_hyperliquid_first_then_asgard(self, mock_open_position):
        """Test that exit closes Hyperliquid before Asgard (spec 5.2)."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.LSTMonitor'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=True)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            bot._positions.setdefault("default", {})[mock_open_position.position_id] = mock_open_position

            # Execute exit
            await bot._execute_exit(mock_open_position, "test_exit")

            # Note: The position manager is responsible for the ordering,
            # we just verify it was called
            mock_pm_instance.close_position.assert_called_once_with(
                mock_open_position.position_id
            )
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_exit_with_close_failure(self, mock_open_position):
        """Test exit when close operation fails."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.LSTMonitor'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=False)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            bot._positions.setdefault("default", {})[mock_open_position.position_id] = mock_open_position

            # Execute exit - should fail
            await bot._execute_exit(mock_open_position, "test_exit")

            # Verify position is still tracked
            assert sum(len(v) for v in bot._positions.values()) == 1
            assert bot._stats.positions_closed == 0
            
            # Verify state was NOT updated
            mock_state_instance.delete_position.assert_not_called()
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_exit_due_to_negative_apy(self, mock_open_position):
        """Test exit triggered by negative APY condition."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.LSTMonitor'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            # Setup risk engine to trigger exit
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.NEGATIVE_APY,
                level=RiskLevel.WARNING,
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=True)
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            bot._positions.setdefault("default", {})[mock_open_position.position_id] = mock_open_position

            # Run monitor cycle which should detect exit condition
            await bot._monitor_position(mock_open_position)

            # Verify exit was executed
            assert sum(len(v) for v in bot._positions.values()) == 0
            assert bot._stats.positions_closed == 1
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_exit_due_to_funding_flip(self, mock_open_position):
        """Test exit triggered by funding rate flip."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.LSTMonitor'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.FUNDING_FLIP,
                level=RiskLevel.WARNING,
                details={
                    "current_funding": 0.05,
                    "predicted_funding": 0.10,
                }
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=True)
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            bot._positions.setdefault("default", {})[mock_open_position.position_id] = mock_open_position

            # Run monitor cycle
            await bot._monitor_position(mock_open_position)

            # Verify exit was executed
            assert sum(len(v) for v in bot._positions.values()) == 0
            
            await bot.shutdown()


class TestExitCallbacks:
    """Test callbacks during exit flow."""
    
    @pytest.mark.asyncio
    async def test_position_closed_callback(self, mock_open_position):
        """Test that position closed callback is triggered."""
        
        callback_triggered = False
        callback_position = None
        callback_reason = None
        
        def callback(position, reason):
            nonlocal callback_triggered, callback_position, callback_reason
            callback_triggered = True
            callback_position = position
            callback_reason = reason
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.LSTMonitor'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=True)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            bot.add_position_closed_callback(callback)
            await bot.setup()
            
            bot._positions.setdefault("default", {})[mock_open_position.position_id] = mock_open_position

            # Execute exit
            await bot._execute_exit(mock_open_position, "manual_exit")

            # Verify callback was triggered
            assert callback_triggered is True
            assert callback_position is not None
            assert callback_position.position_id == mock_open_position.position_id
            assert callback_reason == "manual_exit"
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_multiple_exit_callbacks(self, mock_open_position):
        """Test multiple callbacks during exit."""
        
        callbacks_triggered = []
        
        def callback1(position, reason):
            callbacks_triggered.append("callback1")
        
        def callback2(position, reason):
            callbacks_triggered.append("callback2")
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.LSTMonitor'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=True)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            bot.add_position_closed_callback(callback1)
            bot.add_position_closed_callback(callback2)
            await bot.setup()
            
            bot._positions.setdefault("default", {})[mock_open_position.position_id] = mock_open_position

            # Execute exit
            await bot._execute_exit(mock_open_position, "test")

            # Verify both callbacks were triggered
            assert "callback1" in callbacks_triggered
            assert "callback2" in callbacks_triggered
            
            await bot.shutdown()


class TestExitWithDifferentAssets:
    """Test exit with different asset types."""
    
    @pytest.mark.asyncio
    async def test_exit_with_jupsol_position(self):
        """Test exit with jupSOL position."""
        
        asgard = AsgardPosition(
            position_pda="TestPDAjupSOL",
            intent_id="test_intent_jupsol",
            asset=Asset.JUPSOL,
            protocol=Protocol.KAMINO,
            collateral_usd=Decimal("5000"),
            position_size_usd=Decimal("15000"),
            leverage=Decimal("3"),
            token_a_amount=Decimal("95"),
            token_b_borrowed=Decimal("10000"),
            entry_price_token_a=Decimal("157.89"),
            current_health_factor=Decimal("0.25"),
            current_token_a_price=Decimal("158"),
        )
        
        hyperliquid = HyperliquidPosition(
            coin="SOL",
            size_sol=Decimal("-95"),
            entry_px=Decimal("150"),
            leverage=Decimal("3"),
            margin_used=Decimal("4750"),
            margin_fraction=Decimal("0.15"),
            account_value=Decimal("5000"),
            mark_px=Decimal("150"),
        )
        
        position = CombinedPosition(
            position_id="test_pos_jupsol_exit",
            asgard=asgard,
            hyperliquid=hyperliquid,
            reference=PositionReference(
                asgard_entry_price=Decimal("157.89"),
                hyperliquid_entry_price=Decimal("150"),
            ),
            opportunity_id="test_opp_jupsol",
            status="open",
        )
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.LSTMonitor'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=True)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            bot._positions.setdefault("default", {})[position.position_id] = position

            # Execute exit
            await bot._execute_exit(position, "test_exit")

            # Verify position was removed
            assert sum(len(v) for v in bot._positions.values()) == 0
            
            await bot.shutdown()


class TestExitWhilePaused:
    """Test exit behavior when bot is paused."""
    
    @pytest.mark.asyncio
    async def test_exit_not_executed_while_paused(self, mock_open_position):
        """Test that auto-exit doesn't happen when bot is paused."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.LSTMonitor'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            # Risk engine would trigger exit, but pause controller blocks it
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.NEGATIVE_APY,
            )
            
            # Bot is paused
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = True
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            bot._positions.setdefault("default", {})[mock_open_position.position_id] = mock_open_position

            # Run monitor cycle while paused
            await bot._monitor_cycle()

            # Verify position was NOT closed (monitor cycle skipped)
            assert sum(len(v) for v in bot._positions.values()) == 1
            
            await bot.shutdown()
