"""
Tests for Position Manager.

These tests verify:
- Pre-flight checks (all 6 checks)
- Position opening flow (Asgard first, then Hyperliquid)
- Position closing flow (Hyperliquid first, then Asgard)
- Delta calculation with LST appreciation
- Rebalance logic (cost-benefit analysis)
- Error handling and recovery
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config.assets import Asset
from bot.core.position_manager import (
    PositionManager,
    PreflightResult,
    DeltaInfo,
    RebalanceResult,
    PositionManagerResult,
)
from shared.models.common import Protocol, ExitReason
from shared.models.opportunity import ArbitrageOpportunity, OpportunityScore
from shared.models.funding import FundingRate, AsgardRates
from shared.models.position import (
    AsgardPosition,
    HyperliquidPosition,
    CombinedPosition,
    PositionReference
)


class TestPreflightChecks:
    """Tests for pre-flight check functionality."""
    
    @pytest.fixture
    def mock_opportunity(self):
        """Create a mock opportunity."""
        return ArbitrageOpportunity(
            id="test-opp-1",
            asset=Asset.SOL,
            selected_protocol=Protocol.MARGINFI,
            asgard_rates=AsgardRates(
                protocol_id=0,
                token_a_mint="So11111111111111111111111111111111111111112",
                token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                token_a_lending_apy=Decimal("0.05"),
                token_b_borrowing_apy=Decimal("0.08"),
                token_b_max_borrow_capacity=Decimal("1000000"),
            ),
            current_funding=FundingRate(
                timestamp=datetime.utcnow(),
                coin="SOL",
                rate_8hr=Decimal("-0.0001"),
            ),
            predicted_funding=FundingRate(
                timestamp=datetime.utcnow(),
                coin="SOL",
                rate_8hr=Decimal("-0.0001"),
            ),
            funding_volatility=Decimal("0.1"),
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("10000"),
            position_size_usd=Decimal("30000"),
            score=OpportunityScore(
                funding_apy=Decimal("0.10"),
                net_carry_apy=Decimal("-0.01"),
            ),
            price_deviation=Decimal("0.001"),
            preflight_checks_passed=False,
        )
    
    @pytest.mark.asyncio
    async def test_preflight_all_checks_pass(self, mock_opportunity):
        """Test all pre-flight checks passing."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient') as mock_solana, \
             patch('bot.core.position_manager.ArbitrumClient') as mock_arbitrum:

            # Setup mocks
            mock_consensus_instance = AsyncMock()
            mock_consensus_instance.check_consensus = AsyncMock(return_value=MagicMock(
                is_within_threshold=True,
                price_deviation=Decimal("0.001"),
            ))
            mock_consensus.return_value = mock_consensus_instance

            mock_solana_instance = AsyncMock()
            mock_solana_instance.get_balance = AsyncMock(return_value=1.0)
            mock_solana_instance.get_token_balance = AsyncMock(return_value=10000)
            mock_solana.return_value = mock_solana_instance

            mock_arbitrum_instance = AsyncMock()
            mock_arbitrum_instance.get_balance = AsyncMock(return_value=Decimal("0.1"))
            mock_arbitrum_instance.get_usdc_balance = AsyncMock(return_value=Decimal("5000"))
            mock_arbitrum.return_value = mock_arbitrum_instance

            mock_asgard_instance = AsyncMock()
            mock_asgard.return_value = mock_asgard_instance

            mock_hl_instance = AsyncMock()
            mock_hl_instance.get_deposited_balance = AsyncMock(return_value=10000.0)
            mock_hl.return_value = mock_hl_instance

            async with PositionManager() as manager:
                result = await manager.run_preflight_checks(mock_opportunity)

                assert result.passed is True
                assert result.all_checks_passed is True
                assert len(result.errors) == 0
                assert mock_opportunity.preflight_checks_passed is True
    
    @pytest.mark.asyncio
    async def test_preflight_price_deviation_fail(self, mock_opportunity):
        """Test pre-flight failing on price deviation."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient') as mock_solana, \
             patch('bot.core.position_manager.ArbitrumClient') as mock_arbitrum:

            # Setup mocks with price deviation failure
            mock_consensus_instance = AsyncMock()
            mock_consensus_instance.check_consensus = AsyncMock(return_value=MagicMock(
                is_within_threshold=False,
                price_deviation=Decimal("0.01"),  # 1% deviation
            ))
            mock_consensus.return_value = mock_consensus_instance

            mock_solana_instance = AsyncMock()
            mock_solana_instance.get_balance = AsyncMock(return_value=1.0)
            mock_solana_instance.get_token_balance = AsyncMock(return_value=10000)
            mock_solana.return_value = mock_solana_instance

            mock_arbitrum_instance = AsyncMock()
            mock_arbitrum_instance.get_balance = AsyncMock(return_value=Decimal("0.1"))
            mock_arbitrum_instance.get_usdc_balance = AsyncMock(return_value=Decimal("5000"))
            mock_arbitrum.return_value = mock_arbitrum_instance

            mock_asgard.return_value = AsyncMock()
            mock_hl_instance = AsyncMock()
            mock_hl_instance.get_deposited_balance = AsyncMock(return_value=10000.0)
            mock_hl.return_value = mock_hl_instance

            async with PositionManager() as manager:
                result = await manager.run_preflight_checks(mock_opportunity)

                assert result.passed is False
                assert result.checks["price_consensus"] is False
                assert any("deviation" in e.lower() for e in result.errors)
    
    @pytest.mark.asyncio
    async def test_preflight_funding_validation_fail(self, mock_opportunity):
        """Test pre-flight failing on funding rate validation."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient') as mock_solana, \
             patch('bot.core.position_manager.ArbitrumClient') as mock_arbitrum:

            # Make funding positive (should fail)
            mock_opportunity.current_funding.rate_8hr = Decimal("0.0001")

            mock_consensus_instance = AsyncMock()
            mock_consensus_instance.check_consensus = AsyncMock(return_value=MagicMock(
                is_within_threshold=True,
                price_deviation=Decimal("0.001"),
            ))
            mock_consensus.return_value = mock_consensus_instance

            mock_solana_instance = AsyncMock()
            mock_solana_instance.get_balance = AsyncMock(return_value=1.0)
            mock_solana_instance.get_token_balance = AsyncMock(return_value=10000)
            mock_solana.return_value = mock_solana_instance

            mock_arbitrum_instance = AsyncMock()
            mock_arbitrum_instance.get_balance = AsyncMock(return_value=Decimal("0.1"))
            mock_arbitrum_instance.get_usdc_balance = AsyncMock(return_value=Decimal("5000"))
            mock_arbitrum.return_value = mock_arbitrum_instance

            mock_asgard.return_value = AsyncMock()
            mock_hl_instance = AsyncMock()
            mock_hl_instance.get_deposited_balance = AsyncMock(return_value=10000.0)
            mock_hl.return_value = mock_hl_instance

            async with PositionManager() as manager:
                result = await manager.run_preflight_checks(mock_opportunity)

                assert result.passed is False
                assert result.checks["funding_validation"] is False


class TestPositionOpening:
    """Tests for position opening flow."""
    
    @pytest.fixture
    def mock_opportunity(self):
        """Create a mock opportunity."""
        return ArbitrageOpportunity(
            id="test-opp-1",
            asset=Asset.SOL,
            selected_protocol=Protocol.MARGINFI,
            asgard_rates=AsgardRates(
                protocol_id=0,
                token_a_mint="So11111111111111111111111111111111111111112",
                token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                token_a_lending_apy=Decimal("0.05"),
                token_b_borrowing_apy=Decimal("0.08"),
                token_b_max_borrow_capacity=Decimal("1000000"),
            ),
            current_funding=FundingRate(
                timestamp=datetime.utcnow(),
                coin="SOL",
                rate_8hr=Decimal("-0.0001"),
            ),
            funding_volatility=Decimal("0.1"),
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("10000"),
            position_size_usd=Decimal("30000"),
            score=OpportunityScore(
                funding_apy=Decimal("0.10"),
                net_carry_apy=Decimal("-0.01"),
            ),
            price_deviation=Decimal("0.001"),
            preflight_checks_passed=True,
        )
    
    @pytest.fixture
    def mock_asgard_position(self):
        """Create a mock Asgard position."""
        return AsgardPosition(
            position_pda="testpda123",
            intent_id="intent123",
            asset=Asset.SOL,
            protocol=Protocol.MARGINFI,
            collateral_usd=Decimal("5000"),
            position_size_usd=Decimal("15000"),
            leverage=Decimal("3"),
            token_a_amount=Decimal("150"),
            token_b_borrowed=Decimal("10000"),
            entry_price_token_a=Decimal("100"),
            current_health_factor=Decimal("0.25"),
            current_token_a_price=Decimal("100"),
        )
    
    @pytest.fixture
    def mock_hyperliquid_position(self):
        """Create a mock Hyperliquid position."""
        return HyperliquidPosition(
            coin="SOL",
            size_sol=Decimal("-150"),  # Short
            entry_px=Decimal("100"),
            leverage=Decimal("3"),
            margin_used=Decimal("5000"),
            margin_fraction=Decimal("0.25"),
            account_value=Decimal("10000"),
            mark_px=Decimal("100"),
        )
    
    @pytest.mark.asyncio
    async def test_open_position_success(self, mock_opportunity, mock_asgard_position, mock_hyperliquid_position):
        """Test successful position opening."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard_mgr, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl_trader, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator') as mock_validator, \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            # Setup Asgard mock
            mock_asgard_instance = AsyncMock()
            mock_asgard_instance.open_long_position = AsyncMock(return_value=MagicMock(
                success=True,
                position=mock_asgard_position,
                intent_id="intent123",
                signature="sig123",
            ))
            mock_asgard_instance.close_position = AsyncMock()
            mock_asgard_mgr.return_value = mock_asgard_instance
            
            # Setup Hyperliquid mock
            from bot.venues.hyperliquid.trader import PositionInfo
            mock_hl_instance = AsyncMock()
            mock_hl_instance.update_leverage = AsyncMock()
            mock_hl_instance.open_short = AsyncMock(return_value=MagicMock(
                success=True,
                order_id="order123",
                avg_px="100.0",
            ))
            mock_hl_instance.get_position = AsyncMock(return_value=PositionInfo(
                coin="SOL",
                size=-150.0,
                entry_px=100.0,
                leverage=3,
                margin_used=5000.0,
                margin_fraction=0.25,
                unrealized_pnl=0.0,
            ))
            mock_hl_instance.close_short = AsyncMock()
            mock_hl_trader.return_value = mock_hl_instance
            
            # Setup consensus mock
            mock_consensus_instance = AsyncMock()
            mock_consensus_result = MagicMock()
            mock_consensus_result.asgard_price = Decimal("100")
            mock_consensus_result.hyperliquid_price = Decimal("100")
            mock_consensus_result.consensus_price = Decimal("100")
            mock_consensus_result.price_deviation = Decimal("0")
            mock_consensus_result.is_within_threshold = True
            mock_consensus_instance.check_consensus = AsyncMock(return_value=mock_consensus_result)
            mock_consensus.return_value = mock_consensus_instance
            
            # Setup validator mock
            mock_validator_instance = AsyncMock()
            mock_validator_instance.validate_fills = AsyncMock(return_value=MagicMock(
                action="proceed",
                reason="Within tolerance",
            ))
            mock_validator.return_value = mock_validator_instance
            
            async with PositionManager() as manager:
                result = await manager.open_position(mock_opportunity)
                
                assert result.success is True
                assert result.position is not None
                assert result.position.asgard.position_pda == "testpda123"
                assert result.position.hyperliquid.size_sol == Decimal("-150")
                assert result.position.status == "open"
                
                # Verify Asgard was opened first
                mock_asgard_instance.open_long_position.assert_called_once()
                
                # Verify Hyperliquid was opened second
                mock_hl_instance.open_short.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_open_position_hyperliquid_fails_unwinds(self, mock_opportunity, mock_asgard_position):
        """Test that Asgard position is unwound if Hyperliquid fails."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard_mgr, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl_trader, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            # Setup Asgard mock
            mock_asgard_instance = AsyncMock()
            mock_asgard_instance.open_long_position = AsyncMock(return_value=MagicMock(
                success=True,
                position=mock_asgard_position,
                intent_id="intent123",
                signature="sig123",
            ))
            mock_asgard_instance.close_position = AsyncMock(return_value=MagicMock(
                success=True,
            ))
            mock_asgard_mgr.return_value = mock_asgard_instance
            
            # Setup Hyperliquid mock to fail
            mock_hl_instance = AsyncMock()
            mock_hl_instance.update_leverage = AsyncMock()
            mock_hl_instance.open_short = AsyncMock(return_value=MagicMock(
                success=False,
                error="Insufficient margin",
            ))
            mock_hl_instance.get_position = AsyncMock(return_value=None)
            mock_hl_trader.return_value = mock_hl_instance
            
            # Setup consensus mock
            mock_consensus_instance = AsyncMock()
            mock_consensus_instance.check_consensus = AsyncMock(return_value=MagicMock(
                asgard_price=Decimal("100"),
                hyperliquid_price=Decimal("100"),
                price_deviation=Decimal("0"),
                is_within_threshold=True,
            ))
            mock_consensus.return_value = mock_consensus_instance
            
            async with PositionManager() as manager:
                result = await manager.open_position(mock_opportunity)
                
                assert result.success is False
                assert "Hyperliquid" in result.error
                assert result.stage == "hyperliquid_open"
                
                # Verify unwind was attempted
                mock_asgard_instance.close_position.assert_called_once_with("testpda123")
    
    @pytest.mark.asyncio
    async def test_open_position_preflight_not_passed(self, mock_opportunity):
        """Test that position opening fails if preflight checks not passed."""
        mock_opportunity.preflight_checks_passed = False
        
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                result = await manager.open_position(mock_opportunity)
                
                assert result.success is False
                assert "preflight" in result.error.lower()


class TestPositionClosing:
    """Tests for position closing flow."""
    
    @pytest.fixture
    def mock_combined_position(self):
        """Create a mock combined position."""
        return CombinedPosition(
            position_id="test-pos-1",
            asgard=AsgardPosition(
                position_pda="testpda123",
                intent_id="intent123",
                asset=Asset.SOL,
                protocol=Protocol.MARGINFI,
                collateral_usd=Decimal("5000"),
                position_size_usd=Decimal("15000"),
                leverage=Decimal("3"),
                token_a_amount=Decimal("150"),
                token_b_borrowed=Decimal("10000"),
                entry_price_token_a=Decimal("100"),
                current_health_factor=Decimal("0.25"),
                current_token_a_price=Decimal("100"),
            ),
            hyperliquid=HyperliquidPosition(
                coin="SOL",
                size_sol=Decimal("-150"),
                entry_px=Decimal("100"),
                leverage=Decimal("3"),
                margin_used=Decimal("5000"),
                margin_fraction=Decimal("0.25"),
                account_value=Decimal("10000"),
                mark_px=Decimal("100"),
            ),
            reference=PositionReference(
                asgard_entry_price=Decimal("100"),
                hyperliquid_entry_price=Decimal("100"),
            ),
            opportunity_id="test-opp-1",
            status="open",
        )
    
    @pytest.mark.asyncio
    async def test_close_position_success(self, mock_combined_position):
        """Test successful position closing."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard_mgr, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl_trader, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            # Setup mocks
            mock_asgard_instance = AsyncMock()
            mock_asgard_instance.close_position = AsyncMock(return_value=MagicMock(
                success=True,
                signature="close_sig",
            ))
            mock_asgard_mgr.return_value = mock_asgard_instance
            
            mock_hl_instance = AsyncMock()
            mock_hl_instance.close_short = AsyncMock(return_value=MagicMock(
                success=True,
                order_id="close_order",
            ))
            mock_hl_trader.return_value = mock_hl_instance
            
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                # Register the position first
                manager._positions[mock_combined_position.position_id] = mock_combined_position
                
                result = await manager.close_position(
                    mock_combined_position.position_id,
                    reason=ExitReason.FUNDING_FLIP
                )
                
                assert result.success is True
                assert result.position.status == "closed"
                assert result.position.exit_reason == ExitReason.FUNDING_FLIP
                assert result.position.exit_time is not None
                
                # Verify Hyperliquid was closed FIRST
                mock_hl_instance.close_short.assert_called_once()
                
                # Verify Asgard was closed second
                mock_asgard_instance.close_position.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_position_not_found(self):
        """Test closing a non-existent position."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                result = await manager.close_position("non-existent-id")
                
                assert result.success is False
                assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_close_position_already_closed(self, mock_combined_position):
        """Test closing an already closed position."""
        mock_combined_position.status = "closed"
        
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                manager._positions[mock_combined_position.position_id] = mock_combined_position
                
                result = await manager.close_position(mock_combined_position.position_id)
                
                assert result.success is False
                assert "not open" in result.error.lower()


class TestDeltaCalculation:
    """Tests for delta calculation and tracking."""
    
    @pytest.fixture
    def mock_neutral_position(self):
        """Create a perfectly neutral position."""
        return CombinedPosition(
            position_id="test-pos-1",
            asgard=AsgardPosition(
                position_pda="testpda123",
                intent_id="intent123",
                asset=Asset.SOL,
                protocol=Protocol.MARGINFI,
                collateral_usd=Decimal("5000"),
                position_size_usd=Decimal("15000"),
                leverage=Decimal("3"),
                token_a_amount=Decimal("150"),
                token_b_borrowed=Decimal("10000"),
                entry_price_token_a=Decimal("100"),
                current_health_factor=Decimal("0.25"),
                current_token_a_price=Decimal("100"),
            ),
            hyperliquid=HyperliquidPosition(
                coin="SOL",
                size_sol=Decimal("-150"),
                entry_px=Decimal("100"),
                leverage=Decimal("3"),
                margin_used=Decimal("5000"),
                margin_fraction=Decimal("0.25"),
                account_value=Decimal("10000"),
                mark_px=Decimal("100"),
            ),
            reference=PositionReference(
                asgard_entry_price=Decimal("100"),
                hyperliquid_entry_price=Decimal("100"),
            ),
            opportunity_id="test-opp-1",
            status="open",
        )
    
    @pytest.fixture
    def mock_lst_position(self):
        """Create a position with LST asset."""
        return CombinedPosition(
            position_id="test-pos-2",
            asgard=AsgardPosition(
                position_pda="testpda456",
                intent_id="intent456",
                asset=Asset.JITOSOL,  # LST asset
                protocol=Protocol.MARGINFI,
                collateral_usd=Decimal("5000"),
                position_size_usd=Decimal("15000"),
                leverage=Decimal("3"),
                token_a_amount=Decimal("138.89"),  # Fewer tokens due to premium
                token_b_borrowed=Decimal("10000"),
                entry_price_token_a=Decimal("108"),  # LST trades at premium
                current_health_factor=Decimal("0.25"),
                current_token_a_price=Decimal("110"),  # Appreciated
            ),
            hyperliquid=HyperliquidPosition(
                coin="SOL",
                size_sol=Decimal("-138.89"),  # Match LST SOL value
                entry_px=Decimal("108"),
                leverage=Decimal("3"),
                margin_used=Decimal("5000"),
                margin_fraction=Decimal("0.25"),
                account_value=Decimal("10000"),
                mark_px=Decimal("100"),  # SOL didn't move as much
            ),
            reference=PositionReference(
                asgard_entry_price=Decimal("108"),
                hyperliquid_entry_price=Decimal("108"),
            ),
            opportunity_id="test-opp-2",
            status="open",
        )
    
    @pytest.mark.asyncio
    async def test_delta_neutral_position(self, mock_neutral_position):
        """Test delta calculation for perfectly neutral position."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                delta = await manager.get_position_delta(mock_neutral_position)
                
                assert delta.delta_usd == Decimal("0")
                assert delta.delta_ratio == Decimal("0")
                assert delta.is_neutral is True
                assert delta.needs_rebalance is False
                assert delta.drift_direction == "neutral"
    
    @pytest.mark.asyncio
    async def test_delta_long_heavy(self, mock_neutral_position):
        """Test delta calculation when long is heavier."""
        # Make long worth more
        mock_neutral_position.asgard.current_token_a_price = Decimal("105")
        
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                delta = await manager.get_position_delta(mock_neutral_position)
                
                # Long value: 150 * 105 = 15750
                # Short value: 150 * 100 = 15000
                # Delta: 15750 - 15000 = 750
                assert delta.delta_usd == Decimal("750")
                assert delta.delta_ratio > 0
                assert delta.drift_direction == "long_heavy"
                assert delta.needs_rebalance is True
    
    @pytest.mark.asyncio
    async def test_lst_appreciation_drift(self, mock_lst_position):
        """Test LST appreciation creates natural delta drift."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                delta = await manager.get_position_delta(mock_lst_position)
                
                # LST appreciated from 108 to 110
                # Appreciation: 138.89 * (110 - 108) = ~277.78
                assert delta.lst_appreciation_usd > 0
                assert delta.effective_delta_usd > delta.delta_usd


class TestRebalanceLogic:
    """Tests for rebalance decision logic."""
    
    @pytest.fixture
    def mock_drifted_position(self):
        """Create a position with significant delta drift."""
        return CombinedPosition(
            position_id="test-pos-1",
            asgard=AsgardPosition(
                position_pda="testpda123",
                intent_id="intent123",
                asset=Asset.SOL,
                protocol=Protocol.MARGINFI,
                collateral_usd=Decimal("5000"),
                position_size_usd=Decimal("15000"),
                leverage=Decimal("3"),
                token_a_amount=Decimal("150"),
                token_b_borrowed=Decimal("10000"),
                entry_price_token_a=Decimal("100"),
                current_health_factor=Decimal("0.25"),
                current_token_a_price=Decimal("110"),  # 10% up, long worth more
            ),
            hyperliquid=HyperliquidPosition(
                coin="SOL",
                size_sol=Decimal("-150"),
                entry_px=Decimal("100"),
                leverage=Decimal("3"),
                margin_used=Decimal("5000"),
                margin_fraction=Decimal("0.25"),
                account_value=Decimal("10000"),
                mark_px=Decimal("100"),  # Short didn't change
            ),
            reference=PositionReference(
                asgard_entry_price=Decimal("100"),
                hyperliquid_entry_price=Decimal("100"),
            ),
            opportunity_id="test-opp-1",
            status="open",
        )
    
    @pytest.mark.asyncio
    async def test_rebalance_not_needed_when_neutral(self, mock_drifted_position):
        """Test no rebalance when position is neutral."""
        # Reset to neutral
        mock_drifted_position.asgard.current_token_a_price = Decimal("100")
        
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                result = await manager.rebalance_if_needed(mock_drifted_position)
                
                assert result.rebalanced is False
                assert "within threshold" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_rebalance_needed_but_not_cost_effective(self, mock_drifted_position):
        """Test rebalance needed but not cost-effective."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                # Mock high rebalance cost - use side_effect to return actual Decimals
                manager._calculate_rebalance_cost = lambda pos: Decimal("1000")
                manager._calculate_drift_cost = lambda pos, delta: Decimal("10")
                
                result = await manager.rebalance_if_needed(mock_drifted_position)
                
                assert result.rebalanced is False
                assert "drift cost" in result.reason.lower()
                assert result.drift_cost is not None
                assert result.rebalance_cost is not None


class TestPositionTracking:
    """Tests for position tracking and retrieval."""
    
    @pytest.fixture
    def mock_positions(self):
        """Create multiple mock positions."""
        open_pos = CombinedPosition(
            position_id="open-pos",
            asgard=AsgardPosition(
                position_pda="pda1",
                intent_id="intent1",
                asset=Asset.SOL,
                protocol=Protocol.MARGINFI,
                collateral_usd=Decimal("5000"),
                position_size_usd=Decimal("15000"),
                leverage=Decimal("3"),
                token_a_amount=Decimal("150"),
                token_b_borrowed=Decimal("10000"),
                entry_price_token_a=Decimal("100"),
                current_health_factor=Decimal("0.25"),
                current_token_a_price=Decimal("100"),
            ),
            hyperliquid=HyperliquidPosition(
                coin="SOL",
                size_sol=Decimal("-150"),
                entry_px=Decimal("100"),
                leverage=Decimal("3"),
                margin_used=Decimal("5000"),
                margin_fraction=Decimal("0.25"),
                account_value=Decimal("10000"),
                mark_px=Decimal("100"),
            ),
            reference=PositionReference(
                asgard_entry_price=Decimal("100"),
                hyperliquid_entry_price=Decimal("100"),
            ),
            opportunity_id="opp1",
            status="open",
        )
        closed_pos = CombinedPosition(
            position_id="closed-pos",
            asgard=AsgardPosition(
                position_pda="pda2",
                intent_id="intent2",
                asset=Asset.SOL,
                protocol=Protocol.MARGINFI,
                collateral_usd=Decimal("5000"),
                position_size_usd=Decimal("15000"),
                leverage=Decimal("3"),
                token_a_amount=Decimal("150"),
                token_b_borrowed=Decimal("10000"),
                entry_price_token_a=Decimal("100"),
                current_health_factor=Decimal("0.25"),
                current_token_a_price=Decimal("100"),
            ),
            hyperliquid=HyperliquidPosition(
                coin="SOL",
                size_sol=Decimal("-150"),
                entry_px=Decimal("100"),
                leverage=Decimal("3"),
                margin_used=Decimal("5000"),
                margin_fraction=Decimal("0.25"),
                account_value=Decimal("10000"),
                mark_px=Decimal("100"),
            ),
            reference=PositionReference(
                asgard_entry_price=Decimal("100"),
                hyperliquid_entry_price=Decimal("100"),
            ),
            opportunity_id="opp2",
            status="closed",
        )
        return {"open": open_pos, "closed": closed_pos}
    
    @pytest.mark.asyncio
    async def test_get_position(self, mock_positions):
        """Test retrieving a specific position."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                manager._positions = {
                    mock_positions["open"].position_id: mock_positions["open"],
                    mock_positions["closed"].position_id: mock_positions["closed"],
                }
                
                # Get existing position
                pos = manager.get_position("open-pos")
                assert pos is not None
                assert pos.position_id == "open-pos"
                
                # Get non-existent position
                pos = manager.get_position("non-existent")
                assert pos is None
    
    @pytest.mark.asyncio
    async def test_get_open_positions(self, mock_positions):
        """Test filtering for open positions only."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient'), \
             patch('bot.core.position_manager.ArbitrumClient'):
            
            mock_asgard.return_value = AsyncMock()
            mock_hl.return_value = AsyncMock()
            mock_consensus.return_value = AsyncMock()
            
            async with PositionManager() as manager:
                manager._positions = {
                    mock_positions["open"].position_id: mock_positions["open"],
                    mock_positions["closed"].position_id: mock_positions["closed"],
                }
                
                open_positions = manager.get_open_positions()
                assert len(open_positions) == 1
                assert open_positions[0].status == "open"


class TestPositionManagerLifecycle:
    """Tests for full position lifecycle."""
    
    @pytest.mark.asyncio
    async def test_context_manager_initialization(self):
        """Test that context manager properly initializes components."""
        with patch('bot.core.position_manager.AsgardPositionManager') as mock_asgard, \
             patch('bot.core.position_manager.HyperliquidTrader') as mock_hl, \
             patch('bot.core.position_manager.PriceConsensus') as mock_consensus, \
             patch('bot.core.position_manager.FillValidator'), \
             patch('bot.core.position_manager.SolanaClient') as mock_solana, \
             patch('bot.core.position_manager.ArbitrumClient') as mock_arbitrum:
            
            mock_asgard.return_value = MagicMock()
            mock_hl.return_value = MagicMock()
            mock_consensus.return_value = MagicMock()
            mock_solana.return_value = MagicMock()
            mock_arbitrum.return_value = MagicMock()
            
            async with PositionManager() as manager:
                assert manager.asgard_manager is not None
                assert manager.hyperliquid_trader is not None
                assert manager.price_consensus is not None
                assert manager.fill_validator is not None
    
    @pytest.mark.asyncio
    async def test_injected_dependencies(self):
        """Test that injected dependencies are used."""
        mock_asgard = MagicMock()
        mock_hl = MagicMock()
        mock_consensus = MagicMock()
        mock_validator = MagicMock()
        mock_solana = MagicMock()
        mock_arbitrum = MagicMock()
        
        manager = PositionManager(
            asgard_manager=mock_asgard,
            hyperliquid_trader=mock_hl,
            price_consensus=mock_consensus,
            fill_validator=mock_validator,
            solana_client=mock_solana,
            arbitrum_client=mock_arbitrum,
        )
        
        assert manager.asgard_manager is mock_asgard
        assert manager.hyperliquid_trader is mock_hl
        assert manager.price_consensus is mock_consensus
        assert manager.fill_validator is mock_validator
        assert manager.solana_client is mock_solana
        assert manager.arbitrum_client is mock_arbitrum


class TestHyperliquidBalancePreflight:
    """Tests for Hyperliquid clearinghouse balance in preflight."""

    @pytest.fixture
    def mock_opportunity(self):
        """Create a mock opportunity with $10k deployed capital."""
        return ArbitrageOpportunity(
            id="test-opp-hl",
            asset=Asset.SOL,
            selected_protocol=Protocol.MARGINFI,
            asgard_rates=AsgardRates(
                protocol_id=0,
                token_a_mint="So11111111111111111111111111111111111111112",
                token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                token_a_lending_apy=Decimal("0.05"),
                token_b_borrowing_apy=Decimal("0.08"),
                token_b_max_borrow_capacity=Decimal("1000000"),
            ),
            current_funding=FundingRate(
                timestamp=datetime.utcnow(),
                coin="SOL",
                rate_8hr=Decimal("-0.0001"),
            ),
            predicted_funding=FundingRate(
                timestamp=datetime.utcnow(),
                coin="SOL",
                rate_8hr=Decimal("-0.0001"),
            ),
            funding_volatility=Decimal("0.1"),
            leverage=Decimal("3"),
            deployed_capital_usd=Decimal("10000"),
            position_size_usd=Decimal("30000"),
            score=OpportunityScore(
                funding_apy=Decimal("0.10"),
                net_carry_apy=Decimal("-0.01"),
            ),
            price_deviation=Decimal("0.001"),
            preflight_checks_passed=False,
        )

    @pytest.mark.asyncio
    async def test_hl_balance_sufficient_no_bridge_needed(self, mock_opportunity):
        """Test preflight passes without bridge when HL has enough."""
        mock_solana = AsyncMock()
        mock_solana.get_balance = AsyncMock(return_value=1.0)
        mock_solana.get_token_balance = AsyncMock(return_value=10000)

        mock_arbitrum = AsyncMock()
        mock_arbitrum.get_balance = AsyncMock(return_value=Decimal("0.1"))
        mock_arbitrum.get_usdc_balance = AsyncMock(return_value=Decimal("5000"))

        mock_hl_trader = AsyncMock()
        mock_hl_trader.get_deposited_balance = AsyncMock(return_value=6000.0)  # > 5000 margin

        mock_consensus = AsyncMock()
        mock_consensus.check_consensus = AsyncMock(return_value=MagicMock(
            is_within_threshold=True,
            price_deviation=Decimal("0.001"),
        ))

        manager = PositionManager(
            asgard_manager=AsyncMock(),
            hyperliquid_trader=mock_hl_trader,
            price_consensus=mock_consensus,
            fill_validator=MagicMock(),
            solana_client=mock_solana,
            arbitrum_client=mock_arbitrum,
        )

        result = await manager.run_preflight_checks(mock_opportunity)

        assert result.checks["wallet_balance"] is True
        assert manager._needs_bridge_deposit is False

    @pytest.mark.asyncio
    async def test_hl_balance_low_arb_usdc_available_sets_bridge_flag(self, mock_opportunity):
        """Test that low HL balance + available Arb USDC sets bridge flag."""
        mock_solana = AsyncMock()
        mock_solana.get_balance = AsyncMock(return_value=1.0)
        mock_solana.get_token_balance = AsyncMock(return_value=10000)

        mock_arbitrum = AsyncMock()
        mock_arbitrum.get_balance = AsyncMock(return_value=Decimal("0.1"))
        mock_arbitrum.get_usdc_balance = AsyncMock(return_value=Decimal("6000"))

        mock_hl_trader = AsyncMock()
        mock_hl_trader.get_deposited_balance = AsyncMock(return_value=100.0)  # Low

        mock_consensus = AsyncMock()
        mock_consensus.check_consensus = AsyncMock(return_value=MagicMock(
            is_within_threshold=True,
            price_deviation=Decimal("0.001"),
        ))

        manager = PositionManager(
            asgard_manager=AsyncMock(),
            hyperliquid_trader=mock_hl_trader,
            price_consensus=mock_consensus,
            fill_validator=MagicMock(),
            solana_client=mock_solana,
            arbitrum_client=mock_arbitrum,
        )

        result = await manager.run_preflight_checks(mock_opportunity)

        assert result.checks["wallet_balance"] is True  # Soft pass
        assert manager._needs_bridge_deposit is True
        assert manager._bridge_deposit_amount > 0

    @pytest.mark.asyncio
    async def test_hl_and_arb_both_low_fails(self, mock_opportunity):
        """Test preflight fails when both HL and Arbitrum USDC are low."""
        mock_solana = AsyncMock()
        mock_solana.get_balance = AsyncMock(return_value=1.0)
        mock_solana.get_token_balance = AsyncMock(return_value=10000)

        mock_arbitrum = AsyncMock()
        mock_arbitrum.get_balance = AsyncMock(return_value=Decimal("0.1"))
        mock_arbitrum.get_usdc_balance = AsyncMock(return_value=Decimal("100"))  # Too low

        mock_hl_trader = AsyncMock()
        mock_hl_trader.get_deposited_balance = AsyncMock(return_value=50.0)  # Also low

        mock_consensus = AsyncMock()
        mock_consensus.check_consensus = AsyncMock(return_value=MagicMock(
            is_within_threshold=True,
            price_deviation=Decimal("0.001"),
        ))

        manager = PositionManager(
            asgard_manager=AsyncMock(),
            hyperliquid_trader=mock_hl_trader,
            price_consensus=mock_consensus,
            fill_validator=MagicMock(),
            solana_client=mock_solana,
            arbitrum_client=mock_arbitrum,
        )

        result = await manager.run_preflight_checks(mock_opportunity)

        assert result.checks["wallet_balance"] is False
        assert any("balance" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_eth_too_low_for_bridge_fails(self, mock_opportunity):
        """Test preflight fails when ETH is below bridge threshold."""
        mock_solana = AsyncMock()
        mock_solana.get_balance = AsyncMock(return_value=1.0)
        mock_solana.get_token_balance = AsyncMock(return_value=10000)

        mock_arbitrum = AsyncMock()
        mock_arbitrum.get_balance = AsyncMock(return_value=Decimal("0.001"))  # Too low

        manager = PositionManager(
            asgard_manager=AsyncMock(),
            hyperliquid_trader=AsyncMock(),
            price_consensus=AsyncMock(),
            fill_validator=MagicMock(),
            solana_client=mock_solana,
            arbitrum_client=mock_arbitrum,
        )

        result = await manager.run_preflight_checks(mock_opportunity)

        assert result.checks["wallet_balance"] is False


class TestAutoBridgeDeposit:
    """Tests for auto-bridge deposit before HL short."""

    @pytest.mark.asyncio
    async def test_auto_deposit_called_when_flag_set(self):
        """Test that depositor is called when _needs_bridge_deposit is True."""
        mock_depositor = AsyncMock()
        mock_depositor.deposit = AsyncMock(return_value=MagicMock(
            success=True,
            deposit_tx_hash="0xbridge",
        ))

        mock_hl_trader = AsyncMock()
        mock_hl_trader.update_leverage = AsyncMock()
        mock_hl_trader.open_short = AsyncMock(return_value=MagicMock(
            success=True,
            order_id="order1",
            avg_px="100.0",
        ))
        mock_hl_trader.get_position = AsyncMock(return_value=MagicMock(
            coin="SOL",
            size=-50.0,
            entry_px=100.0,
            leverage=3,
            margin_used=1666.0,
            margin_fraction=0.25,
            unrealized_pnl=0.0,
        ))

        manager = PositionManager(
            asgard_manager=AsyncMock(),
            hyperliquid_trader=mock_hl_trader,
            fill_validator=MagicMock(),
        )
        manager._depositor = mock_depositor
        manager._needs_bridge_deposit = True
        manager._bridge_deposit_amount = 5000.0

        result = await manager._open_hyperliquid_position(
            position_id="test-pos",
            coin="SOL",
            size_sol=Decimal("50"),
            leverage=3,
        )

        assert result.success is True
        mock_depositor.deposit.assert_called_once_with(5000.0)
        # Flag should be cleared
        assert manager._needs_bridge_deposit is False

    @pytest.mark.asyncio
    async def test_auto_deposit_failure_blocks_short(self):
        """Test that failed bridge deposit prevents opening short."""
        mock_depositor = AsyncMock()
        mock_depositor.deposit = AsyncMock(return_value=MagicMock(
            success=False,
            error="Bridge tx failed",
        ))

        manager = PositionManager(
            asgard_manager=AsyncMock(),
            hyperliquid_trader=AsyncMock(),
            fill_validator=MagicMock(),
        )
        manager._depositor = mock_depositor
        manager._needs_bridge_deposit = True
        manager._bridge_deposit_amount = 5000.0

        result = await manager._open_hyperliquid_position(
            position_id="test-pos",
            coin="SOL",
            size_sol=Decimal("50"),
            leverage=3,
        )

        assert result.success is False
        assert "Bridge deposit failed" in result.error

    @pytest.mark.asyncio
    async def test_no_depositor_when_bridge_needed_fails(self):
        """Test failure when bridge is needed but no depositor configured."""
        manager = PositionManager(
            asgard_manager=AsyncMock(),
            hyperliquid_trader=AsyncMock(),
            fill_validator=MagicMock(),
        )
        manager._needs_bridge_deposit = True
        manager._bridge_deposit_amount = 5000.0
        # No depositor set

        result = await manager._open_hyperliquid_position(
            position_id="test-pos",
            coin="SOL",
            size_sol=Decimal("50"),
            leverage=3,
        )

        assert result.success is False
        assert "no depositor" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_bridge_proceeds_normally(self):
        """Test that short opens normally when no bridge is needed."""
        mock_hl_trader = AsyncMock()
        mock_hl_trader.update_leverage = AsyncMock()
        mock_hl_trader.open_short = AsyncMock(return_value=MagicMock(
            success=True,
            order_id="order1",
            avg_px="100.0",
        ))
        mock_hl_trader.get_position = AsyncMock(return_value=MagicMock(
            coin="SOL",
            size=-50.0,
            entry_px=100.0,
            leverage=3,
            margin_used=1666.0,
            margin_fraction=0.25,
            unrealized_pnl=0.0,
        ))

        manager = PositionManager(
            asgard_manager=AsyncMock(),
            hyperliquid_trader=mock_hl_trader,
            fill_validator=MagicMock(),
        )
        # _needs_bridge_deposit is False by default

        result = await manager._open_hyperliquid_position(
            position_id="test-pos",
            coin="SOL",
            size_sol=Decimal("50"),
            leverage=3,
        )

        assert result.success is True
