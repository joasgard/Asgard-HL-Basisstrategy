-- Migration: Add position_intents table for intent-based position entry
-- Version: 7
-- PostgreSQL version

CREATE TABLE IF NOT EXISTS position_intents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    asset TEXT NOT NULL DEFAULT 'SOL',
    leverage REAL NOT NULL DEFAULT 3.0,
    size_usd REAL NOT NULL,

    -- Entry criteria
    min_funding_rate REAL,
    max_funding_volatility REAL DEFAULT 0.50,
    max_entry_price REAL,

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'active', 'executed', 'cancelled', 'expired', 'failed')
    ),

    -- Execution tracking
    position_id TEXT,
    job_id TEXT,
    execution_error TEXT,
    criteria_snapshot JSONB,

    -- Timestamps
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    activated_at TIMESTAMP,
    executed_at TIMESTAMP,
    cancelled_at TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Index for scanner: find all active/pending intents
CREATE INDEX IF NOT EXISTS idx_intents_status ON position_intents(status);

-- Index for scanner: pending/active intents only
CREATE INDEX IF NOT EXISTS idx_intents_scannable ON position_intents(status)
    WHERE status IN ('pending', 'active');

-- Index for user's intents
CREATE INDEX IF NOT EXISTS idx_intents_user ON position_intents(user_id);

-- Index for expiry checking
CREATE INDEX IF NOT EXISTS idx_intents_expires ON position_intents(expires_at)
    WHERE expires_at IS NOT NULL AND status IN ('pending', 'active');

-- DOWN
DROP INDEX IF EXISTS idx_intents_expires;
DROP INDEX IF EXISTS idx_intents_user;
DROP INDEX IF EXISTS idx_intents_scannable;
DROP INDEX IF EXISTS idx_intents_status;
DROP TABLE IF EXISTS position_intents;
