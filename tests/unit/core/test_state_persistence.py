"""Tests for State Persistence module."""
import pytest
import json
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.state.persistence import (
    StatePersistence,
    RecoveryResult,
    DecimalEncoder,
    decode_decimal,
)
from src.models.position import CombinedPosition, AsgardPosition, HyperliquidPosition
from src.models.common import Asset, Protocol


def create_test_asgard_position(**kwargs):
    """Helper to create AsgardPosition with defaults."""
    defaults = {
        "position_pda": "test_pda",
        "intent_id": "test_intent",
        "asset": Asset.SOL,
        "protocol": Protocol.MARGINFI,
        "collateral_usd": Decimal("5000"),
        "position_size_usd": Decimal("15000"),
        "leverage": Decimal("3"),
        "token_a_amount": Decimal("50"),
        "token_b_borrowed": Decimal("10000"),
        "entry_price_token_a": Decimal("100"),
        "current_token_a_price": Decimal("100"),
        "current_health_factor": Decimal("0.25"),
    }
    defaults.update(kwargs)
    return AsgardPosition(**defaults)


def create_test_hyperliquid_position(**kwargs):
    """Helper to create HyperliquidPosition with defaults."""
    defaults = {
        "coin": "SOL",
        "size_sol": Decimal("-150"),
        "entry_px": Decimal("100"),
        "leverage": Decimal("3"),
        "margin_used": Decimal("5000"),
        "margin_fraction": Decimal("0.15"),
        "account_value": Decimal("10000"),
        "mark_px": Decimal("100"),
    }
    defaults.update(kwargs)
    return HyperliquidPosition(**defaults)


def create_test_combined_position(**kwargs):
    """Helper to create CombinedPosition with defaults."""
    from src.models.position import PositionReference
    
    defaults = {
        "position_id": "test_pos",
        "asgard": create_test_asgard_position(),
        "hyperliquid": create_test_hyperliquid_position(),
        "reference": PositionReference(
            asgard_entry_price=Decimal("100"),
            hyperliquid_entry_price=Decimal("100"),
        ),
        "opportunity_id": "opp_123",
        "status": "open",
    }
    defaults.update(kwargs)
    return CombinedPosition(**defaults)


@pytest.fixture
async def persistence():
    """Create a StatePersistence instance with in-memory DB."""
    p = StatePersistence(":memory:")
    await p.setup()
    yield p
    await p.close()


class TestStatePersistenceInitialization:
    """Test StatePersistence initialization."""
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test StatePersistence initialization."""
        p = StatePersistence("test.db")
        
        assert p.db_path == "test.db"
        assert p._db is None
    
    @pytest.mark.asyncio
    async def test_setup_creates_tables(self):
        """Test that setup creates database tables."""
        p = StatePersistence(":memory:")
        await p.setup()
        
        # Check that we can query tables
        cursor = await p._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = await cursor.fetchall()
        table_names = [t[0] for t in tables]
        
        assert "positions" in table_names
        assert "action_log" in table_names
        assert "state" in table_names
        
        await p.close()


class TestDecimalEncoder:
    """Test DecimalEncoder functionality."""
    
    def test_encode_decimal(self):
        """Test encoding Decimal values."""
        data = {"value": Decimal("123.456")}
        result = json.dumps(data, cls=DecimalEncoder)
        
        assert "123.456" in result
    
    def test_encode_datetime(self):
        """Test encoding datetime values."""
        now = datetime.utcnow()
        data = {"time": now}
        result = json.dumps(data, cls=DecimalEncoder)
        
        assert now.isoformat() in result
    
    def test_encode_asset(self):
        """Test encoding Asset enum."""
        data = {"asset": Asset.SOL}
        result = json.dumps(data, cls=DecimalEncoder)
        
        assert "SOL" in result


class TestDecodeDecimal:
    """Test decode_decimal function."""
    
    def test_decode_decimal_string(self):
        """Test decoding decimal strings."""
        data = {"value": "123.456"}
        result = decode_decimal(data)
        
        assert isinstance(result["value"], Decimal)
        assert result["value"] == Decimal("123.456")
    
    def test_decode_nested_dict(self):
        """Test decoding nested dictionaries."""
        data = {"nested": {"value": "789.012"}}
        result = decode_decimal(data)
        
        assert isinstance(result["nested"]["value"], Decimal)
    
    def test_decode_list(self):
        """Test decoding lists with decimal strings."""
        data = {"values": ["111.111", "222.222", "not_a_number"]}
        result = decode_decimal(data)
        
        assert isinstance(result["values"][0], Decimal)
        assert isinstance(result["values"][1], Decimal)
        assert result["values"][2] == "not_a_number"


class TestPositionOperations:
    """Test position save/load operations."""
    
    @pytest.mark.asyncio
    async def test_save_and_load_position(self, persistence):
        """Test saving and loading a position."""
        position = create_test_combined_position(
            position_id="combined_pos_123",
        )
        
        # Save
        result = await persistence.save_position(position)
        assert result is True
        
        # Load
        loaded = await persistence.load_positions(include_closed=True)
        assert len(loaded) == 1
        assert loaded[0].position_id == "combined_pos_123"
    
    @pytest.mark.asyncio
    async def test_load_only_active_positions(self, persistence):
        """Test loading only non-closed positions."""
        positions = await persistence.load_positions(include_closed=False)
        assert isinstance(positions, list)
    
    @pytest.mark.asyncio
    async def test_get_position_by_id(self, persistence):
        """Test getting a specific position."""
        position = create_test_combined_position(
            position_id="specific_pos",
        )
        
        await persistence.save_position(position)
        
        # Get specific position
        loaded = await persistence.get_position("specific_pos")
        assert loaded is not None
        assert loaded.position_id == "specific_pos"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_position(self, persistence):
        """Test getting a position that doesn't exist."""
        loaded = await persistence.get_position("nonexistent")
        assert loaded is None
    
    @pytest.mark.asyncio
    async def test_delete_position(self, persistence):
        """Test soft-deleting a position."""
        position = create_test_combined_position(
            position_id="delete_me",
        )
        
        await persistence.save_position(position)
        
        # Delete
        result = await persistence.delete_position("delete_me")
        assert result is True
        
        # Should not appear in active positions
        active = await persistence.load_positions(include_closed=False)
        assert len(active) == 0
        
        # Should still exist in DB (soft delete)
        all_positions = await persistence.load_positions(include_closed=True)
        assert len(all_positions) == 1


class TestActionLog:
    """Test action logging functionality."""
    
    @pytest.mark.asyncio
    async def test_log_action(self, persistence):
        """Test logging an action."""
        action = {
            "type": "position_opened",
            "asset": "SOL",
            "size": Decimal("10000"),
        }
        
        result = await persistence.log_action(action)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_get_audit_log(self, persistence):
        """Test retrieving audit log."""
        # Log some actions
        await persistence.log_action({"type": "action1", "data": "test1"})
        await persistence.log_action({"type": "action2", "data": "test2"})
        
        # Get log
        logs = await persistence.get_audit_log(limit=10)
        
        assert len(logs) == 2
        assert logs[0]["type"] == "action2"  # Most recent first
        assert logs[1]["type"] == "action1"
    
    @pytest.mark.asyncio
    async def test_get_audit_log_with_filter(self, persistence):
        """Test filtering audit log by type."""
        await persistence.log_action({"type": "position_opened", "data": "test1"})
        await persistence.log_action({"type": "position_closed", "data": "test2"})
        await persistence.log_action({"type": "position_opened", "data": "test3"})
        
        # Filter by type
        logs = await persistence.get_audit_log(action_type="position_opened")
        
        assert len(logs) == 2
        for log in logs:
            assert log["type"] == "position_opened"
    
    @pytest.mark.asyncio
    async def test_get_audit_log_with_date_range(self, persistence):
        """Test filtering audit log by date range."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)
        
        await persistence.log_action({"type": "test", "data": "test"})
        
        logs = await persistence.get_audit_log(start=yesterday, end=tomorrow)
        
        assert len(logs) == 1


class TestStateOperations:
    """Test key-value state operations."""
    
    @pytest.mark.asyncio
    async def test_set_and_get_state(self, persistence):
        """Test setting and getting state values."""
        # Set state
        result = await persistence.set_state("test_key", {"value": 123})
        assert result is True
        
        # Get state
        value = await persistence.get_state("test_key")
        assert value == {"value": 123}
    
    @pytest.mark.asyncio
    async def test_get_state_default(self, persistence):
        """Test getting state with default value."""
        value = await persistence.get_state("nonexistent_key", default="default_val")
        assert value == "default_val"
    
    @pytest.mark.asyncio
    async def test_delete_state(self, persistence):
        """Test deleting state."""
        await persistence.set_state("delete_key", "value")
        
        result = await persistence.delete_state("delete_key")
        assert result is True
        
        value = await persistence.get_state("delete_key")
        assert value is None
    
    @pytest.mark.asyncio
    async def test_state_with_decimal(self, persistence):
        """Test storing Decimal values in state."""
        await persistence.set_state("decimal_key", {"value": Decimal("123.456")})
        
        value = await persistence.get_state("decimal_key")
        # Decimal gets serialized to string and back
        assert value["value"] == "123.456"


class TestRecovery:
    """Test recovery functionality."""
    
    @pytest.mark.asyncio
    async def test_recovery_on_startup(self, persistence):
        """Test recovery on startup."""
        # Create and save some positions
        for i in range(3):
            position = create_test_combined_position(
                position_id=f"pos_{i}",
            )
            await persistence.save_position(position)
        
        # Recover
        result = await persistence.recovery_on_startup()
        
        assert result.success is True
        assert result.positions_recovered == 3
    
    @pytest.mark.asyncio
    async def test_recovery_with_no_positions(self, persistence):
        """Test recovery when no positions exist."""
        result = await persistence.recovery_on_startup()
        
        assert result.success is True
        assert result.positions_recovered == 0


class TestHelperMethods:
    """Test helper methods."""
    
    @pytest.mark.asyncio
    async def test_position_to_dict(self, persistence):
        """Test converting position to dict."""
        asgard = create_test_asgard_position(
            position_pda="test_pda",
        )
        
        result = persistence._position_to_dict(asgard)
        
        assert result["type"] == "asgard"
        assert result["position_pda"] == "test_pda"
    
    @pytest.mark.asyncio
    async def test_dict_to_position(self, persistence):
        """Test converting dict to position."""
        data = {
            "position_id": "test_pos",
            "asgard": {
                "position_pda": "pda_123",
                "intent_id": "intent_123",
                "asset": "SOL",
                "protocol": 0,
                "collateral_usd": "5000",
                "token_a_amount": "50",
                "token_b_borrowed": "10000",
                "entry_price_token_a": "100",
                "current_token_a_price": "100",
                "current_health_factor": "0.25",
            },
            "hyperliquid": {
                "coin": "SOL",
                "size_sol": "-150",
                "entry_px": "100",
                "leverage": "3",
                "margin_used": "5000",
                "margin_fraction": "0.15",
                "account_value": "10000",
                "mark_px": "100",
            },
            "reference": {
                "asgard_entry_price": "100",
                "hyperliquid_entry_price": "100",
            },
            "opportunity_id": "opp_123",
            "status": "open",
        }
        
        result = persistence._dict_to_position(data)
        
        assert isinstance(result, CombinedPosition)
        assert result.position_id == "test_pos"
