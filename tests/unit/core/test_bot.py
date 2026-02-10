"""Tests for the main Bot Runner."""
import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.bot import (
    DeltaNeutralBot,
    BotConfig,
    BotStats,
)
from src.core.pause_controller import PauseScope, CircuitBreakerType
from src.core.risk_engine import ExitReason
from src.models.opportunity import ArbitrageOpportunity
from src.models.position import CombinedPosition, AsgardPosition, HyperliquidPosition
from src.models.common import Asset, Protocol


@pytest.fixture
def bot_config():
    """Create bot configuration."""
    return BotConfig(
        poll_interval_seconds=1,
        scan_interval_seconds=2,
        max_concurrent_positions=3,
        admin_api_key="test_key",
    )


@pytest.fixture
def mock_bot(bot_config):
    """Create a bot with mocked dependencies."""
    with patch('src.core.bot.StatePersistence') as mock_state, \
         patch('src.core.bot.SolanaClient'), \
         patch('src.core.bot.ArbitrumClient'), \
         patch('src.core.bot.RiskEngine'), \
         patch('src.core.bot.PositionSizer'), \
         patch('src.core.bot.LSTMonitor'), \
         patch('src.core.bot.PauseController'), \
         patch('src.core.bot.PositionManager') as mock_pm, \
         patch('src.core.bot.OpportunityDetector'):
        
        # Setup mock position manager
        mock_pm_instance = AsyncMock()
        mock_pm.return_value = mock_pm_instance
        mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
        mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
        
        bot = DeltaNeutralBot(config=bot_config)
        yield bot


class TestBotInitialization:
    """Test bot initialization."""
    
    def test_default_initialization(self):
        """Test bot with default config."""
        with patch('src.core.bot.StatePersistence'), \
             patch('src.core.bot.SolanaClient'), \
             patch('src.core.bot.ArbitrumClient'), \
             patch('src.core.bot.RiskEngine'), \
             patch('src.core.bot.PositionSizer'), \
             patch('src.core.bot.LSTMonitor'), \
             patch('src.core.bot.PauseController'), \
             patch('src.core.bot.PositionManager') as mock_pm:
            
            mock_pm_instance = AsyncMock()
            mock_pm.return_value = mock_pm_instance
            
            bot = DeltaNeutralBot()
            
            assert bot.config is not None
            assert bot._running is False
    
    def test_custom_config(self, bot_config):
        """Test bot with custom config."""
        with patch('src.core.bot.StatePersistence'), \
             patch('src.core.bot.SolanaClient'), \
             patch('src.core.bot.ArbitrumClient'), \
             patch('src.core.bot.RiskEngine'), \
             patch('src.core.bot.PositionSizer'), \
             patch('src.core.bot.LSTMonitor'), \
             patch('src.core.bot.PauseController'), \
             patch('src.core.bot.PositionManager') as mock_pm:
            
            mock_pm_instance = AsyncMock()
            mock_pm.return_value = mock_pm_instance
            
            bot = DeltaNeutralBot(config=bot_config)
            
            assert bot.config.poll_interval_seconds == 1
            assert bot.config.scan_interval_seconds == 2
            assert bot.config.max_concurrent_positions == 3


class TestBotStats:
    """Test BotStats functionality."""
    
    def test_stats_initialization(self):
        """Test stats initialization."""
        stats = BotStats()
        
        assert stats.start_time is None
        assert stats.stop_time is None
        assert stats.opportunities_found == 0
        assert stats.positions_opened == 0
        assert stats.positions_closed == 0
        assert len(stats.errors) == 0
    
    def test_uptime_calculation(self):
        """Test uptime calculation."""
        stats = BotStats()
        stats.start_time = datetime.utcnow()
        
        # Should have some uptime
        assert stats.uptime_seconds > 0
        assert "00:00:" in stats.uptime_formatted
    
    def test_uptime_when_not_started(self):
        """Test uptime when bot hasn't started."""
        stats = BotStats()
        
        assert stats.uptime_seconds == 0.0


class TestBotSetupAndShutdown:
    """Test bot setup and shutdown."""
    
    @pytest.mark.asyncio
    async def test_setup_initializes_components(self, mock_bot):
        """Test that setup initializes all components."""
        mock_bot._state = AsyncMock()
        
        await mock_bot.setup()
        
        mock_bot._state.setup.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_closes_components(self, mock_bot):
        """Test that shutdown closes all components."""
        mock_bot._state = AsyncMock()
        mock_bot._running = True
        
        await mock_bot.shutdown()
        
        assert mock_bot._running is False
        mock_bot._state.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_context_manager(self, bot_config):
        """Test async context manager."""
        with patch('src.core.bot.StatePersistence') as mock_state, \
             patch('src.core.bot.SolanaClient'), \
             patch('src.core.bot.ArbitrumClient'), \
             patch('src.core.bot.RiskEngine'), \
             patch('src.core.bot.PositionSizer'), \
             patch('src.core.bot.LSTMonitor'), \
             patch('src.core.bot.PauseController'), \
             patch('src.core.bot.PositionManager') as mock_pm:
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_pm_instance = AsyncMock()
            mock_pm.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            
            async with DeltaNeutralBot(config=bot_config) as bot:
                assert bot._state is not None
            
            # Should have closed on exit
            mock_state_instance.close.assert_called_once()


class TestMonitorCycle:
    """Test monitoring cycle."""
    
    @pytest.mark.asyncio
    async def test_monitor_cycle_when_paused(self, mock_bot):
        """Test monitor cycle skips when paused."""
        mock_bot._pause_controller = MagicMock()
        mock_bot._pause_controller.check_paused.return_value = True
        
        await mock_bot._monitor_cycle()
        
        # Should not process positions when paused
    
    @pytest.mark.asyncio
    async def test_monitor_position_triggers_exit(self, mock_bot):
        """Test that monitor position triggers exit when needed."""
        # Setup mocks
        position = MagicMock(spec=CombinedPosition)
        position.position_id = "test_pos"
        position.is_closed = False
        
        mock_bot._positions = {"test_pos": position}
        mock_bot._risk_engine = MagicMock()
        mock_bot._risk_engine.evaluate_exit_trigger.return_value = MagicMock(
            should_exit=True,
            reason=ExitReason.NEGATIVE_APY,
        )
        mock_bot.config.enable_auto_exit = True
        
        # Mock _execute_exit
        mock_bot._execute_exit = AsyncMock()
        
        await mock_bot._monitor_position(position)
        
        mock_bot._execute_exit.assert_called_once()


class TestScanCycle:
    """Test scanning cycle."""
    
    @pytest.mark.asyncio
    async def test_scan_cycle_when_paused(self, mock_bot):
        """Test scan cycle skips when paused."""
        mock_bot._pause_controller = MagicMock()
        mock_bot._pause_controller.check_paused.return_value = True
        
        await mock_bot._scan_cycle()
        
        # Should not scan when paused
    
    @pytest.mark.asyncio
    async def test_scan_cycle_max_positions(self, mock_bot):
        """Test scan cycle skips when max positions reached."""
        mock_bot._pause_controller = MagicMock()
        mock_bot._pause_controller.check_paused.return_value = False
        mock_bot._pause_controller.can_execute.return_value = True
        mock_bot.config.max_concurrent_positions = 1
        mock_bot._positions = {"pos1": MagicMock()}
        
        await mock_bot._scan_cycle()
        
        # Should not scan when max positions reached
    
    @pytest.mark.asyncio
    async def test_scan_cycle_finds_opportunity(self, mock_bot):
        """Test scan cycle finds and executes opportunity."""
        # Setup
        mock_bot._pause_controller = MagicMock()
        mock_bot._pause_controller.check_paused.return_value = False
        mock_bot._pause_controller.can_execute.return_value = True
        mock_bot.config.max_concurrent_positions = 5
        mock_bot.config.min_opportunity_apy = Decimal("0.01")
        
        # Mock opportunity
        opportunity = MagicMock(spec=ArbitrageOpportunity)
        opportunity.asset = Asset.SOL
        opportunity.total_expected_apy = Decimal("0.15")
        
        # Mock detector
        mock_detector = AsyncMock()
        mock_detector.__aenter__ = AsyncMock(return_value=mock_detector)
        mock_detector.__aexit__ = AsyncMock(return_value=None)
        mock_detector.scan_opportunities = AsyncMock(return_value=[opportunity])
        mock_bot._opportunity_detector = mock_detector
        
        # Mock _execute_entry
        mock_bot._execute_entry = AsyncMock()
        
        await mock_bot._scan_cycle()
        
        mock_bot._execute_entry.assert_called_once()
        assert mock_bot._stats.opportunities_found == 1


class TestExecuteEntry:
    """Test position entry execution."""
    
    @pytest.mark.asyncio
    async def test_execute_entry_success(self, mock_bot):
        """Test successful position entry."""
        # Setup mocks
        opportunity = MagicMock(spec=ArbitrageOpportunity)
        opportunity.asset = Asset.SOL
        
        sizing_result = MagicMock()
        sizing_result.success = True
        sizing_result.size = MagicMock()
        
        mock_bot._position_sizer = MagicMock()
        mock_bot._position_sizer.calculate_position_size.return_value = sizing_result
        
        mock_bot._solana_client = AsyncMock()
        mock_bot._solana_client.get_balance = AsyncMock(return_value=1000.0)
        mock_bot._arbitrum_client = AsyncMock()
        mock_bot._arbitrum_client.get_balance = AsyncMock(return_value=1000.0)
        
        position = MagicMock(spec=CombinedPosition)
        position.position_id = "new_pos"
        
        mock_bot._position_manager = AsyncMock()
        mock_bot._position_manager.open_position = AsyncMock(return_value=MagicMock(
            success=True,
            position=position,
        ))
        
        mock_bot._state = AsyncMock()
        
        await mock_bot._execute_entry(opportunity)
        
        mock_bot._position_manager.open_position.assert_called_once()
        assert "new_pos" in mock_bot._positions
    
    @pytest.mark.asyncio
    async def test_execute_entry_sizing_failure(self, mock_bot):
        """Test entry when sizing fails."""
        opportunity = MagicMock(spec=ArbitrageOpportunity)
        opportunity.asset = Asset.SOL
        
        sizing_result = MagicMock()
        sizing_result.success = False
        sizing_result.error = "Insufficient balance"
        
        mock_bot._position_sizer = MagicMock()
        mock_bot._position_sizer.calculate_position_size.return_value = sizing_result
        
        mock_bot._solana_client = AsyncMock()
        mock_bot._solana_client.get_balance = AsyncMock(return_value=100.0)
        mock_bot._arbitrum_client = AsyncMock()
        mock_bot._arbitrum_client.get_balance = AsyncMock(return_value=100.0)
        
        await mock_bot._execute_entry(opportunity)
        
        # Should not attempt to open position


class TestExecuteExit:
    """Test position exit execution."""
    
    @pytest.mark.asyncio
    async def test_execute_exit_success(self, mock_bot):
        """Test successful position exit."""
        position = MagicMock(spec=CombinedPosition)
        position.position_id = "pos1"
        
        mock_bot._positions = {"pos1": position}
        mock_bot._position_manager = AsyncMock()
        mock_bot._position_manager.close_position = AsyncMock(return_value=True)
        mock_bot._state = AsyncMock()
        
        await mock_bot._execute_exit(position, "test_reason")
        
        mock_bot._position_manager.close_position.assert_called_once_with("pos1")
        assert "pos1" not in mock_bot._positions
        assert mock_bot._stats.positions_closed == 1
    
    @pytest.mark.asyncio
    async def test_execute_exit_failure(self, mock_bot):
        """Test failed position exit."""
        position = MagicMock(spec=CombinedPosition)
        position.position_id = "pos1"
        
        mock_bot._positions = {"pos1": position}
        mock_bot._position_manager = AsyncMock()
        mock_bot._position_manager.close_position = AsyncMock(return_value=False)
        
        await mock_bot._execute_exit(position, "test_reason")
        
        # Position should still be tracked
        assert "pos1" in mock_bot._positions


class TestCallbacks:
    """Test callback functionality."""
    
    def test_add_opportunity_callback(self, mock_bot):
        """Test adding opportunity callback."""
        callback = MagicMock()
        mock_bot.add_opportunity_callback(callback)
        
        assert callback in mock_bot._opportunity_callbacks
    
    def test_add_position_opened_callback(self, mock_bot):
        """Test adding position opened callback."""
        callback = MagicMock()
        mock_bot.add_position_opened_callback(callback)
        
        assert callback in mock_bot._position_opened_callbacks
    
    def test_add_position_closed_callback(self, mock_bot):
        """Test adding position closed callback."""
        callback = MagicMock()
        mock_bot.add_position_closed_callback(callback)
        
        assert callback in mock_bot._position_closed_callbacks


class TestPublicAPI:
    """Test public API methods."""
    
    def test_get_stats(self, mock_bot):
        """Test get_stats method."""
        stats = mock_bot.get_stats()
        
        assert isinstance(stats, BotStats)
    
    def test_get_positions(self, mock_bot):
        """Test get_positions method."""
        mock_position = MagicMock()
        # Use user-scoped structure: user_id -> position_id -> position
        mock_bot._positions = {"default": {"pos1": mock_position}}
        
        positions = mock_bot.get_positions()
        
        assert "pos1" in positions
    
    @pytest.mark.asyncio
    async def test_pause(self, mock_bot):
        """Test pause method."""
        mock_bot._pause_controller = MagicMock()
        mock_bot._pause_controller.pause.return_value = True
        
        result = await mock_bot.pause("test_key", "test_reason")
        
        assert result is True
        mock_bot._pause_controller.pause.assert_called_once_with(
            "test_key", "test_reason", PauseScope.ALL
        )
    
    @pytest.mark.asyncio
    async def test_resume(self, mock_bot):
        """Test resume method."""
        mock_bot._pause_controller = MagicMock()
        mock_bot._pause_controller.resume.return_value = True
        
        result = await mock_bot.resume("test_key")
        
        assert result is True
        mock_bot._pause_controller.resume.assert_called_once_with("test_key")


class TestRecovery:
    """Test state recovery."""
    
    @pytest.mark.asyncio
    async def test_recover_state(self, mock_bot):
        """Test state recovery on startup."""
        position = MagicMock()
        position.position_id = "recovered_pos"
        position.user_id = "test_user"
        position.is_closed = False
        
        mock_bot._state = AsyncMock()
        mock_bot._state.load_positions = AsyncMock(return_value=[position])
        
        await mock_bot._recover_state()
        
        # Check nested structure: user_id -> position_id
        assert "test_user" in mock_bot._positions
        assert "recovered_pos" in mock_bot._positions["test_user"]
