"""Tests for LST Correlation Monitor."""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from src.core.lst_monitor import (
    LSTMonitor, 
    PegStatus, 
    PegCheckResult,
    LSTDeltaAdjustment,
)
from src.config.assets import Asset


class TestLSTMonitorInitialization:
    """Test LSTMonitor initialization."""
    
    def test_default_initialization(self):
        """Test LSTMonitor with default thresholds."""
        monitor = LSTMonitor()
        
        assert monitor.warning_premium == Decimal("0.03")   # 3%
        assert monitor.critical_premium == Decimal("0.05")  # 5%
        assert monitor.warning_discount == Decimal("0.01")  # 1%
        assert monitor.critical_discount == Decimal("0.02")  # 2%
    
    def test_custom_initialization(self):
        """Test LSTMonitor with custom thresholds."""
        monitor = LSTMonitor(
            warning_premium=Decimal("0.02"),
            critical_premium=Decimal("0.04"),
            warning_discount=Decimal("0.005"),
            critical_discount=Decimal("0.015"),
        )
        
        assert monitor.warning_premium == Decimal("0.02")
        assert monitor.critical_premium == Decimal("0.04")
        assert monitor.warning_discount == Decimal("0.005")
        assert monitor.critical_discount == Decimal("0.015")
    
    def test_lst_assets_list(self):
        """Test that correct LST assets are monitored."""
        monitor = LSTMonitor()
        
        assert Asset.JITOSOL in monitor.LST_ASSETS
        assert Asset.JUPSOL in monitor.LST_ASSETS
        assert Asset.INF in monitor.LST_ASSETS
        assert Asset.SOL not in monitor.LST_ASSETS


class TestPegCheckNormal:
    """Test normal peg scenarios (within thresholds)."""
    
    def test_lst_at_normal_premium(self):
        """Test LST at normal premium (0.5-2%)."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("102.00"),  # 2% premium
            sol_price_usd=Decimal("100.00"),
        )
        
        assert result.status == PegStatus.NORMAL
        assert result.premium_pct == Decimal("0.02")
        assert result.is_depegged is False
        assert result.is_critical is False
    
    def test_lst_at_small_discount(self):
        """Test LST at small discount (< 1%)."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.JUPSOL,
            lst_price_usd=Decimal("99.50"),  # 0.5% discount
            sol_price_usd=Decimal("100.00"),
        )
        
        assert result.status == PegStatus.NORMAL
        assert result.premium_pct == Decimal("-0.005")
        assert result.is_depegged is False
    
    def test_lst_at_exact_warning_premium(self):
        """Test LST at exactly warning premium threshold."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.INF,
            lst_price_usd=Decimal("103.00"),  # Exactly 3%
            sol_price_usd=Decimal("100.00"),
        )
        
        assert result.status == PegStatus.WARNING
        assert result.premium_pct == Decimal("0.03")
    
    def test_lst_at_exact_warning_discount(self):
        """Test LST at exactly warning discount threshold."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("99.00"),  # Exactly 1% discount
            sol_price_usd=Decimal("100.00"),
        )
        
        assert result.status == PegStatus.WARNING
        assert result.premium_pct == Decimal("-0.01")


class TestPegCheckWarning:
    """Test warning threshold scenarios."""
    
    def test_lst_above_warning_premium(self):
        """Test LST above warning premium (> 3%)."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("104.00"),  # 4% premium
            sol_price_usd=Decimal("100.00"),
        )
        
        assert result.status == PegStatus.WARNING
        assert result.premium_pct == Decimal("0.04")
        assert result.warning_threshold_crossed == "premium"
        assert result.is_depegged is True
        assert result.is_critical is False
    
    def test_lst_above_warning_discount(self):
        """Test LST above warning discount (> 1%)."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.JUPSOL,
            lst_price_usd=Decimal("98.50"),  # 1.5% discount - warning range
            sol_price_usd=Decimal("100.00"),
        )
        
        assert result.status == PegStatus.WARNING
        assert result.premium_pct == Decimal("-0.015")
        assert result.warning_threshold_crossed == "discount"


class TestPegCheckCritical:
    """Test critical threshold scenarios."""
    
    def test_lst_above_critical_premium(self):
        """Test LST above critical premium (> 5%)."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("106.00"),  # 6% premium
            sol_price_usd=Decimal("100.00"),
        )
        
        assert result.status == PegStatus.CRITICAL
        assert result.premium_pct == Decimal("0.06")
        assert result.critical_threshold_crossed == "premium"
        assert result.is_critical is True
    
    def test_lst_above_critical_discount(self):
        """Test LST above critical discount (> 2%)."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.INF,
            lst_price_usd=Decimal("97.00"),  # 3% discount
            sol_price_usd=Decimal("100.00"),
        )
        
        assert result.status == PegStatus.CRITICAL
        assert result.premium_pct == Decimal("-0.03")
        assert result.critical_threshold_crossed == "discount"
        assert result.is_critical is True
    
    def test_lst_at_exact_critical_premium(self):
        """Test LST at exactly critical premium threshold."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.JUPSOL,
            lst_price_usd=Decimal("105.00"),  # Exactly 5%
            sol_price_usd=Decimal("100.00"),
        )
        
        assert result.status == PegStatus.CRITICAL
        assert result.premium_pct == Decimal("0.05")
    
    def test_should_emergency_close_critical(self):
        """Test emergency close decision for critical depeg."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("106.00"),
            sol_price_usd=Decimal("100.00"),
        )
        
        assert monitor.should_emergency_close(result) is True
    
    def test_should_not_emergency_close_warning(self):
        """Test no emergency close for warning level."""
        monitor = LSTMonitor()
        
        result = monitor.check_lst_peg(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("104.00"),  # 4% - warning only
            sol_price_usd=Decimal("100.00"),
        )
        
        assert monitor.should_emergency_close(result) is False


class TestCheckAllLSTPegs:
    """Test checking all LSTs at once."""
    
    def test_check_all_lst_normal(self):
        """Test checking all LSTs when all normal."""
        monitor = LSTMonitor()
        
        prices = {
            Asset.SOL: Decimal("100.00"),
            Asset.JITOSOL: Decimal("102.00"),  # 2% premium
            Asset.JUPSOL: Decimal("101.50"),  # 1.5% premium
            Asset.INF: Decimal("100.50"),     # 0.5% premium
        }
        
        results = monitor.check_all_lst_pegs(prices)
        
        assert len(results) == 3
        assert all(r.status == PegStatus.NORMAL for r in results.values())
    
    def test_check_all_lst_mixed(self):
        """Test checking all LSTs with mixed statuses."""
        monitor = LSTMonitor()
        
        prices = {
            Asset.SOL: Decimal("100.00"),
            Asset.JITOSOL: Decimal("106.00"),  # 6% - critical
            Asset.JUPSOL: Decimal("104.00"),  # 4% - warning
            Asset.INF: Decimal("101.00"),     # 1% - normal
        }
        
        results = monitor.check_all_lst_pegs(prices)
        
        assert results[Asset.JITOSOL].status == PegStatus.CRITICAL
        assert results[Asset.JUPSOL].status == PegStatus.WARNING
        assert results[Asset.INF].status == PegStatus.NORMAL
    
    def test_check_all_missing_sol_price(self):
        """Test error when SOL price missing."""
        monitor = LSTMonitor()
        
        prices = {
            Asset.JITOSOL: Decimal("102.00"),
        }
        
        with pytest.raises(ValueError, match="SOL price required"):
            monitor.check_all_lst_pegs(prices)


class TestEffectiveDeltaCalculation:
    """Test effective delta calculations."""
    
    def test_effective_delta_with_premium(self):
        """Test delta adjustment when LST at premium."""
        monitor = LSTMonitor()
        
        adjustment = monitor.calculate_effective_delta(
            lst_asset=Asset.JITOSOL,
            position_delta_usd=Decimal("10000"),
            lst_price_usd=Decimal("104.00"),  # 4% premium
            sol_price_usd=Decimal("100.00"),
        )
        
        # $10k position at 4% premium = $10k / 1.04 = $9,615 effective
        assert adjustment.adjusted_delta_usd < Decimal("10000")
        assert adjustment.adjustment_usd < 0
        assert "premium" in adjustment.reason.lower()
    
    def test_effective_delta_with_discount(self):
        """Test delta adjustment when LST at discount."""
        monitor = LSTMonitor()
        
        adjustment = monitor.calculate_effective_delta(
            lst_asset=Asset.JUPSOL,
            position_delta_usd=Decimal("10000"),
            lst_price_usd=Decimal("98.00"),  # 2% discount
            sol_price_usd=Decimal("100.00"),
        )
        
        # $10k position at 2% discount = $10k / 0.98 = $10,204 effective
        assert adjustment.adjusted_delta_usd > Decimal("10000")
        assert adjustment.adjustment_usd > 0
        assert "discount" in adjustment.reason.lower()
    
    def test_effective_delta_at_peg(self):
        """Test no adjustment when LST at peg."""
        monitor = LSTMonitor()
        
        adjustment = monitor.calculate_effective_delta(
            lst_asset=Asset.INF,
            position_delta_usd=Decimal("10000"),
            lst_price_usd=Decimal("100.00"),
            sol_price_usd=Decimal("100.00"),
        )
        
        assert adjustment.adjusted_delta_usd == Decimal("10000")
        assert adjustment.adjustment_usd == 0
        assert "at peg" in adjustment.reason.lower()
    
    def test_effective_delta_non_lst(self):
        """Test no adjustment for non-LST assets."""
        monitor = LSTMonitor()
        
        adjustment = monitor.calculate_effective_delta(
            lst_asset=Asset.SOL,  # Not an LST
            position_delta_usd=Decimal("10000"),
            lst_price_usd=Decimal("100.00"),
            sol_price_usd=Decimal("100.00"),
        )
        
        assert adjustment.adjusted_delta_usd == Decimal("10000")
        assert adjustment.adjustment_usd == 0
        assert "is not an lst" in adjustment.reason.lower()
    
    def test_effective_delta_calculation_accuracy(self):
        """Test precise delta adjustment calculation."""
        monitor = LSTMonitor()
        
        # LST at 5% premium
        adjustment = monitor.calculate_effective_delta(
            lst_asset=Asset.JITOSOL,
            position_delta_usd=Decimal("30000"),
            lst_price_usd=Decimal("105.00"),
            sol_price_usd=Decimal("100.00"),
        )
        
        # $30k / 1.05 = $28,571.43
        expected_adjusted = Decimal("30000") / Decimal("1.05")
        assert abs(adjustment.adjusted_delta_usd - expected_adjusted) < Decimal("0.01")


class TestLSTMonitorCallbacks:
    """Test alert callback functionality."""
    
    def test_warning_callback_triggered(self):
        """Test that warning callbacks are triggered."""
        monitor = LSTMonitor()
        callback = MagicMock()
        monitor.add_warning_callback(callback)
        
        monitor.check_lst_peg(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("104.00"),  # Warning level
            sol_price_usd=Decimal("100.00"),
        )
        
        callback.assert_called_once()
        result = callback.call_args[0][0]
        assert result.status == PegStatus.WARNING
    
    def test_critical_callback_triggered(self):
        """Test that critical callbacks are triggered."""
        monitor = LSTMonitor()
        callback = MagicMock()
        monitor.add_critical_callback(callback)
        
        monitor.check_lst_peg(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("106.00"),  # Critical level
            sol_price_usd=Decimal("100.00"),
        )
        
        callback.assert_called_once()
        result = callback.call_args[0][0]
        assert result.status == PegStatus.CRITICAL
    
    def test_no_callback_for_normal(self):
        """Test that no callbacks for normal status."""
        monitor = LSTMonitor()
        warning_callback = MagicMock()
        critical_callback = MagicMock()
        monitor.add_warning_callback(warning_callback)
        monitor.add_critical_callback(critical_callback)
        
        monitor.check_lst_peg(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("101.00"),  # Normal
            sol_price_usd=Decimal("100.00"),
        )
        
        warning_callback.assert_not_called()
        critical_callback.assert_not_called()


class TestPegCheckResultProperties:
    """Test PegCheckResult property methods."""
    
    def test_is_premium_property(self):
        """Test is_premium property."""
        result = PegCheckResult(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("104.00"),
            sol_price_usd=Decimal("100.00"),
            premium_pct=Decimal("0.04"),
            status=PegStatus.WARNING,
        )
        
        assert result.is_premium is True
        assert result.is_discount is False
    
    def test_is_discount_property(self):
        """Test is_discount property."""
        result = PegCheckResult(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("97.00"),
            sol_price_usd=Decimal("100.00"),
            premium_pct=Decimal("-0.03"),
            status=PegStatus.CRITICAL,
        )
        
        assert result.is_premium is False
        assert result.is_discount is True
    
    def test_timestamp_auto_set(self):
        """Test that timestamp is auto-set if not provided."""
        from datetime import datetime
        
        result = PegCheckResult(
            lst_asset=Asset.JITOSOL,
            lst_price_usd=Decimal("100.00"),
            sol_price_usd=Decimal("100.00"),
            premium_pct=Decimal("0"),
            status=PegStatus.NORMAL,
        )
        
        assert result.timestamp is not None
        assert isinstance(result.timestamp, datetime)


class TestLSTAssetValidation:
    """Test LST asset validation."""
    
    def test_is_lst_asset_true(self):
        """Test is_lst_asset returns True for LSTs."""
        monitor = LSTMonitor()
        
        assert monitor.is_lst_asset(Asset.JITOSOL) is True
        assert monitor.is_lst_asset(Asset.JUPSOL) is True
        assert monitor.is_lst_asset(Asset.INF) is True
    
    def test_is_lst_asset_false(self):
        """Test is_lst_asset returns False for non-LSTs."""
        monitor = LSTMonitor()
        
        assert monitor.is_lst_asset(Asset.SOL) is False
    
    def test_non_lst_raises_error(self):
        """Test that checking peg for non-LST raises error."""
        monitor = LSTMonitor()
        
        with pytest.raises(ValueError, match="not an LST"):
            monitor.check_lst_peg(
                lst_asset=Asset.SOL,
                lst_price_usd=Decimal("100.00"),
                sol_price_usd=Decimal("100.00"),
            )


class TestThresholdSummary:
    """Test threshold summary method."""
    
    def test_get_threshold_summary(self):
        """Test getting threshold configuration."""
        monitor = LSTMonitor(
            warning_premium=Decimal("0.025"),
            critical_premium=Decimal("0.055"),
        )
        
        summary = monitor.get_threshold_summary()
        
        assert summary["warning_premium"] == Decimal("0.025")
        assert summary["critical_premium"] == Decimal("0.055")
        assert summary["warning_discount"] == Decimal("0.01")
        assert summary["critical_discount"] == Decimal("0.02")
