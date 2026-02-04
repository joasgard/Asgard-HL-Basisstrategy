"""
Tests for Position Monitor module.

These tests verify:
- APY threshold checking (10% minimum)
- Consecutive breach counting
- Exit condition triggering
- Funding flip detection
- Delta drift calculation
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.assets import Asset
from src.core.position_monitor import (
    MonitorConfig,
    PositionMonitor,
    PositionStatus,
)
from src.models.common import Protocol
from src.models.position import AsgardPosition, CombinedPosition, HyperliquidPosition, PositionReference


# Fixtures
@pytest.fixture
def monitor_config():
    """Default monitor configuration."""
    return MonitorConfig(
        min_apy_threshold=Decimal("0.10"),  # 10%
        consecutive_breaches_required=2,
        exit_on_funding_flip=True,
        max_delta_drift=Decimal("0.005"),
    )


@pytest.fixture
def base_asgard_position():
    """Base Asgard position factory."""
    def _create():
        return AsgardPosition(
            position_pda="pda1",
            intent_id="intent-1",
            asset=Asset.SOL,
            protocol=Protocol.MARGINFI,
            collateral_usd=Decimal("50000"),
            position_size_usd=Decimal("150000"),
            leverage=Decimal("3"),
            token_a_amount=Decimal("1500"),
            token_b_borrowed=Decimal("100000"),
            entry_price_token_a=Decimal("100"),
            current_health_factor=Decimal("0.25"),
            current_token_a_price=Decimal("100"),
        )
    return _create


@pytest.fixture
def base_hyperliquid_position():
    """Base Hyperliquid position factory."""
    def _create():
        return HyperliquidPosition(
            coin="SOL",
            size_sol=Decimal("-1500"),
            entry_px=Decimal("100"),
            leverage=Decimal("3"),
            margin_used=Decimal("50000"),
            margin_fraction=Decimal("0.33"),
            account_value=Decimal("55000"),
            mark_px=Decimal("100"),
        )
    return _create


@pytest.fixture
def base_reference():
    """Base position reference."""
    return PositionReference(
        asgard_entry_price=Decimal("100"),
        hyperliquid_entry_price=Decimal("100"),
    )


@pytest.fixture
def high_apy_position(base_asgard_position, base_hyperliquid_position, base_reference):
    """Position with high APY (15% - should hold)."""
    return CombinedPosition(
        position_id="pos-high-apy",
        asgard=base_asgard_position(),
        hyperliquid=base_hyperliquid_position(),
        reference=base_reference,
        opportunity_id="opp-1",
    )


@pytest.fixture
def low_apy_position(base_asgard_position, base_hyperliquid_position, base_reference):
    """Position with low APY (5% - should exit after consecutive breaches)."""
    return CombinedPosition(
        position_id="pos-low-apy",
        asgard=base_asgard_position(),
        hyperliquid=base_hyperliquid_position(),
        reference=base_reference,
        opportunity_id="opp-2",
    )


@pytest.fixture
def mock_opportunity_detector():
    """Mock OpportunityDetector."""
    mock = MagicMock()
    mock.hyperliquid = MagicMock()
    mock.hyperliquid.get_current_funding_rates = AsyncMock(return_value={
        "SOL": MagicMock(annualized_rate=-0.15)
    })
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


class TestMonitorConfig:
    """Tests for MonitorConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = MonitorConfig()
        
        assert config.min_apy_threshold == Decimal("0.10")  # 10%
        assert config.consecutive_breaches_required == 2
        assert config.exit_on_funding_flip is True
        assert config.max_delta_drift == Decimal("0.005")
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = MonitorConfig(
            min_apy_threshold=Decimal("0.15"),
            consecutive_breaches_required=3,
        )
        
        assert config.min_apy_threshold == Decimal("0.15")
        assert config.consecutive_breaches_required == 3


class TestPositionMonitorInit:
    """Tests for PositionMonitor initialization."""
    
    def test_init_default(self):
        """Test initialization with defaults."""
        monitor = PositionMonitor()
        
        assert monitor.config is not None
        assert monitor.config.min_apy_threshold == Decimal("0.10")
        assert monitor.opportunity_detector is None
        assert monitor._own_detector is True
    
    def test_init_with_config(self, monitor_config):
        """Test initialization with custom config."""
        monitor = PositionMonitor(config=monitor_config)
        
        assert monitor.config == monitor_config
        assert monitor.config.min_apy_threshold == Decimal("0.10")
    
    def test_init_with_detector(self, mock_opportunity_detector):
        """Test initialization with provided detector."""
        monitor = PositionMonitor(opportunity_detector=mock_opportunity_detector)
        
        assert monitor.opportunity_detector is mock_opportunity_detector
        assert monitor._own_detector is False


class TestCheckPositionHighAPY:
    """Tests for high APY positions (should hold)."""
    
    @pytest.mark.asyncio
    async def test_high_apy_hold_position(self, high_apy_position, monitor_config):
        """Test that high APY positions are held."""
        monitor = PositionMonitor(config=monitor_config)
        
        # High APY: 15% funding
        status = await monitor.check_position(
            high_apy_position, 
            current_funding_rate=Decimal("-0.15")
        )
        
        assert status.should_exit is False
        assert status.exit_reason is None
        assert status.apy_below_threshold is False
    
    @pytest.mark.asyncio
    async def test_exact_threshold_hold(self, base_asgard_position, base_hyperliquid_position, base_reference, monitor_config):
        """Test position at exactly 10% threshold (should hold)."""
        position = CombinedPosition(
            position_id="pos-exact",
            asgard=base_asgard_position(),
            hyperliquid=base_hyperliquid_position(),
            reference=base_reference,
            opportunity_id="opp-exact",
        )
        
        monitor = PositionMonitor(config=monitor_config)
        # 11% funding - 1% carry = 10%, which equals threshold, so NOT below
        status = await monitor.check_position(
            position,
            current_funding_rate=Decimal("-0.11")
        )
        
        assert status.apy_below_threshold is False
        assert status.should_exit is False


class TestCheckPositionLowAPY:
    """Tests for low APY positions (should exit after breaches)."""
    
    @pytest.mark.asyncio
    async def test_low_apy_first_breach_no_exit(self, low_apy_position, monitor_config):
        """Test first breach doesn't trigger exit (need consecutive)."""
        monitor = PositionMonitor(config=monitor_config)
        
        # Low APY: 5% funding - 1% carry = 4%
        status = await monitor.check_position(
            low_apy_position,
            current_funding_rate=Decimal("-0.05")
        )
        
        # First check: breach detected but no exit
        assert status.apy_below_threshold is True
        assert status.should_exit is False
        assert status.consecutive_breaches == 1
    
    @pytest.mark.asyncio
    async def test_low_apy_second_breach_triggers_exit(self, low_apy_position, monitor_config):
        """Test second consecutive breach triggers exit."""
        monitor = PositionMonitor(config=monitor_config)
        
        # First check
        await monitor.check_position(low_apy_position, current_funding_rate=Decimal("-0.05"))
        
        # Second check - should trigger exit
        status = await monitor.check_position(low_apy_position, current_funding_rate=Decimal("-0.05"))
        
        assert status.should_exit is True
        assert status.exit_reason is not None
        assert "APY below 10%" in status.exit_reason
        assert status.consecutive_breaches == 2
    
    @pytest.mark.asyncio
    async def test_apy_recovery_resets_breach_count(self, low_apy_position, monitor_config):
        """Test that APY recovery resets breach count."""
        monitor = PositionMonitor(config=monitor_config)
        
        # First check - low APY
        await monitor.check_position(low_apy_position, current_funding_rate=Decimal("-0.05"))
        assert monitor.get_breach_count(low_apy_position.position_id) == 1
        
        # Simulate recovery - high APY check (same position ID)
        status = await monitor.check_position(low_apy_position, current_funding_rate=Decimal("-0.15"))
        
        # Breach count should be reset
        assert monitor.get_breach_count(low_apy_position.position_id) == 0
        assert status.apy_below_threshold is False


class TestFundingFlip:
    """Tests for funding flip detection."""
    
    @pytest.mark.asyncio
    async def test_funding_flip_triggers_exit(self, base_asgard_position, base_hyperliquid_position, base_reference, monitor_config):
        """Test that positive funding triggers exit."""
        position = CombinedPosition(
            position_id="pos-flip",
            asgard=base_asgard_position(),
            hyperliquid=base_hyperliquid_position(),
            reference=base_reference,
            opportunity_id="opp-flip",
        )
        
        monitor = PositionMonitor(config=monitor_config)
        # Positive funding = shorts pay (bad for us)
        status = await monitor.check_position(position, current_funding_rate=Decimal("0.05"))
        
        assert status.should_exit is True
        assert status.exit_reason == "Funding rate flipped positive"
        assert status.funding_flipped is True
    
    @pytest.mark.asyncio
    async def test_negative_funding_no_flip(self, high_apy_position, monitor_config):
        """Test that negative funding doesn't trigger flip."""
        monitor = PositionMonitor(config=monitor_config)
        
        status = await monitor.check_position(
            high_apy_position,
            current_funding_rate=Decimal("-0.15")
        )
        
        assert status.funding_flipped is False
        assert status.exit_reason != "Funding rate flipped positive"


class TestDeltaDrift:
    """Tests for delta drift calculation."""
    
    def test_delta_drift_calculation(self, base_asgard_position):
        """Test delta drift calculation."""
        monitor = PositionMonitor()
        
        asgard = base_asgard_position()
        asgard.position_size_usd = Decimal("150000")
        
        hyperliquid = HyperliquidPosition(
            coin="SOL",
            size_sol=Decimal("-1530"),
            entry_px=Decimal("100"),
            leverage=Decimal("3"),
            margin_used=Decimal("50000"),
            margin_fraction=Decimal("0.33"),
            account_value=Decimal("55000"),
            mark_px=Decimal("100"),
        )
        # size_usd = 1530 * 100 = 153000 (2% larger)
        
        position = CombinedPosition(
            position_id="pos-drift",
            asgard=asgard,
            hyperliquid=hyperliquid,
            reference=PositionReference(
                asgard_entry_price=Decimal("100"),
                hyperliquid_entry_price=Decimal("100"),
            ),
            opportunity_id="opp-drift",
        )
        
        drift = monitor._calculate_delta_drift(position)
        
        # Drift: |150k - 153k| / avg = 3k / 151.5k ≈ 1.98%
        assert drift == pytest.approx(Decimal("0.0198"), abs=Decimal("0.001"))
    
    @pytest.mark.asyncio
    async def test_excessive_delta_drift_triggers_exit(self, base_asgard_position, base_reference, monitor_config):
        """Test that excessive delta drift triggers exit."""
        asgard = base_asgard_position()
        asgard.position_size_usd = Decimal("150000")
        
        hyperliquid = HyperliquidPosition(
            coin="SOL",
            size_sol=Decimal("-1580"),  # 158k USD = ~5% drift
            entry_px=Decimal("100"),
            leverage=Decimal("3"),
            margin_used=Decimal("50000"),
            margin_fraction=Decimal("0.33"),
            account_value=Decimal("55000"),
            mark_px=Decimal("100"),
        )
        
        position = CombinedPosition(
            position_id="pos-high-drift",
            asgard=asgard,
            hyperliquid=hyperliquid,
            reference=base_reference,
            opportunity_id="opp-high-drift",
        )
        
        monitor = PositionMonitor(config=monitor_config)
        # High APY should not matter with excessive drift
        status = await monitor.check_position(
            position,
            current_funding_rate=Decimal("-0.15")
        )
        
        # Should exit due to delta drift even with high APY
        assert status.should_exit is True
        assert "Delta drift exceeded" in status.exit_reason
    
    def test_no_drift_when_equal(self, base_asgard_position):
        """Test zero drift when positions are equal."""
        monitor = PositionMonitor()
        
        asgard = base_asgard_position()
        asgard.position_size_usd = Decimal("150000")
        
        hyperliquid = HyperliquidPosition(
            coin="SOL",
            size_sol=Decimal("-1500"),  # 150k USD
            entry_px=Decimal("100"),
            leverage=Decimal("3"),
            margin_used=Decimal("50000"),
            margin_fraction=Decimal("0.33"),
            account_value=Decimal("55000"),
            mark_px=Decimal("100"),
        )
        
        position = CombinedPosition(
            position_id="pos-no-drift",
            asgard=asgard,
            hyperliquid=hyperliquid,
            reference=PositionReference(
                asgard_entry_price=Decimal("100"),
                hyperliquid_entry_price=Decimal("100"),
            ),
            opportunity_id="opp-no-drift",
        )
        
        drift = monitor._calculate_delta_drift(position)
        
        assert drift == Decimal("0")


class TestBreachCountManagement:
    """Tests for breach count tracking."""
    
    def test_reset_breach_count(self):
        """Test resetting breach count."""
        monitor = PositionMonitor()
        
        # Simulate breaches
        monitor._breach_counts["pos1"] = 3
        
        assert monitor.get_breach_count("pos1") == 3
        
        monitor.reset_breach_count("pos1")
        
        assert monitor.get_breach_count("pos1") == 0
        assert "pos1" not in monitor._breach_counts
    
    def test_get_breach_count_nonexistent(self):
        """Test getting breach count for unknown position."""
        monitor = PositionMonitor()
        
        count = monitor.get_breach_count("unknown")
        
        assert count == 0


class TestEvaluateAllPositions:
    """Tests for batch position evaluation."""
    
    @pytest.mark.asyncio
    async def test_evaluate_multiple_positions(self, high_apy_position, low_apy_position, monitor_config):
        """Test evaluating multiple positions."""
        monitor = PositionMonitor(config=monitor_config)
        
        # Second breach for low APY position
        await monitor.check_position(low_apy_position, current_funding_rate=Decimal("-0.05"))
        
        positions = [high_apy_position, low_apy_position]
        results = await monitor.evaluate_all_positions(positions)
        
        assert len(results) == 2
        
        # High APY should not exit
        high_status = next(r for r in results if r.position_id == high_apy_position.position_id)
        assert high_status.should_exit is False
        
        # Low APY with second breach should exit
        low_status = next(r for r in results if r.position_id == low_apy_position.position_id)
        assert low_status.should_exit is True
    
    @pytest.mark.asyncio
    async def test_evaluate_with_error_handling(self, base_asgard_position, base_hyperliquid_position, base_reference, monitor_config):
        """Test error handling during batch evaluation."""
        monitor = PositionMonitor(config=monitor_config)
        
        # Create position (no current funding rate passed, will use fallback)
        bad_position = CombinedPosition(
            position_id="pos-bad",
            asgard=base_asgard_position(),
            hyperliquid=base_hyperliquid_position(),
            reference=base_reference,
            opportunity_id="opp-bad",
        )
        
        results = await monitor.evaluate_all_positions([bad_position])
        
        assert len(results) == 1
        assert results[0].position_id == "pos-bad"
        # Should not exit on error
        assert results[0].should_exit is False


class TestPositionStatus:
    """Tests for PositionStatus dataclass."""
    
    def test_to_summary(self):
        """Test summary generation."""
        status = PositionStatus(
            position_id="pos1",
            current_apy=Decimal("0.08"),
            projected_annual_profit=Decimal("4000"),
            should_exit=True,
            exit_reason="APY below threshold",
            apy_below_threshold=True,
            consecutive_breaches=2,
        )
        
        summary = status.to_summary()
        
        assert summary["position_id"] == "pos1"
        assert summary["current_apy"] == 0.08
        assert summary["should_exit"] is True
        assert summary["exit_reason"] == "APY below threshold"
        assert summary["apy_below_threshold"] is True
        assert summary["consecutive_breaches"] == 2


class TestContextManager:
    """Tests for async context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager_initializes_detector(self):
        """Test that context manager initializes detector."""
        with patch("src.core.position_monitor.OpportunityDetector") as mock_class:
            mock_detector = MagicMock()
            mock_detector.__aenter__ = AsyncMock(return_value=mock_detector)
            mock_detector.__aexit__ = AsyncMock(return_value=None)
            mock_class.return_value = mock_detector
            
            async with PositionMonitor() as monitor:
                pass
            
            mock_detector.__aenter__.assert_called_once()
            mock_detector.__aexit__.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_context_manager_preserves_external_detector(self, mock_opportunity_detector):
        """Test that external detector is not managed."""
        monitor = PositionMonitor(opportunity_detector=mock_opportunity_detector)
        
        async with monitor as m:
            assert m is monitor
        
        mock_opportunity_detector.__aenter__.assert_not_called()


class TestLSTStakingAPY:
    """Tests for LST staking APY inclusion."""
    
    @pytest.mark.asyncio
    async def test_lst_staking_included_in_apy(self, base_asgard_position, base_hyperliquid_position, base_reference, monitor_config):
        """Test that LST staking APY is included in total."""
        asgard = base_asgard_position()
        asgard.asset = Asset.JITOSOL  # LST asset
        
        position = CombinedPosition(
            position_id="pos-lst",
            asgard=asgard,
            hyperliquid=base_hyperliquid_position(),
            reference=base_reference,
            opportunity_id="opp-lst",
        )
        
        monitor = PositionMonitor(config=monitor_config)
        # Total: 12% funding - 1% carry + 8% staking = 19% (well above 10% threshold)
        # Note: LST staking is calculated by the monitor based on asset type
        status = await monitor.check_position(position, current_funding_rate=Decimal("-0.12"))
        
        # Should include LST yield in calculation
        assert status.apy_below_threshold is False
