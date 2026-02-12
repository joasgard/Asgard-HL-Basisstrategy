"""
Database module for SQLite with encrypted configuration fields.
"""

from shared.db.database import Database, get_db
from shared.db.migrations import SchemaMigrator, run_migrations

__all__ = ["Database", "get_db", "SchemaMigrator", "run_migrations"]
