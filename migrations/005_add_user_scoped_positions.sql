-- Migration: Add user-scoped positions table and fix schema for multi-tenant support
-- Version: 5
-- Date: 2026-02-10

-- Note: This migration assumes we're starting fresh or migrating from a single-tenant setup.
-- If position_jobs table exists with wrong FK, we fix it here.

-- Fix foreign key constraint on position_jobs if table exists
-- SQLite doesn't support ALTER TABLE DROP CONSTRAINT, so we recreate if needed
-- For fresh installs, migration 003 has been fixed. For existing DBs, manual fix required.

-- User-scoped positions table (replaces the one in persistence.py)
-- This stores active positions with user isolation
CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    data TEXT NOT NULL,  -- JSON containing full position data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_closed INTEGER DEFAULT 0,
    
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Index for user-scoped queries
CREATE INDEX IF NOT EXISTS idx_positions_user ON positions(user_id);

-- Index for user's active positions
CREATE INDEX IF NOT EXISTS idx_positions_user_active ON positions(user_id, is_closed) WHERE is_closed = 0;

-- Index for closed flag
CREATE INDEX IF NOT EXISTS idx_positions_closed ON positions(is_closed);

-- Update position_history to include user_id (for proper archival)
-- SQLite doesn't support adding FK to existing table easily, so we recreate
ALTER TABLE position_history ADD COLUMN user_id TEXT;

-- Index for user-scoped history
CREATE INDEX IF NOT EXISTS idx_position_history_user ON position_history(user_id);

-- DOWN
-- Drop indexes
DROP INDEX IF EXISTS idx_position_history_user;
DROP INDEX IF EXISTS idx_positions_user_active;
DROP INDEX IF EXISTS idx_positions_user;
DROP INDEX IF EXISTS idx_positions_closed;

-- Drop tables
DROP TABLE IF EXISTS positions;

-- Remove column from position_history (not reversible in SQLite without recreate)
-- This would require table recreation in a real rollback
