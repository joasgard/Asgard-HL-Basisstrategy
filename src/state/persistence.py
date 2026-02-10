"""
State Persistence for Delta Neutral Arbitrage Bot.

Handles persistence of bot state across restarts:
- Open positions
- Transaction state machine records
- Audit log of all actions
- Recovery on startup for incomplete transactions

Uses SQLite for storage with async operations via aiosqlite.

Usage:
    persistence = StatePersistence()
    await persistence.setup()
    
    # Save position
    await persistence.save_position(position)
    
    # Load positions
    positions = await persistence.load_positions()
    
    # Log action
    await persistence.log_action({"type": "entry", "asset": "SOL"})
    
    # Get audit log
    logs = await persistence.get_audit_log(start_date, end_date)
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from pathlib import Path

try:
    import aiosqlite
except ImportError:
    aiosqlite = None

from src.config.assets import Asset
from src.models.position import (
    AsgardPosition, 
    HyperliquidPosition, 
    CombinedPosition,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RecoveryResult:
    """Result of state recovery."""
    
    success: bool
    positions_recovered: int
    incomplete_transactions: int
    errors: List[str]


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Asset):
            return obj.value

        return super().default(obj)


def decode_decimal(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Decode Decimal values from JSON."""
    result = {}
    for key, value in obj.items():
        if isinstance(value, str):
            # Try to parse as Decimal
            try:
                result[key] = Decimal(value)
            except:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = decode_decimal(value)
        elif isinstance(value, list):
            result[key] = [
                Decimal(v) if isinstance(v, str) and _is_decimal(v) else v
                for v in value
            ]
        else:
            result[key] = value
    return result


def _is_decimal(s: str) -> bool:
    """Check if string represents a decimal number."""
    try:
        Decimal(s)
        return True
    except:
        return False


class StatePersistence:
    """
    Manages persistence of bot state.
    
    Stores:
    - Positions: CombinedPosition objects
    - Actions: Audit log of all bot actions
    - State: Key-value state store
    
    Database Schema:
    - positions: id, data (JSON), created_at, updated_at, is_closed
    - action_log: id, action_type, data (JSON), timestamp
    - state: key, value, updated_at
    
    Usage:
        persistence = StatePersistence("bot_state.db")
        await persistence.setup()
        
        # Save and load positions
        await persistence.save_position(position)
        positions = await persistence.load_positions()
        
        # Audit logging
        await persistence.log_action({
            "type": "position_opened",
            "asset": "SOL",
            "size": 10000,
        })
    
    Args:
        db_path: Path to SQLite database
    """
    
    DEFAULT_DB_PATH = "state.db"
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self._db = None
        
        logger.info(f"StatePersistence initialized (db: {self.db_path})")
    
    async def setup(self):
        """Setup database connection and tables."""
        if aiosqlite is None:
            raise ImportError("aiosqlite is required for state persistence")
        
        self._db = await aiosqlite.connect(self.db_path)
        
        # Enable foreign keys
        await self._db.execute("PRAGMA foreign_keys = ON")
        
        # Create tables
        await self._create_tables()
        
        logger.info("State persistence setup complete")
    
    async def close(self):
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("State persistence connection closed")
    
    async def _create_tables(self):
        """Create database tables."""
        # Positions table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_closed INTEGER DEFAULT 0
            )
        """)
        
        # Action log table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                data TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # State table (key-value)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_closed 
            ON positions(is_closed)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_action_log_timestamp 
            ON action_log(timestamp)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_action_log_type 
            ON action_log(action_type)
        """)
        
        await self._db.commit()
    
    # Position methods
    
    async def save_position(self, position: CombinedPosition) -> bool:
        """
        Save a position to the database.
        
        Args:
            position: Position to save
            
        Returns:
            True if saved successfully
        """
        if self._db is None:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        try:
            # CombinedPosition uses 'asgard' and 'hyperliquid' fields
            # Get asset from asgard.asset
            asset_val = position.asgard.asset.value if hasattr(position.asgard.asset, 'value') else str(position.asgard.asset)
            
            data = {
                "position_id": position.position_id,
                "asset": asset_val,
                "asgard": self._position_to_dict(position.asgard),
                "hyperliquid": self._position_to_dict(position.hyperliquid),
                "reference": {
                    "asgard_entry_price": str(position.reference.asgard_entry_price),
                    "hyperliquid_entry_price": str(position.reference.hyperliquid_entry_price),
                },
                "opportunity_id": position.opportunity_id,
                "status": position.status,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            json_data = json.dumps(data, cls=DecimalEncoder)
            
            await self._db.execute(
                """
                INSERT OR REPLACE INTO positions (id, data, updated_at, is_closed)
                VALUES (?, ?, ?, ?)
                """,
                (
                    position.position_id,
                    json_data,
                    datetime.utcnow().isoformat(),
                    0 if position.status == "open" else 1,
                )
            )
            await self._db.commit()
            
            logger.debug(f"Position saved: {position.position_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save position: {e}")
            return False
    
    async def load_positions(
        self,
        include_closed: bool = False,
    ) -> List[CombinedPosition]:
        """
        Load positions from the database.
        
        Args:
            include_closed: Whether to include closed positions
            
        Returns:
            List of positions
        """
        if self._db is None:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        try:
            if include_closed:
                cursor = await self._db.execute(
                    "SELECT data FROM positions ORDER BY created_at DESC"
                )
            else:
                cursor = await self._db.execute(
                    "SELECT data FROM positions WHERE is_closed = 0 ORDER BY created_at DESC"
                )
            
            rows = await cursor.fetchall()
            positions = []
            
            for row in rows:
                try:
                    data = json.loads(row[0])
                    data = decode_decimal(data)
                    position = self._dict_to_position(data)
                    positions.append(position)
                except Exception as e:
                    logger.error(f"Failed to parse position data: {e}")
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to load positions: {e}")
            return []
    
    async def get_position(self, position_id: str) -> Optional[CombinedPosition]:
        """Get a specific position by ID."""
        if self._db is None:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        try:
            cursor = await self._db.execute(
                "SELECT data FROM positions WHERE id = ?",
                (position_id,)
            )
            row = await cursor.fetchone()
            
            if row:
                data = json.loads(row[0])
                data = decode_decimal(data)
                return self._dict_to_position(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get position: {e}")
            return None
    
    async def delete_position(self, position_id: str) -> bool:
        """Mark a position as closed (soft delete)."""
        if self._db is None:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        try:
            await self._db.execute(
                "UPDATE positions SET is_closed = 1, updated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), position_id)
            )
            await self._db.commit()
            
            logger.debug(f"Position marked as closed: {position_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete position: {e}")
            return False
    
    async def update_position(self, position: CombinedPosition) -> bool:
        """Update an existing position."""
        return await self.save_position(position)
    
    # Action log methods
    
    async def log_action(self, action: Dict[str, Any]) -> bool:
        """
        Log an action to the audit log.
        
        Args:
            action: Action data (must include 'type' key)
            
        Returns:
            True if logged successfully
        """
        if self._db is None:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        try:
            action_type = action.get("type", "unknown")
            json_data = json.dumps(action, cls=DecimalEncoder)
            
            await self._db.execute(
                "INSERT INTO action_log (action_type, data) VALUES (?, ?)",
                (action_type, json_data)
            )
            await self._db.commit()
            
            logger.debug(f"Action logged: {action_type}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to log action: {e}")
            return False
    
    async def get_audit_log(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        action_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get audit log entries.
        
        Args:
            start: Start date filter
            end: End date filter
            action_type: Filter by action type
            limit: Maximum number of entries
            
        Returns:
            List of action log entries
        """
        if self._db is None:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        try:
            query = "SELECT data, timestamp FROM action_log WHERE 1=1"
            params = []
            
            if start:
                query += " AND timestamp >= ?"
                params.append(start.isoformat())
            
            if end:
                query += " AND timestamp <= ?"
                params.append(end.isoformat())
            
            if action_type:
                query += " AND action_type = ?"
                params.append(action_type)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor = await self._db.execute(query, params)
            rows = await cursor.fetchall()
            
            actions = []
            for row in rows:
                try:
                    data = json.loads(row[0])
                    data["_timestamp"] = row[1]
                    actions.append(data)
                except Exception as e:
                    logger.error(f"Failed to parse action data: {e}")
            
            return actions
            
        except Exception as e:
            logger.error(f"Failed to get audit log: {e}")
            return []
    
    # State methods (key-value store)
    
    async def set_state(self, key: str, value: Any) -> bool:
        """Set a state value."""
        if self._db is None:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        try:
            json_value = json.dumps(value, cls=DecimalEncoder)
            
            await self._db.execute(
                """
                INSERT OR REPLACE INTO state (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, json_value, datetime.utcnow().isoformat())
            )
            await self._db.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set state: {e}")
            return False
    
    async def get_state(self, key: str, default: Any = None) -> Any:
        """Get a state value."""
        if self._db is None:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        try:
            cursor = await self._db.execute(
                "SELECT value FROM state WHERE key = ?",
                (key,)
            )
            row = await cursor.fetchone()
            
            if row:
                return json.loads(row[0])
            
            return default
            
        except Exception as e:
            logger.error(f"Failed to get state: {e}")
            return default
    
    async def delete_state(self, key: str) -> bool:
        """Delete a state value."""
        if self._db is None:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        try:
            await self._db.execute("DELETE FROM state WHERE key = ?", (key,))
            await self._db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete state: {e}")
            return False
    
    # Recovery method
    
    async def recovery_on_startup(self) -> RecoveryResult:
        """
        Recover state on startup.
        
        Returns:
            RecoveryResult with recovery details
        """
        errors = []
        positions_recovered = 0
        incomplete_transactions = 0
        
        try:
            # Load active positions
            positions = await self.load_positions(include_closed=False)
            positions_recovered = len(positions)
            
            # Check for incomplete transactions (would query state_machine)
            # This is a placeholder - actual implementation would check
            # the transaction state machine for incomplete transactions
            
            logger.info(
                f"Recovery complete: {positions_recovered} positions, "
                f"{incomplete_transactions} incomplete transactions"
            )
            
            return RecoveryResult(
                success=True,
                positions_recovered=positions_recovered,
                incomplete_transactions=incomplete_transactions,
                errors=errors,
            )
            
        except Exception as e:
            logger.error(f"Recovery failed: {e}")
            errors.append(str(e))
            return RecoveryResult(
                success=False,
                positions_recovered=0,
                incomplete_transactions=0,
                errors=errors,
            )
    
    # Helper methods
    
    def _position_to_dict(self, position) -> Dict[str, Any]:
        """Convert position to dictionary."""
        if position is None:
            return None
        
        if isinstance(position, AsgardPosition):
            return {
                "type": "asgard",
                "position_pda": position.position_pda,
                "intent_id": position.intent_id,
                "asset": position.asset.value if hasattr(position.asset, 'value') else str(position.asset),
                "protocol": position.protocol.value if hasattr(position.protocol, 'value') else str(position.protocol),
                "collateral_usd": position.collateral_usd,
                "position_size_usd": position.position_size_usd,
                "leverage": position.leverage,
                "token_a_amount": position.token_a_amount,
                "token_b_borrowed": position.token_b_borrowed,
                "entry_price_token_a": position.entry_price_token_a,
                "current_health_factor": position.current_health_factor,
                "current_token_a_price": position.current_token_a_price,
            }
        elif isinstance(position, HyperliquidPosition):
            return {
                "type": "hyperliquid",
                "coin": position.coin,
                "size_sol": position.size_sol,
                "entry_px": position.entry_px,
                "leverage": position.leverage,
                "margin_used": position.margin_used,
                "margin_fraction": position.margin_fraction,
                "account_value": position.account_value,
                "mark_px": position.mark_px,
            }
        else:
            return {"type": "unknown", "data": str(position)}
    
    def _dict_to_position(self, data: Dict[str, Any]) -> CombinedPosition:
        """Convert dictionary to CombinedPosition."""
        # This is a simplified conversion
        # In production, would need more robust deserialization
        
        asset_val = data.get("asset", "SOL")
        try:
            asset = Asset(asset_val)
        except:
            asset = Asset.SOL
        
        # Create minimal position objects
        asgard_data = data.get("asgard", {})
        hyperliquid_data = data.get("hyperliquid", {})
        
        # Import Protocol here to avoid circular imports
        from src.models.common import Protocol
        
        asgard_position = AsgardPosition(
            position_pda=asgard_data.get("position_pda", ""),
            intent_id=asgard_data.get("intent_id", "test_intent"),
            asset=asset,
            protocol=Protocol(asgard_data.get("protocol", 0)),
            collateral_usd=asgard_data.get("collateral_usd", Decimal("0")),
            position_size_usd=asgard_data.get("position_size_usd", Decimal("0")),
            leverage=asgard_data.get("leverage", Decimal("3")),
            token_a_amount=asgard_data.get("token_a_amount", Decimal("0")),
            token_b_borrowed=asgard_data.get("token_b_borrowed", Decimal("0")),
            entry_price_token_a=asgard_data.get("entry_price_token_a", Decimal("0")),
            current_token_a_price=asgard_data.get("current_token_a_price", Decimal("0")),
            current_health_factor=asgard_data.get("current_health_factor", Decimal("0.25")),
        )
        
        hyperliquid_position = HyperliquidPosition(
            coin=hyperliquid_data.get("coin", "SOL"),
            size_sol=hyperliquid_data.get("size_sol", Decimal("0")),
            entry_px=hyperliquid_data.get("entry_px", Decimal("0")),
            leverage=hyperliquid_data.get("leverage", Decimal("3")),
            margin_used=hyperliquid_data.get("margin_used", Decimal("0")),
            margin_fraction=hyperliquid_data.get("margin_fraction", Decimal("0.15")),
            account_value=hyperliquid_data.get("account_value", Decimal("0")),
            mark_px=hyperliquid_data.get("mark_px", Decimal("0")),
        )
        
        # Import PositionReference here
        from src.models.position import PositionReference
        
        ref_data = data.get("reference", {})
        reference = PositionReference(
            asgard_entry_price=Decimal(ref_data.get("asgard_entry_price", "0")),
            hyperliquid_entry_price=Decimal(ref_data.get("hyperliquid_entry_price", "0")),
        )
        
        combined = CombinedPosition(
            position_id=data.get("position_id", ""),
            asgard=asgard_position,
            hyperliquid=hyperliquid_position,
            reference=reference,
            opportunity_id=data.get("opportunity_id", ""),
            status=data.get("status", "open"),
        )
        
        return combined
