"""Integration tests for state recovery scenarios.

Tests recovery of bot state after crashes:
- Position recovery on startup
- Incomplete transaction handling
- State persistence across restarts
"""
import pytest
import asyncio
import tempfile
import os
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from bot.core.bot import DeltaNeutralBot, BotConfig
from shared.models.position import (
    AsgardPosition, 
    HyperliquidPosition, 
    CombinedPosition,
    PositionReference
)
from shared.models.common import Asset, Protocol
from bot.state.persistence import StatePersistence, RecoveryResult


@pytest.fixture
def mock_open_position():
    """Create a mock open position."""
    asgard = AsgardPosition(
        position_pda="TestPDA_Recover_001",
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
        size_sol=Decimal("-100"),
        entry_px=Decimal("150"),
        leverage=Decimal("3"),
        margin_used=Decimal("5000"),
        margin_fraction=Decimal("0.15"),
        account_value=Decimal("5000"),
        mark_px=Decimal("150"),
    )
    
    return CombinedPosition(
        position_id="test_pos_recover_001",
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
def mock_closed_position():
    """Create a mock closed position."""
    asgard = AsgardPosition(
        position_pda="TestPDA_Closed_001",
        intent_id="test_intent_002",
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
        margin_fraction=Decimal("0.15"),
        account_value=Decimal("5000"),
        mark_px=Decimal("150"),
    )
    
    return CombinedPosition(
        position_id="test_pos_closed_001",
        asgard=asgard,
        hyperliquid=hyperliquid,
        reference=PositionReference(
            asgard_entry_price=Decimal("150"),
            hyperliquid_entry_price=Decimal("150"),
        ),
        opportunity_id="test_opp_002",
        status="closed",
        exit_time=datetime.utcnow(),
    )


@pytest.fixture
async def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_state.db")
        yield db_path


class TestPositionRecovery:
    """Test recovery of positions on startup."""
    
    @pytest.mark.asyncio
    async def test_recover_single_open_position(self, mock_open_position, temp_db_path):
        """Test recovery of a single open position."""
        
        # First, save a position to the database
        persistence = StatePersistence(db_path=temp_db_path)
        await persistence.setup()
        await persistence.save_position(mock_open_position)
        await persistence.close()
        
        # Now create a new bot and verify it recovers the position
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            # Use the real persistence with the temp db
            real_persistence = StatePersistence(db_path=temp_db_path)
            mock_state.return_value = real_persistence
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Recover state
            await bot._recover_state()
            
            # Verify position was recovered
            assert sum(len(v) for v in bot._positions.values()) == 1
            assert mock_open_position.position_id in bot._positions.get("default", {})

            recovered = bot._positions["default"][mock_open_position.position_id]
            assert recovered.asgard.asset == Asset.SOL
            assert recovered.status == "open"
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_recover_multiple_open_positions(self, temp_db_path):
        """Test recovery of multiple open positions."""
        
        # Create multiple positions
        positions = []
        for i in range(3):
            asgard = AsgardPosition(
                position_pda=f"TestPDA_Multi_{i}",
                intent_id=f"test_intent_multi_{i}",
                asset=Asset.SOL if i == 0 else Asset.JITOSOL,
                protocol=Protocol.MARGINFI if i == 0 else Protocol.KAMINO,
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
                margin_fraction=Decimal("0.15"),
                account_value=Decimal("5000"),
                mark_px=Decimal("150"),
            )
            
            pos = CombinedPosition(
                position_id=f"test_pos_multi_{i}",
                asgard=asgard,
                hyperliquid=hyperliquid,
                reference=PositionReference(
                    asgard_entry_price=Decimal("150"),
                    hyperliquid_entry_price=Decimal("150"),
                ),
                opportunity_id=f"test_opp_multi_{i}",
                status="open",
            )
            positions.append(pos)
        
        # Save positions to database
        persistence = StatePersistence(db_path=temp_db_path)
        await persistence.setup()
        for pos in positions:
            await persistence.save_position(pos)
        await persistence.close()
        
        # Recover positions
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            real_persistence = StatePersistence(db_path=temp_db_path)
            mock_state.return_value = real_persistence
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Recover state
            await bot._recover_state()
            
            # Verify all positions were recovered
            assert sum(len(v) for v in bot._positions.values()) == 3
            all_positions = bot.get_positions()
            for pos in positions:
                assert pos.position_id in all_positions
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_closed_positions_not_recovered(self, mock_closed_position, temp_db_path):
        """Test that closed positions are not recovered."""
        
        # Save a closed position
        persistence = StatePersistence(db_path=temp_db_path)
        await persistence.setup()
        await persistence.save_position(mock_closed_position)
        # Mark as closed
        await persistence.delete_position(mock_closed_position.position_id)
        await persistence.close()
        
        # Try to recover
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            real_persistence = StatePersistence(db_path=temp_db_path)
            mock_state.return_value = real_persistence
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Recover state
            await bot._recover_state()
            
            # Verify closed position was NOT recovered
            assert sum(len(v) for v in bot._positions.values()) == 0
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_recovery_with_mixed_positions(self, mock_open_position, mock_closed_position, temp_db_path):
        """Test recovery with mix of open and closed positions."""
        
        persistence = StatePersistence(db_path=temp_db_path)
        await persistence.setup()
        
        # Save both positions
        await persistence.save_position(mock_open_position)
        await persistence.save_position(mock_closed_position)
        # Mark one as closed
        await persistence.delete_position(mock_closed_position.position_id)
        
        await persistence.close()
        
        # Recover
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            real_persistence = StatePersistence(db_path=temp_db_path)
            mock_state.return_value = real_persistence
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Recover state
            await bot._recover_state()
            
            # Verify only open position was recovered
            assert sum(len(v) for v in bot._positions.values()) == 1
            all_positions = bot.get_positions()
            assert mock_open_position.position_id in all_positions
            assert mock_closed_position.position_id not in all_positions
            
            await bot.shutdown()


class TestPositionPersistence:
    """Test that positions are properly persisted."""
    
    @pytest.mark.asyncio
    async def test_position_saved_on_open(self, mock_open_position, temp_db_path):
        """Test that position is saved to database when opened."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient') as mock_solana, \
             patch('bot.core.bot.ArbitrumClient') as mock_arbitrum, \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer') as mock_sizer, \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            # Use real persistence
            from bot.core.position_sizer import PositionSize, SizingResult
            
            real_persistence = StatePersistence(db_path=temp_db_path)
            mock_state.return_value = real_persistence
            
            mock_solana_instance = AsyncMock()
            mock_solana.return_value = mock_solana_instance
            mock_solana_instance.get_balance = AsyncMock(return_value=1000.0)
            
            mock_arbitrum_instance = AsyncMock()
            mock_arbitrum.return_value = mock_arbitrum_instance
            mock_arbitrum_instance.get_balance = AsyncMock(return_value=1000.0)
            
            mock_sizer_instance = MagicMock()
            mock_sizer.return_value = mock_sizer_instance
            mock_sizer_instance.calculate_position_size.return_value = SizingResult(
                success=True,
                size=PositionSize(
                    per_leg_deployment_usd=Decimal("5000"),
                    position_size_usd=Decimal("15000"),
                    borrowed_usd=Decimal("10000"),
                    leverage=Decimal("3"),
                    deployment_pct_used=Decimal("0.1"),
                ),
                solana_balance_usd=Decimal("50000"),
                hyperliquid_balance_usd=Decimal("50000"),
                limiting_balance_usd=Decimal("50000"),
            )
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.open_position = AsyncMock(return_value=MagicMock(
                success=True,
                position=mock_open_position,
                error=None,
            ))
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Create mock opportunity
            from shared.models.opportunity import ArbitrageOpportunity, OpportunityScore
            from shared.models.funding import FundingRate, AsgardRates
            
            opportunity = ArbitrageOpportunity(
                id="test_opp_save",
                asset=Asset.SOL,
                selected_protocol=Protocol.MARGINFI,
                asgard_rates=AsgardRates(
                    protocol_id=0,
                    token_a_mint="So11111111111111111111111111111111111111112",
                    token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    token_a_lending_apy=Decimal("0.05"),
                    token_b_borrowing_apy=Decimal("0.03"),
                    token_b_max_borrow_capacity=Decimal("1000000"),
                ),
                hyperliquid_coin="SOL",
                current_funding=FundingRate(
                    coin="SOL",
                    rate_8hr=Decimal("-0.0008"),
                    timestamp=datetime.utcnow(),
                ),
                funding_volatility=Decimal("0.1"),
                leverage=Decimal("3"),
                deployed_capital_usd=Decimal("10000"),
                position_size_usd=Decimal("30000"),
                score=OpportunityScore(
                    funding_apy=Decimal("0.25"),
                    net_carry_apy=Decimal("0.08"),
                ),
                price_deviation=Decimal("0.001"),
                preflight_checks_passed=True,
            )
            
            # Execute entry
            await bot._execute_entry(opportunity)
            
            # Verify position was saved
            await bot.shutdown()
            
            # Create new persistence to verify
            persistence2 = StatePersistence(db_path=temp_db_path)
            await persistence2.setup()
            positions = await persistence2.load_positions()
            await persistence2.close()
            
            assert len(positions) == 1
            assert positions[0].position_id == mock_open_position.position_id
    
    @pytest.mark.asyncio
    async def test_position_marked_closed_on_exit(self, mock_open_position, temp_db_path):
        """Test that position is marked as closed in database on exit."""
        
        # First save an open position
        persistence = StatePersistence(db_path=temp_db_path)
        await persistence.setup()
        await persistence.save_position(mock_open_position)
        await persistence.close()
        
        # Now simulate exit
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            real_persistence = StatePersistence(db_path=temp_db_path)
            mock_state.return_value = real_persistence
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            mock_pm_instance.close_position = AsyncMock(return_value=MagicMock(success=True, error=None))
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            bot._positions.setdefault("default", {})[mock_open_position.position_id] = mock_open_position

            # Execute exit
            await bot._execute_exit(mock_open_position, "test_exit")
            
            await bot.shutdown()
            
            # Verify position was marked as closed
            persistence2 = StatePersistence(db_path=temp_db_path)
            await persistence2.setup()
            
            # Open positions should be empty
            open_positions = await persistence2.load_positions(include_closed=False)
            assert len(open_positions) == 0
            
            # Including closed should show the position
            all_positions = await persistence2.load_positions(include_closed=True)
            assert len(all_positions) == 1
            
            await persistence2.close()


class TestStateRecovery:
    """Test general state recovery functionality."""
    
    @pytest.mark.asyncio
    async def test_recovery_on_empty_database(self, temp_db_path):
        """Test recovery when database is empty."""
        
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            real_persistence = StatePersistence(db_path=temp_db_path)
            await real_persistence.setup()  # Create empty database
            await real_persistence.close()
            
            mock_state.return_value = real_persistence
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Recover state
            await bot._recover_state()
            
            # Verify no positions recovered
            assert sum(len(v) for v in bot._positions.values()) == 0
            
            await bot.shutdown()
    
    @pytest.mark.asyncio
    async def test_recovery_preserves_position_state(self, mock_open_position, temp_db_path):
        """Test that recovered positions preserve their state correctly."""
        
        # Save position with specific state
        persistence = StatePersistence(db_path=temp_db_path)
        await persistence.setup()
        await persistence.save_position(mock_open_position)
        await persistence.close()
        
        # Recover and verify state
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            real_persistence = StatePersistence(db_path=temp_db_path)
            mock_state.return_value = real_persistence
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Recover state
            await bot._recover_state()
            
            # Verify position state is preserved
            recovered = bot._positions["default"][mock_open_position.position_id]
            assert recovered.asgard.position_pda == mock_open_position.asgard.position_pda
            assert recovered.asgard.asset == mock_open_position.asgard.asset
            assert recovered.asgard.protocol == mock_open_position.asgard.protocol
            assert recovered.asgard.collateral_usd == mock_open_position.asgard.collateral_usd
            assert recovered.asgard.leverage == mock_open_position.asgard.leverage
            assert recovered.hyperliquid.coin == mock_open_position.hyperliquid.coin
            assert recovered.hyperliquid.size_sol == mock_open_position.hyperliquid.size_sol
            assert recovered.hyperliquid.margin_fraction == mock_open_position.hyperliquid.margin_fraction
            
            await bot.shutdown()


class TestRecoveryWithLSTPositions:
    """Test recovery of LST positions."""
    
    @pytest.mark.asyncio
    async def test_recover_lst_position(self, temp_db_path):
        """Test recovery of LST position (jitoSOL)."""
        
        asgard = AsgardPosition(
            position_pda="TestPDA_LST_Recover",
            intent_id="test_intent_lst",
            asset=Asset.JITOSOL,
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
            size_sol=Decimal("-100"),
            entry_px=Decimal("150"),
            leverage=Decimal("3"),
            margin_used=Decimal("5000"),
            margin_fraction=Decimal("0.15"),
            account_value=Decimal("5000"),
            mark_px=Decimal("150"),
        )
        
        lst_position = CombinedPosition(
            position_id="test_pos_lst_recover",
            asgard=asgard,
            hyperliquid=hyperliquid,
            reference=PositionReference(
                asgard_entry_price=Decimal("157.89"),
                hyperliquid_entry_price=Decimal("150"),
            ),
            opportunity_id="test_opp_lst",
            status="open",
        )
        
        # Save LST position
        persistence = StatePersistence(db_path=temp_db_path)
        await persistence.setup()
        await persistence.save_position(lst_position)
        await persistence.close()
        
        # Recover
        with patch('bot.core.bot.StatePersistence') as mock_state, \
             patch('bot.core.bot.SolanaClient'), \
             patch('bot.core.bot.ArbitrumClient'), \
             patch('bot.core.bot.RiskEngine'), \
             patch('bot.core.bot.PositionSizer'), \
             patch('bot.core.bot.PauseController'), \
             patch('bot.core.bot.PositionManager') as mock_pm_class, \
             patch('bot.core.bot.OpportunityDetector'):
            
            real_persistence = StatePersistence(db_path=temp_db_path)
            mock_state.return_value = real_persistence
            
            mock_pm_instance = AsyncMock()
            mock_pm_class.return_value = mock_pm_instance
            mock_pm_instance.__aenter__ = AsyncMock(return_value=mock_pm_instance)
            mock_pm_instance.__aexit__ = AsyncMock(return_value=None)
            
            config = BotConfig(admin_api_key="test_key")
            bot = DeltaNeutralBot(config=config)
            await bot.setup()
            
            # Recover state
            await bot._recover_state()
            
            # Verify LST position recovered correctly
            assert sum(len(v) for v in bot._positions.values()) == 1
            recovered = bot._positions["default"][lst_position.position_id]
            assert recovered.asgard.asset == Asset.JITOSOL
            assert recovered.asgard.protocol == Protocol.KAMINO
            
            await bot.shutdown()
