"""
PostgreSQL database connection manager with async support using asyncpg.

Provides connection pooling, transaction management, and a compatible
interface for callers migrating from the previous aiosqlite backend.
"""

import os
import asyncio
from typing import Optional, Any, List, Dict
from contextlib import asynccontextmanager

import asyncpg

# Default database URL
DEFAULT_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://basis:basis@localhost:5432/basis"
)

# Pool sizing
POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN", "2"))
POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX", "10"))


class Database:
    """Async PostgreSQL database wrapper with connection pooling."""

    def __init__(self, database_url: str = DEFAULT_DATABASE_URL):
        self.database_url = database_url
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Establish connection pool."""
        self._pool = await asyncpg.create_pool(
            self.database_url,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
        )

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _ensure_pool(self) -> asyncpg.Pool:
        """Return pool, raising if not connected."""
        if self._pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._pool

    # ------------------------------------------------------------------
    # Query helpers – accept both positional ($1) and ? placeholders.
    # All public query methods auto-convert ? to $N for convenience so
    # callers written for SQLite keep working.
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_placeholders(query: str) -> str:
        """Convert ? placeholders to $1, $2, ... for asyncpg."""
        parts: list[str] = []
        idx = 0
        i = 0
        while i < len(query):
            ch = query[i]
            if ch == '?':
                idx += 1
                parts.append(f'${idx}')
            elif ch == "'" or ch == '"':
                # skip quoted strings
                quote = ch
                parts.append(ch)
                i += 1
                while i < len(query) and query[i] != quote:
                    parts.append(query[i])
                    i += 1
                if i < len(query):
                    parts.append(query[i])
            else:
                parts.append(ch)
            i += 1
        return ''.join(parts)

    async def execute(self, query: str, parameters: tuple = ()) -> str:
        """Execute a query. Returns status string."""
        pool = self._ensure_pool()
        q = self._convert_placeholders(query)
        async with pool.acquire() as conn:
            return await conn.execute(q, *parameters)

    async def executemany(self, query: str, parameters: List[tuple]) -> None:
        """Execute a query for each set of parameters."""
        pool = self._ensure_pool()
        q = self._convert_placeholders(query)
        async with pool.acquire() as conn:
            await conn.executemany(q, parameters)

    async def executescript(self, script: str) -> None:
        """Execute a multi-statement SQL script."""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(script)

    async def fetchone(self, query: str, parameters: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row as dict."""
        pool = self._ensure_pool()
        q = self._convert_placeholders(query)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(q, *parameters)
            return dict(row) if row else None

    async def fetchall(self, query: str, parameters: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows as list of dicts."""
        pool = self._ensure_pool()
        q = self._convert_placeholders(query)
        async with pool.acquire() as conn:
            rows = await conn.fetch(q, *parameters)
            return [dict(r) for r in rows]

    async def fetchval(self, query: str, parameters: tuple = ()) -> Any:
        """Fetch a single value."""
        pool = self._ensure_pool()
        q = self._convert_placeholders(query)
        async with pool.acquire() as conn:
            return await conn.fetchval(q, *parameters)

    @asynccontextmanager
    async def transaction(self):
        """Transaction context manager using a dedicated connection."""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Yield a thin wrapper that uses this specific connection
                yield _TransactionConnection(conn)

    # ------------------------------------------------------------------
    # Config helpers (used throughout the app)
    # ------------------------------------------------------------------

    async def get_config(self, key: str) -> Optional[str]:
        """Get a config value."""
        row = await self.fetchone(
            "SELECT value FROM config WHERE key = $1", (key,)
        )
        return row["value"] if row else None

    async def set_config(self, key: str, value: str, encrypted: bool = False) -> None:
        """Set a config value (upsert)."""
        await self.execute(
            """INSERT INTO config (key, value, is_encrypted)
               VALUES ($1, $2, $3)
               ON CONFLICT (key) DO UPDATE SET
               value = EXCLUDED.value, is_encrypted = EXCLUDED.is_encrypted""",
            (key, value, encrypted),
        )

    async def get_encrypted_config(self, key: str) -> Optional[bytes]:
        """Get an encrypted config value as bytes."""
        row = await self.fetchone(
            "SELECT value_encrypted FROM config WHERE key = $1 AND is_encrypted = true",
            (key,),
        )
        return row["value_encrypted"] if row else None

    async def set_encrypted_config(self, key: str, value: bytes) -> None:
        """Set an encrypted config value."""
        await self.execute(
            """INSERT INTO config (key, value_encrypted, value, is_encrypted)
               VALUES ($1, $2, NULL, true)
               ON CONFLICT (key) DO UPDATE SET
               value_encrypted = EXCLUDED.value_encrypted,
               value = NULL,
               is_encrypted = true""",
            (key, value),
        )

    async def get_schema_version(self) -> int:
        """Get current schema version."""
        try:
            version = await self.fetchval(
                "SELECT MAX(version) FROM schema_version"
            )
            return version or 0
        except Exception:
            return 0


class _TransactionConnection:
    """Thin wrapper so code inside `async with db.transaction() as tx:` can run queries."""

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    @staticmethod
    def _convert_placeholders(query: str) -> str:
        return Database._convert_placeholders(query)

    async def execute(self, query: str, parameters: tuple = ()) -> str:
        q = self._convert_placeholders(query)
        return await self._conn.execute(q, *parameters)

    async def executemany(self, query: str, parameters: List[tuple]) -> None:
        q = self._convert_placeholders(query)
        await self._conn.executemany(q, parameters)

    async def executescript(self, script: str) -> None:
        await self._conn.execute(script)

    async def fetchone(self, query: str, parameters: tuple = ()) -> Optional[Dict[str, Any]]:
        q = self._convert_placeholders(query)
        row = await self._conn.fetchrow(q, *parameters)
        return dict(row) if row else None

    async def fetchall(self, query: str, parameters: tuple = ()) -> List[Dict[str, Any]]:
        q = self._convert_placeholders(query)
        rows = await self._conn.fetch(q, *parameters)
        return [dict(r) for r in rows]

    async def fetchval(self, query: str, parameters: tuple = ()) -> Any:
        q = self._convert_placeholders(query)
        return await self._conn.fetchval(q, *parameters)


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------
_db_instance: Optional[Database] = None


def get_db() -> Database:
    """Get database singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


async def init_db(database_url: str = DEFAULT_DATABASE_URL) -> Database:
    """Initialize database with connection pool."""
    global _db_instance
    db = Database(database_url)
    await db.connect()
    _db_instance = db
    return db
