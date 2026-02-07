-- Add backup tracking and position history tables

-- Backup tracking
CREATE TABLE IF NOT EXISTS backups (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    size_bytes INTEGER,
    checksum TEXT,
    includes_logs BOOLEAN DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_backups_created 
    ON backups(created_at);

-- Position history (archive of closed positions)
CREATE TABLE IF NOT EXISTS position_history (
    id TEXT PRIMARY KEY,
    asset TEXT NOT NULL,
    status TEXT NOT NULL,  -- closed, liquidated
    opened_at TIMESTAMP,
    closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    entry_prices TEXT,  -- JSON
    exit_prices TEXT,   -- JSON
    pnl_usd REAL,
    funding_earned_usd REAL,
    asgard_protocol TEXT,
    hyperliquid_position_size REAL
);

CREATE INDEX IF NOT EXISTS idx_position_history_closed 
    ON position_history(closed_at);
CREATE INDEX IF NOT EXISTS idx_position_history_asset 
    ON position_history(asset);
