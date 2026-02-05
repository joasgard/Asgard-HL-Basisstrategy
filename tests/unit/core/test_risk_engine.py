"""Tests for Risk Engine module."""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.core.risk_engine import (
    RiskEngine,
    RiskLevel,
    ExitReason,
    HealthCheckResult,
    MarginCheckResult,
    FundingFlipCheck,
    ExitDecision,
    DeltaDriftResult,
)
from src.models.position import AsgardPosition, HyperliquidPosition, CombinedPosition
from src.config.assets import Asset


@pytest.fixture
def risk_engine():
    """Create a RiskEngine instance."""
    return RiskEngine()


@pytest.fixture
def mock_asgard_position():
    """Create a mock Asgard position."""
    pos = MagicMock(spec=AsgardPosition)
    pos.position_pda = "test_asgard_pda"
    pos.health_factor = Decimal("0.25")
    pos.position_size_usd = Decimal("15000")
    return pos


@pytest.fixture
def mock_hyperliquid_position():
    """Create a mock Hyperliquid position."""
    pos = MagicMock(spec=HyperliquidPosition)
    pos.position_id = "test_hl_position"
    pos.margin_fraction = Decimal("0.15")
    return pos


@pytest.fixture
def mock_combined_position(mock_asgard_position, mock_hyperliquid_position):
    """Create a mock Combined position."""
    pos = MagicMock(spec=CombinedPosition)
    pos.position_id = "test_combined"
    pos.asgard_position = mock_asgard_position
    pos.hyperliquid_position = mock_hyperliquid_position
    return pos


class TestRiskEngineInitialization:
    """Test RiskEngine initialization."""
    
    def test_default_initialization(self):
        """Test RiskEngine with default thresholds."""
        engine = RiskEngine()
        
        assert engine.min_health_factor == Decimal("0.20")
        assert engine.emergency_health_factor == Decimal("0.10")
        assert engine.critical_health_factor == Decimal("0.05")
        assert engine.margin_fraction_threshold == Decimal("0.10")
    
    @patch('src.core.risk_engine.get_risk_limits')
    def test_initialization_from_config(self, mock_get_risk_limits):
        """Test that thresholds load from risk config."""
        mock_get_risk_limits.return_value = {
            'asgard': {
                'min_health_factor': 0.25,
                'emergency_health_factor': 0.12,
                'critical_health_factor': 0.06,
            },
            'hyperliquid': {
                'margin_fraction_threshold': 0.12,
            }
        }
        
        engine = RiskEngine()
        
        assert engine.min_health_factor == Decimal("0.25")
        assert engine.emergency_health_factor == Decimal("0.12")
        assert engine.critical_health_factor == Decimal("0.06")
        assert engine.margin_fraction_threshold == Decimal("0.12")


class TestAsgardHealthFactor:
    """Test Asgard health factor checks."""
    
    def test_healthy_position(self, risk_engine, mock_asgard_position):
        """Test healthy position (HF > min threshold)."""
        result = risk_engine.check_asgard_health(
            mock_asgard_position,
            current_health_factor=Decimal("0.30")
        )
        
        assert result.level == RiskLevel.NORMAL
        assert result.health_factor == Decimal("0.30")
        assert result.is_safe is True
        assert result.should_close is False
    
    def test_warning_position(self, risk_engine, mock_asgard_position):
        """Test warning position (HF between emergency and min)."""
        result = risk_engine.check_asgard_health(
            mock_asgard_position,
            current_health_factor=Decimal("0.15")
        )
        
        assert result.level == RiskLevel.WARNING
        assert result.is_safe is False
        assert result.should_close is False  # Not in proximity yet
    
    def test_emergency_position(self, risk_engine, mock_asgard_position):
        """Test emergency position (HF below emergency)."""
        result = risk_engine.check_asgard_health(
            mock_asgard_position,
            current_health_factor=Decimal("0.08")
        )
        
        assert result.level == RiskLevel.CRITICAL
        assert result.should_close is True
    
    def test_critical_position(self, risk_engine, mock_asgard_position):
        """Test critical position (HF below critical)."""
        result = risk_engine.check_asgard_health(
            mock_asgard_position,
            current_health_factor=Decimal("0.03")
        )
        
        assert result.level == RiskLevel.CRITICAL
        assert result.should_close is True
    
    def test_proximity_warning_triggered(self, risk_engine, mock_asgard_position):
        """Test proximity warning after 20 seconds."""
        # HF at 0.22 - within 20% of 0.20 threshold (proximity = 0.24)
        risk_engine.check_asgard_health(
            mock_asgard_position,
            current_health_factor=Decimal("0.22")
        )
        
        # Simulate time passing
        key = f"asgard_{mock_asgard_position.position_pda}"
        risk_engine._proximity_start_times[key] = datetime.utcnow() - timedelta(seconds=25)
        
        result = risk_engine.check_asgard_health(
            mock_asgard_position,
            current_health_factor=Decimal("0.22")
        )
        
        assert result.in_proximity is True
        assert result.should_close is True  # Proximity for 20s+ triggers close


class TestHyperliquidMargin:
    """Test Hyperliquid margin fraction checks."""
    
    def test_healthy_margin(self, risk_engine, mock_hyperliquid_position):
        """Test healthy margin (MF > threshold)."""
        result = risk_engine.check_hyperliquid_margin(
            mock_hyperliquid_position,
            current_margin_fraction=Decimal("0.20")
        )
        
        assert result.level == RiskLevel.NORMAL
        assert result.margin_fraction == Decimal("0.20")
        assert result.is_safe is True
        assert result.should_close is False
    
    def test_warning_margin(self, risk_engine, mock_hyperliquid_position):
        """Test warning margin (MF below threshold)."""
        result = risk_engine.check_hyperliquid_margin(
            mock_hyperliquid_position,
            current_margin_fraction=Decimal("0.08")
        )
        
        assert result.level == RiskLevel.WARNING
        assert result.is_safe is False
    
    def test_critical_margin(self, risk_engine, mock_hyperliquid_position):
        """Test critical margin (MF way below threshold)."""
        result = risk_engine.check_hyperliquid_margin(
            mock_hyperliquid_position,
            current_margin_fraction=Decimal("0.04")
        )
        
        assert result.level == RiskLevel.CRITICAL
        assert result.should_close is True


class TestFundingFlip:
    """Test funding flip detection."""
    
    def test_no_flip_shorts_still_paid(self, risk_engine):
        """Test when shorts are still being paid."""
        result = risk_engine.check_funding_flip(
            current_funding_annual=Decimal("-0.15"),  # -15% (shorts paid)
            predicted_funding_annual=Decimal("-0.10"),  # Still negative
        )
        
        assert result.flipped is False
        assert result.was_shorts_paid is True
        assert result.now_longs_paid is False
    
    def test_funding_flip_detected(self, risk_engine):
        """Test funding flip from negative to positive."""
        result = risk_engine.check_funding_flip(
            current_funding_annual=Decimal("-0.15"),  # Shorts paid
            predicted_funding_annual=Decimal("0.05"),  # Longs will be paid
        )
        
        assert result.flipped is True
        assert result.was_shorts_paid is True
        assert result.now_longs_paid is True
    
    def test_already_positive_no_flip(self, risk_engine):
        """Test when funding already positive (no position should exist)."""
        result = risk_engine.check_funding_flip(
            current_funding_annual=Decimal("0.10"),  # Longs paid
            predicted_funding_annual=Decimal("0.15"),  # Still positive
        )
        
        assert result.flipped is False
        assert result.was_shorts_paid is False


class TestDeltaDrift:
    """Test delta drift checks."""
    
    def test_normal_delta(self, risk_engine):
        """Test delta within normal range."""
        result = risk_engine.check_delta_drift(
            delta_ratio=Decimal("0.003"),  # 0.3%
        )
        
        assert result.level == RiskLevel.NORMAL
        assert result.should_rebalance is False
    
    def test_warning_delta(self, risk_engine):
        """Test delta at warning level."""
        result = risk_engine.check_delta_drift(
            delta_ratio=Decimal("0.007"),  # 0.7%
        )
        
        assert result.level == RiskLevel.WARNING
    
    def test_critical_delta(self, risk_engine):
        """Test delta at critical level."""
        result = risk_engine.check_delta_drift(
            delta_ratio=Decimal("0.03"),  # 3%
        )
        
        assert result.level == RiskLevel.CRITICAL
        assert result.should_rebalance is True  # Critical always triggers
    
    def test_rebalance_cost_effective(self, risk_engine):
        """Test rebalance when cost-effective."""
        result = risk_engine.check_delta_drift(
            delta_ratio=Decimal("0.01"),
            drift_cost=Decimal("100"),  # $100 cost to hold
            rebalance_cost=Decimal("50"),  # $50 to rebalance
        )
        
        assert result.should_rebalance is True
    
    def test_no_rebalance_when_expensive(self, risk_engine):
        """Test no rebalance when drift cost < rebalance cost."""
        result = risk_engine.check_delta_drift(
            delta_ratio=Decimal("0.01"),
            drift_cost=Decimal("30"),  # $30 cost to hold
            rebalance_cost=Decimal("50"),  # $50 to rebalance
        )
        
        assert result.should_rebalance is False


class TestEvaluateExitTrigger:
    """Test comprehensive exit decision making."""
    
    def test_no_exit_healthy_position(self, risk_engine, mock_combined_position):
        """Test no exit for healthy position."""
        decision = risk_engine.evaluate_exit_trigger(
            mock_combined_position,
            current_health_factor=Decimal("0.30"),
            current_margin_fraction=Decimal("0.20"),
            current_apy=Decimal("0.15"),
        )
        
        assert decision.should_exit is False
    
    def test_exit_chain_outage(self, risk_engine, mock_combined_position):
        """Test immediate exit on chain outage."""
        decision = risk_engine.evaluate_exit_trigger(
            mock_combined_position,
            chain_outage="solana",
        )
        
        assert decision.should_exit is True
        assert decision.reason == ExitReason.CHAIN_OUTAGE
        assert decision.level == RiskLevel.CRITICAL
    
    def test_exit_critical_health_factor(self, risk_engine, mock_combined_position):
        """Test exit on critical health factor."""
        decision = risk_engine.evaluate_exit_trigger(
            mock_combined_position,
            current_health_factor=Decimal("0.04"),  # Below critical
        )
        
        assert decision.should_exit is True
        assert decision.reason == ExitReason.ASGARD_HEALTH_FACTOR
        assert decision.level == RiskLevel.CRITICAL
    
    def test_exit_critical_margin(self, risk_engine, mock_combined_position):
        """Test exit on critical margin fraction."""
        decision = risk_engine.evaluate_exit_trigger(
            mock_combined_position,
            current_margin_fraction=Decimal("0.04"),
        )
        
        assert decision.should_exit is True
        assert decision.reason == ExitReason.HYPERLIQUID_MARGIN
    
    def test_exit_lst_depeg(self, risk_engine, mock_combined_position):
        """Test exit on LST depeg."""
        decision = risk_engine.evaluate_exit_trigger(
            mock_combined_position,
            lst_depegged=True,
        )
        
        assert decision.should_exit is True
        assert decision.reason == ExitReason.LST_DEPEG
    
    def test_exit_price_deviation(self, risk_engine, mock_combined_position):
        """Test exit on excessive price deviation."""
        decision = risk_engine.evaluate_exit_trigger(
            mock_combined_position,
            price_deviation=Decimal("0.025"),  # 2.5% > 2% threshold
        )
        
        assert decision.should_exit is True
        assert decision.reason == ExitReason.PRICE_DEVIATION
    
    def test_exit_negative_apy_cost_effective(self, risk_engine, mock_combined_position):
        """Test exit when APY negative and close cost < expected loss."""
        # Very large position, high negative APY, low close cost
        # -50% APY on $20M position = $10M/year loss = $95/min
        mock_combined_position.asgard_position.position_size_usd = Decimal("20000000")
        
        decision = risk_engine.evaluate_exit_trigger(
            mock_combined_position,
            current_health_factor=Decimal("0.25"),  # Healthy
            current_margin_fraction=Decimal("0.15"),  # Healthy
            current_apy=Decimal("-0.50"),  # -50% APY
            estimated_close_cost=Decimal("50"),  # $50 to close (less than $95 loss)
        )
        
        assert decision.should_exit is True
        assert decision.reason == ExitReason.NEGATIVE_APY
    
    def test_no_exit_negative_apy_expensive(self, risk_engine, mock_combined_position):
        """Test no exit when closing cost > expected loss."""
        # Small position, small negative APY
        mock_combined_position.asgard_position.position_size_usd = Decimal("10000")
        
        decision = risk_engine.evaluate_exit_trigger(
            mock_combined_position,
            current_apy=Decimal("-0.01"),  # -1% APY
            estimated_close_cost=Decimal("100"),  # $100 to close (expensive)
        )
        
        assert decision.should_exit is False
    
    def test_exit_funding_flip(self, risk_engine, mock_combined_position):
        """Test exit on funding flip."""
        decision = risk_engine.evaluate_exit_trigger(
            mock_combined_position,
            current_funding_annual=Decimal("-0.15"),
            predicted_funding_annual=Decimal("0.05"),  # Flipping to positive
        )
        
        assert decision.should_exit is True
        assert decision.reason == ExitReason.FUNDING_FLIP


class TestProximityTracking:
    """Test proximity tracking functionality."""
    
    def test_proximity_start_time_set(self, risk_engine, mock_asgard_position):
        """Test that proximity start time is set when entering proximity."""
        risk_engine.check_asgard_health(
            mock_asgard_position,
            current_health_factor=Decimal("0.22")  # Within proximity
        )
        
        key = f"asgard_{mock_asgard_position.position_pda}"
        assert key in risk_engine._proximity_start_times
        assert risk_engine._proximity_start_times[key] is not None
    
    def test_proximity_cleared_when_healthy(self, risk_engine, mock_asgard_position):
        """Test that proximity tracking is cleared when health improves."""
        key = f"asgard_{mock_asgard_position.position_pda}"
        risk_engine._proximity_start_times[key] = datetime.utcnow()
        
        # Now healthy
        risk_engine.check_asgard_health(
            mock_asgard_position,
            current_health_factor=Decimal("0.30")
        )
        
        assert key not in risk_engine._proximity_start_times
    
    def test_reset_proximity_tracking(self, risk_engine, mock_combined_position):
        """Test manual reset of proximity tracking."""
        pos_id = "test_combined"
        risk_engine._proximity_start_times[f"asgard_{pos_id}"] = datetime.utcnow()
        risk_engine._proximity_start_times[f"hyperliquid_{pos_id}"] = datetime.utcnow()
        
        risk_engine.reset_proximity_tracking(pos_id)
        
        assert f"asgard_{pos_id}" not in risk_engine._proximity_start_times
        assert f"hyperliquid_{pos_id}" not in risk_engine._proximity_start_times


class TestRiskSummary:
    """Test risk summary generation."""
    
    def test_risk_summary_healthy(self, risk_engine, mock_combined_position):
        """Test risk summary for healthy position."""
        summary = risk_engine.get_risk_summary(mock_combined_position)
        
        assert summary["overall_risk"] == "normal"
        assert summary["asgard"]["level"] == "normal"
        assert summary["hyperliquid"]["level"] == "normal"
        assert summary["asgard"]["should_close"] is False
        assert summary["hyperliquid"]["should_close"] is False
    
    def test_risk_summary_with_warning(self, risk_engine, mock_combined_position):
        """Test risk summary with warning conditions."""
        mock_combined_position.asgard_position.health_factor = Decimal("0.15")
        
        summary = risk_engine.get_risk_summary(mock_combined_position)
        
        assert summary["asgard"]["level"] == "warning"
        assert summary["asgard"]["health_factor"] == 0.15


class TestHealthCheckResult:
    """Test HealthCheckResult properties."""
    
    def test_is_safe_property(self):
        """Test is_safe property."""
        normal = HealthCheckResult(
            level=RiskLevel.NORMAL,
            health_factor=Decimal("0.30"),
            threshold=Decimal("0.20"),
            distance_to_liquidation=Decimal("0.30"),
            in_proximity=False,
        )
        assert normal.is_safe is True
        
        warning = HealthCheckResult(
            level=RiskLevel.WARNING,
            health_factor=Decimal("0.15"),
            threshold=Decimal("0.20"),
            distance_to_liquidation=Decimal("0.15"),
            in_proximity=False,
        )
        assert warning.is_safe is False


class TestMarginCheckResult:
    """Test MarginCheckResult properties."""
    
    def test_is_safe_property(self):
        """Test is_safe property."""
        normal = MarginCheckResult(
            level=RiskLevel.NORMAL,
            margin_fraction=Decimal("0.20"),
            threshold=Decimal("0.10"),
            distance_to_threshold=Decimal("0.10"),
            in_proximity=False,
        )
        assert normal.is_safe is True


class TestExitDecision:
    """Test ExitDecision dataclass."""
    
    def test_exit_decision_creation(self):
        """Test ExitDecision creation."""
        decision = ExitDecision(
            should_exit=True,
            reason=ExitReason.ASGARD_HEALTH_FACTOR,
            level=RiskLevel.CRITICAL,
            details={"health_factor": 0.05},
            estimated_close_cost=Decimal("50"),
            expected_loss_if_held=Decimal("100"),
        )
        
        assert decision.should_exit is True
        assert decision.reason == ExitReason.ASGARD_HEALTH_FACTOR
        assert decision.level == RiskLevel.CRITICAL
        assert decision.details["health_factor"] == 0.05
        assert decision.estimated_close_cost == Decimal("50")
        assert decision.expected_loss_if_held == Decimal("100")
        assert decision.timestamp is not None
