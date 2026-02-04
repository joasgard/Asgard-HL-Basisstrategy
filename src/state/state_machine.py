"""
Transaction State Machine for Asgard Operations.

Implements a robust state machine for tracking transaction lifecycle:
IDLE → BUILDING → BUILT → SIGNING → SIGNED → SUBMITTING → SUBMITTED → CONFIRMED
                        ↓        ↓          ↓           ↓             ↓
                     FAILED   FAILED     FAILED       FAILED        FAILED/timeout

State persistence in SQLite ensures recovery after crashes.
"""
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from src.models.common import TransactionState
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TransactionRecord:
    """Record of a transaction in the state machine."""
    intent_id: str
    state: TransactionState
    timestamp: datetime
    signature: Optional[str] = None
    metadata: Optional[str] = None  # JSON string for additional data
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "intent_id": self.intent_id,
            "state": self.state.value,
            "timestamp": self.timestamp.isoformat(),
            "signature": self.signature,
            "metadata": self.metadata,
            "error": self.error,
        }


class StateStore:
    """
    SQLite-based state persistence for transactions.
    
    Security note: Only signatures are stored, not full transaction bytes.
    Signatures alone cannot be used to replay or modify transactions.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize state store.
        
        Args:
            db_path: Path to SQLite database. If None, uses default location.
        """
        if db_path is None:
            # Default to project root
            base_dir = Path(__file__).parent.parent.parent
            db_path = str(base_dir / "state.db")
        
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    intent_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    signature TEXT,
                    metadata TEXT,
                    error TEXT
                )
            """)
            
            # Index for querying incomplete transactions
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_state 
                ON transactions(state)
            """)
            
            conn.commit()
        
        logger.debug(f"State store initialized: {self.db_path}")
    
    def save_state(
        self,
        intent_id: str,
        state: TransactionState,
        signature: Optional[str] = None,
        metadata: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Save transaction state.
        
        Args:
            intent_id: Unique identifier for the transaction intent
            state: Current state in the state machine
            signature: Transaction signature (if available)
            metadata: Additional JSON data
            error: Error message (if failed)
        """
        timestamp = datetime.utcnow().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO transactions 
                (intent_id, state, timestamp, signature, metadata, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (intent_id, state.value, timestamp, signature, metadata, error)
            )
            conn.commit()
        
        logger.debug(f"Saved state: {intent_id} -> {state.value}")
    
    def get_state(self, intent_id: str) -> Optional[TransactionRecord]:
        """
        Get transaction state by intent ID.
        
        Args:
            intent_id: Transaction intent ID
            
        Returns:
            TransactionRecord if found, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE intent_id = ?",
                (intent_id,)
            ).fetchone()
            
            if row is None:
                return None
            
            return TransactionRecord(
                intent_id=row[0],
                state=TransactionState(row[1]),
                timestamp=datetime.fromisoformat(row[2]),
                signature=row[3],
                metadata=row[4],
                error=row[5],
            )
    
    def get_incomplete_transactions(self) -> List[TransactionRecord]:
        """
        Get all incomplete transactions (not CONFIRMED or FAILED).
        
        Returns:
            List of transaction records that need attention
        """
        incomplete_states = [
            TransactionState.IDLE.value,
            TransactionState.BUILDING.value,
            TransactionState.BUILT.value,
            TransactionState.SIGNING.value,
            TransactionState.SIGNED.value,
            TransactionState.SUBMITTING.value,
            TransactionState.SUBMITTED.value,
        ]
        
        placeholders = ",".join("?" * len(incomplete_states))
        
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM transactions WHERE state IN ({placeholders})",
                incomplete_states
            ).fetchall()
            
            return [
                TransactionRecord(
                    intent_id=row[0],
                    state=TransactionState(row[1]),
                    timestamp=datetime.fromisoformat(row[2]),
                    signature=row[3],
                    metadata=row[4],
                    error=row[5],
                )
                for row in rows
            ]
    
    def get_transactions_by_state(self, state: TransactionState) -> List[TransactionRecord]:
        """
        Get all transactions in a specific state.
        
        Args:
            state: State to filter by
            
        Returns:
            List of matching transaction records
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE state = ?",
                (state.value,)
            ).fetchall()
            
            return [
                TransactionRecord(
                    intent_id=row[0],
                    state=TransactionState(row[1]),
                    timestamp=datetime.fromisoformat(row[2]),
                    signature=row[3],
                    metadata=row[4],
                    error=row[5],
                )
                for row in rows
            ]
    
    def delete_transaction(self, intent_id: str) -> None:
        """Delete a transaction record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM transactions WHERE intent_id = ?",
                (intent_id,)
            )
            conn.commit()
        
        logger.debug(f"Deleted transaction: {intent_id}")


class TransactionStateMachine:
    """
    State machine for managing transaction lifecycle.
    
    Valid transitions:
    - IDLE → BUILDING
    - BUILDING → BUILT | FAILED
    - BUILT → SIGNING | FAILED
    - SIGNING → SIGNED | FAILED
    - SIGNED → SUBMITTING | FAILED
    - SUBMITTING → SUBMITTED | FAILED
    - SUBMITTED → CONFIRMED | FAILED
    - Any → FAILED (error handling)
    """
    
    VALID_TRANSITIONS = {
        TransactionState.IDLE: {TransactionState.BUILDING, TransactionState.FAILED},
        TransactionState.BUILDING: {TransactionState.BUILT, TransactionState.FAILED},
        TransactionState.BUILT: {TransactionState.SIGNING, TransactionState.FAILED},
        TransactionState.SIGNING: {TransactionState.SIGNED, TransactionState.FAILED},
        TransactionState.SIGNED: {TransactionState.SUBMITTING, TransactionState.FAILED},
        TransactionState.SUBMITTING: {TransactionState.SUBMITTED, TransactionState.FAILED},
        TransactionState.SUBMITTED: {TransactionState.CONFIRMED, TransactionState.FAILED},
        TransactionState.CONFIRMED: set(),  # Terminal state
        TransactionState.FAILED: set(),  # Terminal state
    }
    
    def __init__(self, store: Optional[StateStore] = None):
        """
        Initialize state machine.
        
        Args:
            store: StateStore for persistence. If None, creates default.
        """
        self.store = store or StateStore()
    
    def can_transition(
        self,
        current: TransactionState,
        target: TransactionState
    ) -> bool:
        """
        Check if a state transition is valid.
        
        Args:
            current: Current state
            target: Target state
            
        Returns:
            True if transition is valid
        """
        if current not in self.VALID_TRANSITIONS:
            return False
        return target in self.VALID_TRANSITIONS[current]
    
    def transition(
        self,
        intent_id: str,
        target_state: TransactionState,
        signature: Optional[str] = None,
        metadata: Optional[str] = None,
        error: Optional[str] = None,
    ) -> TransactionRecord:
        """
        Transition to a new state.
        
        Args:
            intent_id: Transaction intent ID
            target_state: State to transition to
            signature: Transaction signature (if applicable)
            metadata: Additional JSON data
            error: Error message (if transitioning to FAILED)
            
        Returns:
            Updated transaction record
            
        Raises:
            ValueError: If transition is not valid
        """
        # Get current state
        current = self.store.get_state(intent_id)
        
        if current is None:
            # New transaction, must start from IDLE
            if target_state != TransactionState.BUILDING:
                raise ValueError(
                    f"New transaction must start from BUILDING, got {target_state}"
                )
            current_state = TransactionState.IDLE
        else:
            current_state = current.state
        
        # Validate transition
        if not self.can_transition(current_state, target_state):
            raise ValueError(
                f"Invalid transition: {current_state.value} → {target_state.value}"
            )
        
        # Save new state
        self.store.save_state(
            intent_id=intent_id,
            state=target_state,
            signature=signature,
            metadata=metadata,
            error=error,
        )
        
        logger.info(f"State transition: {intent_id}: {current_state.value} → {target_state.value}")
        
        return TransactionRecord(
            intent_id=intent_id,
            state=target_state,
            timestamp=datetime.utcnow(),
            signature=signature,
            metadata=metadata,
            error=error,
        )
    
    def get_state(self, intent_id: str) -> Optional[TransactionRecord]:
        """Get current state of a transaction."""
        return self.store.get_state(intent_id)
    
    def recover_on_startup(self) -> List[TransactionRecord]:
        """
        Recover incomplete transactions on startup.
        
        Returns:
            List of incomplete transactions that need attention
        """
        incomplete = self.store.get_incomplete_transactions()
        
        if incomplete:
            logger.info(f"Found {len(incomplete)} incomplete transactions on startup")
            for tx in incomplete:
                logger.info(f"  - {tx.intent_id}: {tx.state.value}")
        
        return incomplete
