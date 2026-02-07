"""
Tests for Asgard Position Manager.

These tests verify:
- Position opening flow
- Position closing flow
- Health monitoring
- Protocol selection
- Error handling
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.assets import Asset
from src.models.common import Protocol, TransactionState
from src.venues.asgard.client import AsgardClient
from src.venues.asgard.manager import (
    AsgardPositionManager,
    OpenPositionResult,
    ClosePositionResult,
    HealthStatus,
)
from src.venues.asgard.market_data import NetCarryResult
from src.venues.asgard.transactions import BuildResult, SignResult, SubmitResult


class TestAsgardPositionManagerInit:
    """Tests for position manager initialization."""
    
    def test_init_with_explicit_clients(self):
        """Test initialization with provided clients."""
        client = MagicMock(spec=AsgardClient)
        manager = AsgardPositionManager(client=client)
        assert manager.client is client
    
    def test_init_creates_clients(self):
        """Test that clients are created if not provided."""
        with patch("src.venues.asgard.manager.AsgardClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            
            manager = AsgardPositionManager()
            assert manager.client is mock_instance


class TestOpenLongPosition:
    """Tests for opening positions."""
    
    @pytest.fixture
    def mock_tx_builder(self):
        """Create a mock transaction builder."""
        builder = MagicMock()
        builder.build_create_position = AsyncMock(return_value=BuildResult(
            intent_id="test-intent",
            unsigned_tx=b"unsigned_tx_bytes",
            blockhash="test_blockhash",
            protocol=Protocol.MARGINFI,
        ))
        builder.sign_transaction = AsyncMock(return_value=SignResult(
            intent_id="test-intent",
            signed_tx=b"signed_tx_bytes",
            signature="test_signature_123",
        ))
        builder.submit_transaction = AsyncMock(return_value=SubmitResult(
            intent_id="test-intent",
            signature="test_signature_123",
            confirmed=True,
            slot=123456789,
        ))
        return builder
    
    @pytest.fixture
    def mock_market_data(self):
        """Create mock market data provider."""
        market_data = MagicMock()
        market_data.select_best_protocol = AsyncMock(return_value=NetCarryResult(
            protocol=Protocol.MARGINFI,
            lending_rate=0.05,
            borrowing_rate=0.08,
            net_carry_rate=-0.01,
            net_carry_apy=-0.01,
            leverage=3.0,
            has_capacity=True,
        ))
        return market_data
    
    @pytest.mark.asyncio
    async def test_open_position_success(self, mock_tx_builder, mock_market_data):
        """Test successful position opening."""
        manager = AsgardPositionManager()
        manager.tx_builder = mock_tx_builder
        manager.market_data = mock_market_data
        
        result = await manager.open_long_position(
            asset=Asset.SOL,
            collateral_usd=50000,
            leverage=3.0,
        )
        
        assert result.success is True
        assert result.intent_id is not None
        assert result.signature == "test_signature_123"
        assert result.position is not None
        assert result.position.asset == Asset.SOL
        assert result.position.protocol == Protocol.MARGINFI
        assert result.position.leverage == 3.0
    
    @pytest.mark.asyncio
    async def test_open_position_selects_best_protocol(self, mock_tx_builder, mock_market_data):
        """Test that best protocol is selected when not specified."""
        manager = AsgardPositionManager()
        manager.tx_builder = mock_tx_builder
        manager.market_data = mock_market_data
        
        await manager.open_long_position(
            asset=Asset.SOL,
            collateral_usd=50000,
            leverage=3.0,
        )
        
        mock_market_data.select_best_protocol.assert_called_once_with(
            asset=Asset.SOL,
            size_usd=50000,
            leverage=3.0,
        )
    
    @pytest.mark.asyncio
    async def test_open_position_uses_specified_protocol(self, mock_tx_builder, mock_market_data):
        """Test that specified protocol is used when provided."""
        manager = AsgardPositionManager()
        manager.tx_builder = mock_tx_builder
        manager.market_data = mock_market_data
        
        await manager.open_long_position(
            asset=Asset.SOL,
            collateral_usd=50000,
            leverage=3.0,
            protocol=Protocol.KAMINO,
        )
        
        # Should not call select_best_protocol
        mock_market_data.select_best_protocol.assert_not_called()
        
        # Should use KAMINO in build
        call_args = mock_tx_builder.build_create_position.call_args
        assert call_args.kwargs["protocol"] == Protocol.KAMINO
    
    @pytest.mark.asyncio
    async def test_open_position_no_tx_builder(self, mock_market_data):
        """Test error when transaction builder is not available."""
        manager = AsgardPositionManager()
        manager.tx_builder = None
        manager.market_data = mock_market_data
        
        result = await manager.open_long_position(
            asset=Asset.SOL,
            collateral_usd=50000,
            leverage=3.0,
        )
        
        assert result.success is False
        assert "Transaction builder not available" in result.error
    
    @pytest.mark.asyncio
    async def test_open_position_no_protocol_found(self, mock_tx_builder):
        """Test error when no suitable protocol is found."""
        manager = AsgardPositionManager()
        manager.tx_builder = mock_tx_builder
        manager.market_data = MagicMock()
        manager.market_data.select_best_protocol = AsyncMock(return_value=None)
        
        result = await manager.open_long_position(
            asset=Asset.SOL,
            collateral_usd=50000,
            leverage=3.0,
        )
        
        assert result.success is False
        assert "No suitable protocol found" in result.error
    
    @pytest.mark.asyncio
    async def test_open_position_excessive_leverage(self, mock_tx_builder, mock_market_data):
        """Test error when leverage exceeds maximum."""
        manager = AsgardPositionManager()
        manager.tx_builder = mock_tx_builder
        manager.market_data = mock_market_data
        
        result = await manager.open_long_position(
            asset=Asset.SOL,
            collateral_usd=50000,
            leverage=10.0,  # Excessive
        )
        
        assert result.success is False
        assert "exceeds maximum" in result.error


class TestClosePosition:
    """Tests for closing positions."""
    
    @pytest.fixture
    def mock_tx_builder_close(self):
        """Create a mock transaction builder for close."""
        builder = MagicMock()
        builder.build_close_position = AsyncMock(return_value=BuildResult(
            intent_id="close-intent",
            unsigned_tx=b"unsigned_close_tx",
            blockhash="test_blockhash",
            protocol=Protocol.MARGINFI,
        ))
        builder.sign_transaction = AsyncMock(return_value=SignResult(
            intent_id="close-intent",
            signed_tx=b"signed_close_tx",
            signature="close_signature_123",
        ))
        builder.submit_close_transaction = AsyncMock(return_value=SubmitResult(
            intent_id="close-intent",
            signature="close_signature_123",
            confirmed=True,
            slot=123456790,
        ))
        return builder
    
    @pytest.mark.asyncio
    async def test_close_position_success(self, mock_tx_builder_close):
        """Test successful position closing."""
        manager = AsgardPositionManager()
        manager.tx_builder = mock_tx_builder_close
        
        result = await manager.close_position(
            position_pda="position_pda_123"
        )
        
        assert result.success is True
        assert result.signature == "close_signature_123"
    
    @pytest.mark.asyncio
    async def test_close_position_no_tx_builder(self):
        """Test error when transaction builder is not available."""
        manager = AsgardPositionManager()
        manager.tx_builder = None
        
        result = await manager.close_position(
            position_pda="position_pda_123"
        )
        
        assert result.success is False
        assert "Transaction builder not available" in result.error


class TestMonitorHealth:
    """Tests for health monitoring."""
    
    @pytest.mark.asyncio
    async def test_monitor_health_healthy(self):
        """Test health monitoring for healthy position."""
        manager = AsgardPositionManager()
        
        # Mock get_position_state
        mock_state = MagicMock()
        mock_state.health_factor = 0.25  # Healthy
        manager.get_position_state = AsyncMock(return_value=mock_state)
        
        health = await manager.monitor_health("position_pda_123")
        
        assert health is not None
        assert health.health_factor == 0.25
        assert health.is_healthy is True
        assert health.status == "HEALTHY"
    
    @pytest.mark.asyncio
    async def test_monitor_health_warning(self):
        """Test health monitoring for warning position."""
        manager = AsgardPositionManager()
        
        mock_state = MagicMock()
        mock_state.health_factor = 0.15  # Warning level
        manager.get_position_state = AsyncMock(return_value=mock_state)
        
        health = await manager.monitor_health("position_pda_123")
        
        assert health.status == "WARNING"
        assert health.is_healthy is False
    
    @pytest.mark.asyncio
    async def test_monitor_health_critical(self):
        """Test health monitoring for critical position."""
        manager = AsgardPositionManager()
        
        mock_state = MagicMock()
        mock_state.health_factor = 0.04  # Critical level
        manager.get_position_state = AsyncMock(return_value=mock_state)
        
        health = await manager.monitor_health("position_pda_123")
        
        assert health.status == "CRITICAL"
        assert health.is_healthy is False
    
    @pytest.mark.asyncio
    async def test_monitor_health_position_not_found(self):
        """Test health monitoring when position not found."""
        manager = AsgardPositionManager()
        manager.get_position_state = AsyncMock(return_value=None)
        
        health = await manager.monitor_health("nonexistent_pda")
        
        assert health is None


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""
    
    def test_healthy_status(self):
        """Test HEALTHY status."""
        status = HealthStatus(
            position_pda="test",
            health_factor=0.25,
            is_healthy=True,
            liquidation_proximity=0.0,
        )
        assert status.status == "HEALTHY"
    
    def test_warning_status(self):
        """Test WARNING status."""
        status = HealthStatus(
            position_pda="test",
            health_factor=0.15,
            is_healthy=False,
            liquidation_proximity=0.25,
        )
        assert status.status == "WARNING"
    
    def test_emergency_status(self):
        """Test EMERGENCY status."""
        status = HealthStatus(
            position_pda="test",
            health_factor=0.08,
            is_healthy=False,
            liquidation_proximity=0.6,
        )
        assert status.status == "EMERGENCY"
    
    def test_critical_status(self):
        """Test CRITICAL status."""
        status = HealthStatus(
            position_pda="test",
            health_factor=0.04,
            is_healthy=False,
            liquidation_proximity=0.8,
        )
        assert status.status == "CRITICAL"


class TestGetPositionState:
    """Tests for getting position state."""
    
    @pytest.mark.asyncio
    async def test_get_position_state_success(self):
        """Test successful position state retrieval."""
        manager = AsgardPositionManager()
        
        mock_response = {
            "positions": [
                {
                    "collateralAmount": 1000.0,
                    "borrowAmount": 2000.0,
                    "healthFactor": 0.25,
                }
            ]
        }
        manager.client = MagicMock()
        manager.client._post = AsyncMock(return_value=mock_response)
        
        state = await manager.get_position_state("position_pda_123")
        
        assert state is not None
        assert state.collateral_amount == 1000.0
        assert state.borrow_amount == 2000.0
        assert state.health_factor == 0.25
    
    @pytest.mark.asyncio
    async def test_get_position_state_not_found(self):
        """Test when position is not found."""
        manager = AsgardPositionManager()
        
        mock_response = {"positions": []}
        manager.client = MagicMock()
        manager.client._post = AsyncMock(return_value=mock_response)
        
        state = await manager.get_position_state("nonexistent_pda")
        
        assert state is None
