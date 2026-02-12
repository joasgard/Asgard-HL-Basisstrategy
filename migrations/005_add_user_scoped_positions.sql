-- Migration: Add user-scoped positions table for multi-tenant support
-- Version: 5
-- PostgreSQL version

-- User-scoped positions table
CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_closed INTEGER DEFAULT 0,

    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Index for user-scoped queries
CREATE INDEX IF NOT EXISTS idx_positions_user ON positions(user_id);

-- Index for user's active positions
CREATE INDEX IF NOT EXISTS idx_positions_user_active ON positions(user_id, is_closed) WHERE is_closed = 0;

-- Index for closed flag
CREATE INDEX IF NOT EXISTS idx_positions_closed ON positions(is_closed);

-- Update position_history to include user_id
ALTER TABLE position_history ADD COLUMN IF NOT EXISTS user_id TEXT;

-- Index for user-scoped history
CREATE INDEX IF NOT EXISTS idx_position_history_user ON position_history(user_id);

-- DOWN
DROP INDEX IF EXISTS idx_position_history_user;
DROP INDEX IF EXISTS idx_positions_user_active;
DROP INDEX IF EXISTS idx_positions_user;
DROP INDEX IF EXISTS idx_positions_closed;
DROP TABLE IF EXISTS positions;
