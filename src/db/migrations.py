"""
Database schema migration system.
"""

import os
import hashlib
import importlib.util
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from src.db.database import Database


# Find migrations directory - handle both dev and production paths
_migrations_paths = [
    Path(__file__).parent.parent.parent / "migrations",  # src/db/ -> src/ -> root/migrations
    Path(__file__).parent.parent.parent.parent / "migrations",  # Alternative structure
    Path("/data/migrations"),  # Docker production path
]
MIGRATIONS_DIR = next((p for p in _migrations_paths if p.exists()), _migrations_paths[0])


@dataclass
class Migration:
    """A single migration."""
    version: int
    name: str
    checksum: str
    sql_up: str
    sql_down: Optional[str] = None


class SchemaMigrator:
    """Handles database schema migrations."""
    
    def __init__(self, db: Database, migrations_dir: Path = MIGRATIONS_DIR):
        self.db = db
        self.migrations_dir = migrations_dir
    
    def _compute_checksum(self, sql: str) -> str:
        """Compute SHA256 checksum of migration SQL."""
        return hashlib.sha256(sql.encode()).hexdigest()[:16]
    
    async def _ensure_schema_version_table(self) -> None:
        """Create schema_version table if it doesn't exist."""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                checksum TEXT
            )
        """)
        await self.db._connection.commit()
    
    async def get_current_version(self) -> int:
        """Get current schema version."""
        await self._ensure_schema_version_table()
        row = await self.db.fetchone(
            "SELECT MAX(version) as version FROM schema_version"
        )
        return row["version"] if row and row["version"] else 0
    
    def _load_migrations(self) -> List[Migration]:
        """Load all migration files from migrations directory."""
        migrations = []
        
        if not self.migrations_dir.exists():
            return migrations
        
        for file in sorted(self.migrations_dir.glob("*.sql")):
            # Parse filename: 001_initial_schema.sql
            parts = file.stem.split("_", 1)
            if len(parts) != 2:
                continue
            
            try:
                version = int(parts[0])
            except ValueError:
                continue
            
            name = parts[1]
            sql = file.read_text()
            checksum = self._compute_checksum(sql)
            
            # Split up/down migrations if separator present
            if "-- DOWN" in sql:
                parts = sql.split("-- DOWN")
                sql_up = parts[0].strip()
                sql_down = parts[1].strip()
            else:
                sql_up = sql
                sql_down = None
            
            migrations.append(Migration(
                version=version,
                name=name,
                checksum=checksum,
                sql_up=sql_up,
                sql_down=sql_down
            ))
        
        return sorted(migrations, key=lambda m: m.version)
    
    async def migrate(self, target_version: Optional[int] = None) -> int:
        """
        Run migrations to target version.
        
        Args:
            target_version: Version to migrate to (None = latest)
            
        Returns:
            Final schema version
        """
        await self._ensure_schema_version_table()
        current = await self.get_current_version()
        migrations = self._load_migrations()
        
        if not migrations:
            return current
        
        if target_version is None:
            target_version = max(m.version for m in migrations)
        
        if current == target_version:
            return current
        
        if current < target_version:
            # Migrate up
            for migration in migrations:
                if current < migration.version <= target_version:
                    await self._apply_migration(migration)
        else:
            # Migrate down
            for migration in reversed(migrations):
                if target_version < migration.version <= current:
                    await self._revert_migration(migration)
        
        return await self.get_current_version()
    
    async def _apply_migration(self, migration: Migration) -> None:
        """Apply a single migration."""
        print(f"Applying migration {migration.version}: {migration.name}")
        
        async with self.db.transaction():
            # Execute migration
            await self.db.executescript(migration.sql_up)
            
            # Record migration
            await self.db.execute(
                "INSERT INTO schema_version (version, checksum) VALUES (?, ?)",
                (migration.version, migration.checksum)
            )
        
        print(f"Applied migration {migration.version}")
    
    async def _revert_migration(self, migration: Migration) -> None:
        """Revert a single migration."""
        if not migration.sql_down:
            raise ValueError(f"Migration {migration.version} has no down script")
        
        print(f"Reverting migration {migration.version}: {migration.name}")
        
        async with self.db.transaction():
            await self.db.executescript(migration.sql_down)
            await self.db.execute(
                "DELETE FROM schema_version WHERE version = ?",
                (migration.version,)
            )
        
        print(f"Reverted migration {migration.version}")
    
    async def verify_checksums(self) -> List[str]:
        """
        Verify migration checksums match applied migrations.
        
        Returns:
            List of errors (empty if all valid)
        """
        errors = []
        migrations = self._load_migrations()
        
        for migration in migrations:
            row = await self.db.fetchone(
                "SELECT checksum FROM schema_version WHERE version = ?",
                (migration.version,)
            )
            
            if row and row["checksum"] != migration.checksum:
                errors.append(
                    f"Migration {migration.version} checksum mismatch: "
                    f"expected {row['checksum']}, got {migration.checksum}"
                )
        
        return errors


async def run_migrations(db: Database, migrations_dir: Optional[Path] = None) -> int:
    """
    Run all pending migrations.
    
    Args:
        db: Database instance
        migrations_dir: Optional custom migrations directory
        
    Returns:
        Final schema version
    """
    migrator = SchemaMigrator(db, migrations_dir or MIGRATIONS_DIR)
    
    # Verify checksums
    errors = await migrator.verify_checksums()
    if errors:
        raise ValueError(f"Migration checksum errors: {errors}")
    
    # Run migrations
    version = await migrator.migrate()
    print(f"Database schema version: {version}")
    
    return version
