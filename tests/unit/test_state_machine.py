"""
Tests for Transaction State Machine.

These tests verify:
- State persistence in SQLite
- Valid state transitions
- Recovery on startup
- Error handling
"""
import os
import tempfile
from pathlib import Path

import pytest

from src.models.common import TransactionState
from src.state.state_machine import StateStore, TransactionStateMachine, TransactionRecord


class TestStateStore:
    """Tests for StateStore SQLite persistence."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        os.unlink(path)
    
    def test_init_creates_database(self, temp_db):
        """Test that initialization creates the database and tables."""
        store = StateStore(db_path=temp_db)
        assert Path(temp_db).exists()
    
    def test_save_and_get_state(self, temp_db):
        """Test saving and retrieving state."""
        store = StateStore(db_path=temp_db)
        
        store.save_state(
            intent_id="test-123",
            state=TransactionState.BUILDING,
            signature="sig123",
            metadata='{"key": "value"}',
        )
        
        record = store.get_state("test-123")
        
        assert record is not None
        assert record.intent_id == "test-123"
        assert record.state == TransactionState.BUILDING
        assert record.signature == "sig123"
        assert record.metadata == '{"key": "value"}'
    
    def test_update_existing_state(self, temp_db):
        """Test that saving updates existing records."""
        store = StateStore(db_path=temp_db)
        
        # Initial save
        store.save_state("test-123", TransactionState.BUILDING)
        
        # Update
        store.save_state(
            "test-123",
            TransactionState.CONFIRMED,
            signature="sig456",
        )
        
        record = store.get_state("test-123")
        assert record.state == TransactionState.CONFIRMED
        assert record.signature == "sig456"
    
    def test_get_state_nonexistent(self, temp_db):
        """Test that getting non-existent state returns None."""
        store = StateStore(db_path=temp_db)
        
        record = store.get_state("does-not-exist")
        assert record is None
    
    def test_get_incomplete_transactions(self, temp_db):
        """Test retrieving incomplete transactions."""
        store = StateStore(db_path=temp_db)
        
        # Create various states
        store.save_state("tx-1", TransactionState.BUILDING)  # Incomplete
        store.save_state("tx-2", TransactionState.SIGNED)    # Incomplete
        store.save_state("tx-3", TransactionState.CONFIRMED) # Complete
        store.save_state("tx-4", TransactionState.FAILED)    # Complete
        store.save_state("tx-5", TransactionState.SUBMITTED) # Incomplete
        
        incomplete = store.get_incomplete_transactions()
        
        intent_ids = {tx.intent_id for tx in incomplete}
        assert intent_ids == {"tx-1", "tx-2", "tx-5"}
    
    def test_get_transactions_by_state(self, temp_db):
        """Test filtering transactions by state."""
        store = StateStore(db_path=temp_db)
        
        store.save_state("tx-1", TransactionState.BUILDING)
        store.save_state("tx-2", TransactionState.BUILDING)
        store.save_state("tx-3", TransactionState.CONFIRMED)
        
        building = store.get_transactions_by_state(TransactionState.BUILDING)
        
        assert len(building) == 2
        assert all(tx.state == TransactionState.BUILDING for tx in building)
    
    def test_delete_transaction(self, temp_db):
        """Test deleting a transaction."""
        store = StateStore(db_path=temp_db)
        
        store.save_state("tx-1", TransactionState.BUILDING)
        assert store.get_state("tx-1") is not None
        
        store.delete_transaction("tx-1")
        assert store.get_state("tx-1") is None


class TestTransactionStateMachine:
    """Tests for TransactionStateMachine."""
    
    @pytest.fixture
    def state_machine(self):
        """Create a state machine with temp database."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store = StateStore(db_path=path)
        sm = TransactionStateMachine(store=store)
        yield sm
        os.unlink(path)
    
    def test_valid_transitions(self, state_machine):
        """Test valid state transitions."""
        # IDLE → BUILDING
        assert state_machine.can_transition(TransactionState.IDLE, TransactionState.BUILDING)
        
        # BUILDING → BUILT
        assert state_machine.can_transition(TransactionState.BUILDING, TransactionState.BUILT)
        
        # BUILT → SIGNING
        assert state_machine.can_transition(TransactionState.BUILT, TransactionState.SIGNING)
        
        # SIGNING → SIGNED
        assert state_machine.can_transition(TransactionState.SIGNING, TransactionState.SIGNED)
        
        # SIGNED → SUBMITTING
        assert state_machine.can_transition(TransactionState.SIGNED, TransactionState.SUBMITTING)
        
        # SUBMITTING → SUBMITTED
        assert state_machine.can_transition(TransactionState.SUBMITTING, TransactionState.SUBMITTED)
        
        # SUBMITTED → CONFIRMED
        assert state_machine.can_transition(TransactionState.SUBMITTED, TransactionState.CONFIRMED)
    
    def test_invalid_transitions(self, state_machine):
        """Test invalid state transitions."""
        # Cannot skip steps
        assert not state_machine.can_transition(TransactionState.IDLE, TransactionState.SIGNED)
        assert not state_machine.can_transition(TransactionState.BUILDING, TransactionState.CONFIRMED)
        
        # Cannot go backwards
        assert not state_machine.can_transition(TransactionState.SIGNED, TransactionState.BUILDING)
        assert not state_machine.can_transition(TransactionState.CONFIRMED, TransactionState.SUBMITTED)
        
        # Terminal states
        assert not state_machine.can_transition(TransactionState.CONFIRMED, TransactionState.FAILED)
        assert not state_machine.can_transition(TransactionState.FAILED, TransactionState.BUILDING)
    
    def test_any_state_can_fail(self, state_machine):
        """Test that any state can transition to FAILED."""
        for state in TransactionState:
            if state not in (TransactionState.CONFIRMED, TransactionState.FAILED):
                assert state_machine.can_transition(state, TransactionState.FAILED), \
                    f"{state.value} should be able to transition to FAILED"
    
    def test_transition_creates_record(self, state_machine):
        """Test that transition creates and persists record."""
        record = state_machine.transition("tx-123", TransactionState.BUILDING)
        
        assert record.intent_id == "tx-123"
        assert record.state == TransactionState.BUILDING
        
        # Verify persisted
        persisted = state_machine.get_state("tx-123")
        assert persisted.state == TransactionState.BUILDING
    
    def test_transition_validates_sequence(self, state_machine):
        """Test that transition validates the sequence."""
        # Start with BUILDING
        state_machine.transition("tx-123", TransactionState.BUILDING)
        
        # Can go to BUILT
        state_machine.transition("tx-123", TransactionState.BUILT)
        
        # Cannot go back to BUILDING
        with pytest.raises(ValueError) as exc_info:
            state_machine.transition("tx-123", TransactionState.BUILDING)
        
        assert "Invalid transition" in str(exc_info.value)
    
    def test_transition_with_signature(self, state_machine):
        """Test transition with signature."""
        state_machine.transition("tx-123", TransactionState.BUILDING)
        state_machine.transition("tx-123", TransactionState.BUILT)
        state_machine.transition("tx-123", TransactionState.SIGNING)
        state_machine.transition(
            "tx-123",
            TransactionState.SIGNED,
            signature="test-signature-123"
        )
        
        record = state_machine.get_state("tx-123")
        assert record.signature == "test-signature-123"
    
    def test_transition_with_error(self, state_machine):
        """Test transition to FAILED with error."""
        state_machine.transition("tx-123", TransactionState.BUILDING)
        state_machine.transition(
            "tx-123",
            TransactionState.FAILED,
            error="Something went wrong"
        )
        
        record = state_machine.get_state("tx-123")
        assert record.state == TransactionState.FAILED
        assert record.error == "Something went wrong"
    
    def test_new_transaction_must_start_building(self, state_machine):
        """Test that new transactions must start from BUILDING."""
        with pytest.raises(ValueError) as exc_info:
            state_machine.transition("tx-123", TransactionState.SIGNED)
        
        assert "must start from BUILDING" in str(exc_info.value)
    
    def test_recover_on_startup(self, state_machine):
        """Test recovery finds incomplete transactions."""
        # Create mix of transactions using save_state directly to set specific states
        store = state_machine.store
        
        store.save_state("tx-1", TransactionState.BUILDING)
        store.save_state("tx-2", TransactionState.SIGNED)
        store.save_state("tx-3", TransactionState.CONFIRMED)
        store.save_state("tx-4", TransactionState.FAILED)
        store.save_state("tx-5", TransactionState.SUBMITTED)
        
        incomplete = state_machine.recover_on_startup()
        
        intent_ids = {tx.intent_id for tx in incomplete}
        assert intent_ids == {"tx-1", "tx-2", "tx-5"}
    
    def test_recover_returns_empty_when_none_incomplete(self, state_machine):
        """Test recovery returns empty list when all complete."""
        state_machine.transition("tx-1", TransactionState.BUILDING)
        state_machine.transition("tx-1", TransactionState.BUILT)
        state_machine.transition("tx-1", TransactionState.SIGNING)
        state_machine.transition("tx-1", TransactionState.SIGNED)
        state_machine.transition("tx-1", TransactionState.SUBMITTING)
        state_machine.transition("tx-1", TransactionState.SUBMITTED)
        state_machine.transition("tx-1", TransactionState.CONFIRMED)
        
        incomplete = state_machine.recover_on_startup()
        assert incomplete == []


class TestTransactionRecord:
    """Tests for TransactionRecord dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        from datetime import datetime
        
        record = TransactionRecord(
            intent_id="tx-123",
            state=TransactionState.CONFIRMED,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            signature="sig-abc",
            metadata='{"key": "value"}',
            error=None,
        )
        
        d = record.to_dict()
        
        assert d["intent_id"] == "tx-123"
        assert d["state"] == "confirmed"
        assert d["timestamp"] == "2025-01-01T12:00:00"
        assert d["signature"] == "sig-abc"
        assert d["metadata"] == '{"key": "value"}'
        assert d["error"] is None
