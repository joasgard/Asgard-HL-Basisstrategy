"""Tests for Position Sizer module."""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from src.core.position_sizer import PositionSizer, PositionSize, SizingResult


class TestPositionSizerInitialization:
    """Test PositionSizer initialization."""
    
    def test_default_initialization(self):
        """Test PositionSizer with default values."""
        sizer = PositionSizer()
        
        assert sizer.min_position_usd == Decimal("100")
        assert sizer.default_deployment_pct == Decimal("0.10")
        assert sizer.max_deployment_pct == Decimal("0.50")
    
    def test_custom_initialization(self):
        """Test PositionSizer with custom values."""
        sizer = PositionSizer(
            min_position_usd=Decimal("5000"),
            default_deployment_pct=Decimal("0.20"),
            max_deployment_pct=Decimal("0.75"),
            default_leverage=Decimal("3.5"),
            max_leverage=Decimal("4.5"),
        )
        
        assert sizer.min_position_usd == Decimal("5000")
        assert sizer.default_deployment_pct == Decimal("0.20")
        assert sizer.max_deployment_pct == Decimal("0.75")
        assert sizer.default_leverage == Decimal("3.5")
        assert sizer.max_leverage == Decimal("4.5")
    
    @patch('src.core.position_sizer.get_risk_limits')
    def test_initialization_from_risk_config(self, mock_get_risk_limits):
        """Test that leverage values load from risk config."""
        mock_get_risk_limits.return_value = {
            'default_leverage': 2.5,
            'max_leverage': 3.5,
        }
        
        sizer = PositionSizer()
        
        assert sizer.default_leverage == Decimal("2.5")
        assert sizer.max_leverage == Decimal("3.5")


class TestPositionSizingCalculations:
    """Test position size calculations."""
    
    def test_basic_sizing_3x_leverage(self):
        """Test basic position sizing with 3x leverage."""
        sizer = PositionSizer()
        
        # $50k on both chains, 10% deployment, 3x leverage
        result = sizer.calculate_position_size(
            solana_balance_usd=Decimal("50000"),
            hyperliquid_balance_usd=Decimal("50000"),
            deployment_pct=Decimal("0.10"),
            leverage=Decimal("3.0"),
        )
        
        assert result.success is True
        assert result.size is not None
        
        # Limiting balance: $50,000
        # Total deployment: $50,000 × 10% = $5,000
        # Per leg: $5,000 / 2 = $2,500
        # Position size: $2,500 × 3 = $7,500
        # Borrowed: $7,500 - $2,500 = $5,000
        assert result.size.per_leg_deployment_usd == Decimal("2500")
        assert result.size.position_size_usd == Decimal("7500")
        assert result.size.borrowed_usd == Decimal("5000")
        assert result.size.leverage == Decimal("3.0")
    
    def test_sizing_with_imbalanced_wallets(self):
        """Test sizing when wallets have different balances."""
        sizer = PositionSizer()
        
        # Solana has more than Hyperliquid
        result = sizer.calculate_position_size(
            solana_balance_usd=Decimal("100000"),
            hyperliquid_balance_usd=Decimal("30000"),
            deployment_pct=Decimal("0.10"),
            leverage=Decimal("3.0"),
        )
        
        assert result.success is True
        
        # Should use Hyperliquid (limiting chain)
        assert result.limiting_balance_usd == Decimal("30000")
        assert result.size.per_leg_deployment_usd == Decimal("1500")  # $30k × 10% / 2
    
    def test_sizing_with_4x_leverage(self):
        """Test sizing with maximum leverage."""
        sizer = PositionSizer()
        
        result = sizer.calculate_position_size(
            solana_balance_usd=Decimal("100000"),
            hyperliquid_balance_usd=Decimal("100000"),
            deployment_pct=Decimal("0.20"),
            leverage=Decimal("4.0"),
        )
        
        assert result.success is True
        assert result.size.leverage == Decimal("4.0")
        assert result.size.per_leg_deployment_usd == Decimal("10000")  # $100k × 20% / 2
        assert result.size.position_size_usd == Decimal("40000")  # $10k × 4
    
    def test_minimum_position_enforcement(self):
        """Test that minimum position size is enforced."""
        sizer = PositionSizer(min_position_usd=Decimal("1000"))
        
        # Small balance that would create position < $1000 at default deployment
        # But with enough to scale up to minimum
        result = sizer.calculate_position_size(
            solana_balance_usd=Decimal("5000"),
            hyperliquid_balance_usd=Decimal("5000"),
            deployment_pct=Decimal("0.05"),  # 5% would give $750 position
            leverage=Decimal("3.0"),
        )
        
        # Should scale up to minimum
        assert result.success is True
        assert result.size.position_size_usd == Decimal("1000")
        assert result.size.was_capped_by_min is True
    
    def test_minimum_position_insufficient_balance(self):
        """Test failure when minimum position exceeds available balance."""
        sizer = PositionSizer(min_position_usd=Decimal("10000"))
        
        result = sizer.calculate_position_size(
            solana_balance_usd=Decimal("1000"),
            hyperliquid_balance_usd=Decimal("1000"),
            deployment_pct=Decimal("0.50"),  # Max deployment
            leverage=Decimal("4.0"),  # Max leverage
        )
        
        assert result.success is False
        assert "Insufficient balance" in result.error
    
    def test_max_deployment_cap(self):
        """Test that deployment percentage is capped at maximum."""
        sizer = PositionSizer()
        
        result = sizer.calculate_position_size(
            solana_balance_usd=Decimal("100000"),
            hyperliquid_balance_usd=Decimal("100000"),
            deployment_pct=Decimal("0.75"),  # Try to deploy 75%
            leverage=Decimal("3.0"),
        )
        
        assert result.success is True
        # Should be capped at 50%
        assert result.size.deployment_pct_used == Decimal("0.50")
        assert result.size.was_capped_by_max is True
    
    def test_leverage_capped_at_max(self):
        """Test that leverage is capped at maximum."""
        sizer = PositionSizer(max_leverage=Decimal("3.0"))
        
        result = sizer.calculate_position_size(
            solana_balance_usd=Decimal("50000"),
            hyperliquid_balance_usd=Decimal("50000"),
            leverage=Decimal("5.0"),  # Try 5x
        )
        
        assert result.success is True
        assert result.size.leverage == Decimal("3.0")  # Capped
    
    def test_leverage_minimum_one(self):
        """Test that leverage is at least 1x."""
        sizer = PositionSizer()
        
        result = sizer.calculate_position_size(
            solana_balance_usd=Decimal("50000"),
            hyperliquid_balance_usd=Decimal("50000"),
            leverage=Decimal("0.5"),  # Try < 1x
        )
        
        assert result.success is True
        assert result.size.leverage == Decimal("1.0")  # Minimum
    
    def test_negative_balance_rejected(self):
        """Test that negative balances are rejected."""
        sizer = PositionSizer()
        
        result = sizer.calculate_position_size(
            solana_balance_usd=Decimal("-1000"),
            hyperliquid_balance_usd=Decimal("50000"),
        )
        
        assert result.success is False
        assert "negative" in result.error.lower()


class TestCalculateForOpportunity:
    """Test calculate_for_opportunity method."""
    
    def test_calculate_without_target(self):
        """Test calculation without target size (uses default)."""
        sizer = PositionSizer()
        
        result = sizer.calculate_for_opportunity(
            solana_balance_usd=Decimal("50000"),
            hyperliquid_balance_usd=Decimal("50000"),
        )
        
        assert result.success is True
        # Should use default 10% deployment
        assert result.size.deployment_pct_used == Decimal("0.10")
    
    def test_calculate_with_achievable_target(self):
        """Test calculation with achievable target size."""
        sizer = PositionSizer()
        
        # Target $15k position at 3x = $5k per leg = $10k total
        # With $50k balance, need 20% deployment
        result = sizer.calculate_for_opportunity(
            solana_balance_usd=Decimal("50000"),
            hyperliquid_balance_usd=Decimal("50000"),
            target_size_usd=Decimal("15000"),
        )
        
        assert result.success is True
        # Should achieve at least close to target (might be slightly different due to rounding)
        assert result.size.position_size_usd >= Decimal("14000")
    
    def test_calculate_with_unachievable_target(self):
        """Test calculation when target exceeds capacity."""
        sizer = PositionSizer()
        
        # Try to get $1M position with $10k balance
        result = sizer.calculate_for_opportunity(
            solana_balance_usd=Decimal("10000"),
            hyperliquid_balance_usd=Decimal("10000"),
            target_size_usd=Decimal("1000000"),
        )
        
        # Should fall back to max available
        assert result.success is True
        assert result.size.deployment_pct_used == Decimal("0.50")  # Max deployment


class TestMaxPositionSize:
    """Test get_max_position_size method."""
    
    def test_max_size_basic(self):
        """Test getting maximum position size."""
        sizer = PositionSizer()
        
        max_size = sizer.get_max_position_size(
            solana_balance_usd=Decimal("50000"),
            hyperliquid_balance_usd=Decimal("50000"),
            leverage=Decimal("3.0"),
        )
        
        # Max deployment: $50k × 50% = $25k
        # Per leg: $25k / 2 = $12.5k
        # Position: $12.5k × 3 = $37.5k
        assert max_size == Decimal("37500")
    
    def test_max_size_with_limiting_chain(self):
        """Test max size with imbalanced wallets."""
        sizer = PositionSizer()
        
        max_size = sizer.get_max_position_size(
            solana_balance_usd=Decimal("100000"),
            hyperliquid_balance_usd=Decimal("20000"),
            leverage=Decimal("4.0"),
        )
        
        # Limiting: Hyperliquid $20k
        # Max deployment: $20k × 50% = $10k
        # Per leg: $10k / 2 = $5k
        # Position: $5k × 4 = $20k
        assert max_size == Decimal("20000")


class TestCanAffordPosition:
    """Test can_afford_position method."""
    
    def test_can_afford_true(self):
        """Test when position is affordable."""
        sizer = PositionSizer()
        
        can_afford = sizer.can_afford_position(
            solana_balance_usd=Decimal("50000"),
            hyperliquid_balance_usd=Decimal("50000"),
            target_size_usd=Decimal("15000"),  # Needs $5k per leg
            leverage=Decimal("3.0"),
        )
        
        assert can_afford is True
    
    def test_can_afford_false_insufficient_solana(self):
        """Test when Solana balance is insufficient."""
        sizer = PositionSizer()
        
        can_afford = sizer.can_afford_position(
            solana_balance_usd=Decimal("3000"),  # Not enough for $5k
            hyperliquid_balance_usd=Decimal("50000"),
            target_size_usd=Decimal("15000"),
            leverage=Decimal("3.0"),
        )
        
        assert can_afford is False
    
    def test_can_afford_false_insufficient_hyperliquid(self):
        """Test when Hyperliquid balance is insufficient."""
        sizer = PositionSizer()
        
        can_afford = sizer.can_afford_position(
            solana_balance_usd=Decimal("50000"),
            hyperliquid_balance_usd=Decimal("3000"),  # Not enough
            target_size_usd=Decimal("15000"),
            leverage=Decimal("3.0"),
        )
        
        assert can_afford is False
    
    def test_can_afford_false_exceeds_max_deployment(self):
        """Test when position exceeds max deployment percentage."""
        sizer = PositionSizer(max_deployment_pct=Decimal("0.10"))
        
        can_afford = sizer.can_afford_position(
            solana_balance_usd=Decimal("100000"),
            hyperliquid_balance_usd=Decimal("100000"),
            target_size_usd=Decimal("100000"),  # Way too big
            leverage=Decimal("3.0"),
        )
        
        assert can_afford is False


class TestSizingResultProperties:
    """Test SizingResult properties."""
    
    def test_sizing_result_success_case(self):
        """Test successful sizing result."""
        size = PositionSize(
            per_leg_deployment_usd=Decimal("2500"),
            position_size_usd=Decimal("7500"),
            borrowed_usd=Decimal("5000"),
            leverage=Decimal("3.0"),
            deployment_pct_used=Decimal("0.10"),
        )
        
        result = SizingResult(
            success=True,
            size=size,
            solana_balance_usd=Decimal("50000"),
            hyperliquid_balance_usd=Decimal("50000"),
            limiting_balance_usd=Decimal("50000"),
        )
        
        assert result.success is True
        assert result.size.position_size_usd == Decimal("7500")
        assert result.error is None
    
    def test_sizing_result_failure_case(self):
        """Test failed sizing result."""
        result = SizingResult(
            success=False,
            error="Insufficient balance",
            solana_balance_usd=Decimal("500"),
            hyperliquid_balance_usd=Decimal("500"),
        )
        
        assert result.success is False
        assert result.size is None
        assert "Insufficient balance" in result.error
