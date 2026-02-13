"""Integration tests for emergency close scenarios.

Tests emergency exit conditions:
- Health factor approaching liquidation threshold
- LST depeg conditions
- Price deviation beyond threshold
- Chain outages
- Circuit breaker triggers
"""
import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from bot.core.bot import DeltaNeutralBot, BotConfig
from bot.core.risk_engine import ExitReason, RiskLevel, ExitDecision
from bot.core.pause_controller import CircuitBreakerType
from shared.models.position import (
    AsgardPosition, 
    HyperliquidPosition, 
    CombinedPosition,
    PositionReference
)
from shared.models.common import Asset, Protocol


@pytest.fixture
def healthy_position():
    """Create a healthy position for testing."""
    asgard = AsgardPosition(
        position_pda="TestPDA_Healthy",
        intent_id="test_intent_001",
        asset=Asset.SOL,
        protocol=Protocol.MARGINFI,
        collateral_usd=Decimal("5000"),
        position_size_usd=Decimal("15000"),
        leverage=Decimal("3"),
        token_a_amount=Decimal("100"),
        token_b_borrowed=Decimal("10000"),
        entry_price_token_a=Decimal("150"),
        current_health_factor=Decimal("0.25"),  # Healthy
        current_token_a_price=Decimal("150"),
    )
    
    hyperliquid = HyperliquidPosition(
        coin="SOL",
        size_sol=Decimal("-100"),
        entry_px=Decimal("150"),
        leverage=Decimal("3"),
        margin_used=Decimal("5000"),
        margin_fraction=Decimal("0.15"),  # Healthy
        account_value=Decimal("5000"),
        mark_px=Decimal("150"),
    )
    
    return CombinedPosition(
        position_id="test_pos_healthy",
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
def critical_health_position():
    """Create a position with critical health factor."""
    asgard = AsgardPosition(
        position_pda="TestPDA_CriticalHF",
        intent_id="test_intent_002",
        asset=Asset.SOL,
        protocol=Protocol.MARGINFI,
        collateral_usd=Decimal("5000"),
        position_size_usd=Decimal("15000"),
        leverage=Decimal("3"),
        token_a_amount=Decimal("100"),
        token_b_borrowed=Decimal("10000"),
        entry_price_token_a=Decimal("150"),
        current_health_factor=Decimal("0.05"),  # Critical (< 10%)
        current_token_a_price=Decimal("150"),
    )
    
    hyperliquid = HyperliquidPosition(
        coin="SOL",
        size_sol=Decimal("-100"),
        entry_px=Decimal("150"),
        leverage=Decimal("3"),
        margin_used=Decimal("5000"),
        margin_fraction=Decimal("0.15"),
        account_value=Decimal("5000"),
        mark_px=Decimal("150"),
    )
    
    return CombinedPosition(
        position_id="test_pos_critical_hf",
        asgard=asgard,
        hyperliquid=hyperliquid,
        reference=PositionReference(
            asgard_entry_price=Decimal("150"),
            hyperliquid_entry_price=Decimal("150"),
        ),
        opportunity_id="test_opp_002",
        status="open",
    )


@pytest.fixture
def critical_margin_position():
    """Create a position with critical margin fraction."""
    asgard = AsgardPosition(
        position_pda="TestPDA_CriticalMF",
        intent_id="test_intent_003",
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
        size_sol=Decimal("-100"),
        entry_px=Decimal("150"),
        leverage=Decimal("3"),
        margin_used=Decimal("5000"),
        margin_fraction=Decimal("0.05"),  # Critical (< 10%)
        account_value=Decimal("5000"),
        mark_px=Decimal("150"),
    )
    
    return CombinedPosition(
        position_id="test_pos_critical_mf",
        asgard=asgard,
        hyperliquid=hyperliquid,
        reference=PositionReference(
            asgard_entry_price=Decimal("150"),
            hyperliquid_entry_price=Decimal("150"),
        ),
        opportunity_id="test_opp_003",
        status="open",
    )


@pytest.fixture
def lst_position():
    """Create a position with LST asset for depeg testing."""
    asgard = AsgardPosition(
        position_pda="TestPDA_LST",
        intent_id="test_intent_004",
        asset=Asset.JITOSOL,
        protocol=Protocol.KAMINO,
        collateral_usd=Decimal("5000"),
        position_size_usd=Decimal("15000"),
        leverage=Decimal("3"),
        token_a_amount=Decimal("95"),
        token_b_borrowed=Decimal("10000"),
        entry_price_token_a=Decimal("157.89"),
        current_health_factor=Decimal("0.25"),
        current_token_a_price=Decimal("157.89"),
    )
    
    hyperliquid = HyperliquidPosition(
        coin="SOL",
        size_sol=Decimal("-100"),
        entry_px=Decimal("150"),
        leverage=Decimal("3"),
        margin_used=Decimal("5000"),
        margin_fraction=Decimal("0.15"),
        account_value=Decimal("5000"),
        mark_px=Decimal("150"),
    )
    
    return CombinedPosition(
        position_id="test_pos_lst",
        asgard=asgard,
        hyperliquid=hyperliquid,
        reference=PositionReference(
            asgard_entry_price=Decimal("157.89"),
            hyperliquid_entry_price=Decimal("150"),
        ),
        opportunity_id="test_opp_004",
        status="open",
    )


class TestEmergencyHealthFactor:
    """Test emergency close due to health factor."""
    
    @pytest.mark.asyncio
    async def test_emergency_close_critical_health_factor(self, critical_health_position):
        """Test emergency close when health factor is critical."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.HEALTH_FACTOR,
                level=RiskLevel.CRITICAL,
                details={
                    "health_factor": 0.05,
                    "threshold": 0.20,
                }
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Add position using user-scoped structure (user_id -> position_id -> position)
            user_id = critical_health_position.user_id or "default"
            bot._positions[user_id] = {critical_health_position.position_id: critical_health_position}
            
            # Run monitor cycle
            await bot._monitor_position(critical_health_position)
            
            # Verify circuit breaker was triggered
            mock_pause_instance.trigger_circuit_breaker.assert_called_once()
            call_args = mock_pause_instance.trigger_circuit_breaker.call_args
            assert call_args[0][0] == CircuitBreakerType.ASGARD_HEALTH
            
            # Verify position was closed
            assert len(bot._positions) == 0
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_emergency_close_critical_margin_fraction(self, critical_margin_position):
        """Test emergency close when margin fraction is critical."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.MARGIN_FRACTION,
                level=RiskLevel.CRITICAL,
                details={
                    "margin_fraction": 0.05,
                    "threshold": 0.10,
                }
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Add position using user-scoped structure
            user_id = critical_margin_position.user_id or "default"
            bot._positions[user_id] = {critical_margin_position.position_id: critical_margin_position}
            
            # Run monitor cycle
            await bot._monitor_position(critical_margin_position)
            
            # Verify circuit breaker was triggered
            mock_pause_instance.trigger_circuit_breaker.assert_called_once()
            call_args = mock_pause_instance.trigger_circuit_breaker.call_args
            assert call_args[0][0] == CircuitBreakerType.HYPERLIQUID_MARGIN
            
            # Verify position was closed
            assert len(bot._positions) == 0
            
            await bot.shutdown()


class TestEmergencyLSTDepeg:
    """Test emergency close due to LST depeg."""
    
    @pytest.mark.asyncio
    async def test_emergency_close_lst_critical_premium(self, lst_position):
        """Test emergency close when LST has critical premium."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):

            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance

            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.LST_DEPEG,
                level=RiskLevel.CRITICAL,
                details={
                    "premium": 0.06,
                    "threshold": 0.05,
                    "asset": "JITOSOL",
                }
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Add position using user-scoped structure
            user_id = lst_position.user_id or "default"
            bot._positions[user_id] = {lst_position.position_id: lst_position}
            
            # Run monitor cycle
            await bot._monitor_position(lst_position)
            
            # Verify circuit breaker was triggered for LST
            mock_pause_instance.trigger_circuit_breaker.assert_called_once()
            call_args = mock_pause_instance.trigger_circuit_breaker.call_args
            assert call_args[0][0] == CircuitBreakerType.LST_DEPEG
            
            # Verify position was closed
            assert len(bot._positions) == 0
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_emergency_close_lst_critical_discount(self, lst_position):
        """Test emergency close when LST has critical discount."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.LST_DEPEG,
                level=RiskLevel.CRITICAL,
                details={
                    "discount": 0.03,  # > 2% critical threshold
                    "threshold": 0.02,
                    "asset": "JITOSOL",
                }
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Add position using user-scoped structure
            user_id = lst_position.user_id or "default"
            bot._positions[user_id] = {lst_position.position_id: lst_position}
            
            # Run monitor cycle
            await bot._monitor_position(lst_position)
            
            # Verify position was closed
            assert len(bot._positions) == 0
            
            await bot.shutdown()


class TestEmergencyPriceDeviation:
    """Test emergency close due to price deviation."""
    
    @pytest.mark.asyncio
    async def test_emergency_close_price_deviation(self, healthy_position):
        """Test emergency close when price deviation exceeds threshold."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.PRICE_DEVIATION,
                level=RiskLevel.CRITICAL,
                details={
                    "price_deviation": 0.025,  # > 2% threshold
                    "threshold": 0.02,
                }
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Add position using user-scoped structure
            user_id = healthy_position.user_id or "default"
            bot._positions[user_id] = {healthy_position.position_id: healthy_position}
            
            # Run monitor cycle
            await bot._monitor_position(healthy_position)
            
            # Verify position was closed
            assert len(bot._positions) == 0
            
            # Note: PRICE_DEVIATION doesn't trigger circuit breaker (only HEALTH_FACTOR,
            # MARGIN_FRACTION, and LST_DEPEG do per spec 8.4)
            
            await bot.shutdown()


class TestEmergencyChainOutage:
    """Test emergency close due to chain outages."""
    
    @pytest.mark.asyncio
    async def test_emergency_close_solana_outage(self, healthy_position):
        """Test emergency close when Solana is down."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.CHAIN_OUTAGE,
                level=RiskLevel.CRITICAL,
                details={
                    "affected_chain": "solana",
                }
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Add position using user-scoped structure
            user_id = healthy_position.user_id or "default"
            bot._positions[user_id] = {healthy_position.position_id: healthy_position}
            
            # Run monitor cycle
            await bot._monitor_position(healthy_position)
            
            # Verify position was closed
            assert len(bot._positions) == 0
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_emergency_close_arbitrum_outage(self, healthy_position):
        """Test emergency close when Arbitrum is down."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.CHAIN_OUTAGE,
                level=RiskLevel.CRITICAL,
                details={
                    "affected_chain": "arbitrum",
                }
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Add position using user-scoped structure
            user_id = healthy_position.user_id or "default"
            bot._positions[user_id] = {healthy_position.position_id: healthy_position}
            
            # Run monitor cycle
            await bot._monitor_position(healthy_position)
            
            # Verify position was closed
            assert len(bot._positions) == 0
            
            await bot.shutdown()


class TestCircuitBreakerTriggers:
    """Test circuit breaker triggers during emergency."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_triggers_on_critical_exit(self, critical_health_position):
        """Test that circuit breaker is triggered on critical exit conditions."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.HEALTH_FACTOR,
                level=RiskLevel.CRITICAL,
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
                enable_circuit_breakers=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Add position using user-scoped structure
            user_id = critical_health_position.user_id or "default"
            bot._positions[user_id] = {critical_health_position.position_id: critical_health_position}
            
            # Run monitor cycle
            await bot._monitor_position(critical_health_position)
            
            # Verify circuit breaker was triggered with correct type
            mock_pause_instance.trigger_circuit_breaker.assert_called_once()
            args = mock_pause_instance.trigger_circuit_breaker.call_args[0]
            assert args[0] == CircuitBreakerType.ASGARD_HEALTH
            
            await bot.shutdown()


class TestEmergencyExitPriority:
    """Test that emergency exits are prioritized correctly."""
    
    @pytest.mark.asyncio
    async def test_chain_outage_highest_priority(self, healthy_position):
        """Test that chain outage has highest exit priority."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine') as mock_risk_class, \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController') as mock_pause_class, \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            mock_state_instance = AsyncMock()
            mock_state.return_value = mock_state_instance
            
            mock_risk_instance = MagicMock()
            mock_risk_class.return_value = mock_risk_instance
            # Multiple conditions met, but chain outage should be reported
            mock_risk_instance.evaluate_exit_trigger.return_value = ExitDecision(
                should_exit=True,
                reason=ExitReason.CHAIN_OUTAGE,  # Highest priority
                level=RiskLevel.CRITICAL,
            )
            
            mock_pause_instance = MagicMock()
            mock_pause_class.return_value = mock_pause_instance
            mock_pause_instance.check_paused.return_value = False
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(
                admin_api_key="test_key",
                enable_auto_exit=True,
            )
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Add position using user-scoped structure
            user_id = healthy_position.user_id or "default"
            bot._positions[user_id] = {healthy_position.position_id: healthy_position}
            
            # Run monitor cycle
            await bot._monitor_position(healthy_position)
            
            # Verify exit was triggered
            assert len(bot._positions) == 0
            
            # Verify log action was called with chain outage reason
            mock_state_instance.log_action.assert_called_once()
            call_args = mock_state_instance.log_action.call_args[0][0]
            assert call_args["reason"] == ExitReason.CHAIN_OUTAGE.value
            
            await bot.shutdown()
