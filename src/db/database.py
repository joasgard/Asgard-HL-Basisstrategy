"""
SQLite database connection manager with async support.
"""

import os
import asyncio
import aiosqlite
from typing import Optional, Any, List, Dict
from contextlib import asynccontextmanager

# Default database path
DEFAULT_DB_PATH = os.getenv("DB_PATH", "data/state.db")


class Database:
    """Async SQLite database wrapper."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
    
    async def connect(self) -> None:
        """Establish database connection."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        
        # Enable WAL mode for better concurrency
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
    
    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
    
    async def execute(self, query: str, parameters: tuple = ()) -> aiosqlite.Cursor:
        """Execute a query."""
        if not self._connection:
            await self.connect()
        return await self._connection.execute(query, parameters)
    
    async def executemany(self, query: str, parameters: List[tuple]) -> aiosqlite.Cursor:
        """Execute a query multiple times."""
        if not self._connection:
            await self.connect()
        return await self._connection.executemany(query, parameters)
    
    async def executescript(self, script: str) -> aiosqlite.Cursor:
        """Execute a SQL script."""
        if not self._connection:
            await self.connect()
        return await self._connection.executescript(script)
    
    async def fetchone(self, query: str, parameters: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row."""
        async with self._lock:
            cursor = await self.execute(query, parameters)
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def fetchall(self, query: str, parameters: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows."""
        async with self._lock:
            cursor = await self.execute(query, parameters)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def fetchval(self, query: str, parameters: tuple = ()) -> Any:
        """Fetch a single value."""
        row = await self.fetchone(query, parameters)
        if row:
            return next(iter(row.values()))
        return None
    
    @asynccontextmanager
    async def transaction(self):
        """Transaction context manager."""
        async with self._lock:
            await self._connection.execute("BEGIN")
            try:
                yield self
                await self._connection.commit()
            except Exception:
                await self._connection.rollback()
                raise
    
    async def get_config(self, key: str) -> Optional[str]:
        """Get a config value."""
        row = await self.fetchone(
            "SELECT value FROM config WHERE key = ?",
            (key,)
        )
        return row["value"] if row else None
    
    async def set_config(self, key: str, value: str, encrypted: bool = False) -> None:
        """Set a config value."""
        await self.execute(
            """INSERT INTO config (key, value, is_encrypted) 
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET 
               value = excluded.value, is_encrypted = excluded.is_encrypted""",
            (key, value, encrypted)
        )
        await self._connection.commit()
    
    async def get_encrypted_config(self, key: str) -> Optional[bytes]:
        """Get an encrypted config value as bytes."""
        row = await self.fetchone(
            "SELECT value_encrypted FROM config WHERE key = ? AND is_encrypted = 1",
            (key,)
        )
        return row["value_encrypted"] if row else None
    
    async def set_encrypted_config(self, key: str, value: bytes) -> None:
        """Set an encrypted config value."""
        await self.execute(
            """INSERT INTO config (key, value_encrypted, value, is_encrypted) 
               VALUES (?, ?, NULL, 1)
               ON CONFLICT(key) DO UPDATE SET 
               value_encrypted = excluded.value_encrypted,
               value = NULL,
               is_encrypted = 1""",
            (key, value)
        )
        await self._connection.commit()
    
    async def get_schema_version(self) -> int:
        """Get current schema version."""
        try:
            version = await self.fetchval(
                "SELECT MAX(version) FROM schema_version"
            )
            return version or 0
        except Exception:
            return 0


# Singleton instance
_db_instance: Optional[Database] = None


def get_db() -> Database:
    """Get database singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


async def init_db(db_path: str = DEFAULT_DB_PATH) -> Database:
    """Initialize database with migrations."""
    db = Database(db_path)
    await db.connect()
    return db
