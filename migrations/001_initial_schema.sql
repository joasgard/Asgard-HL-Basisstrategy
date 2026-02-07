-- Initial schema for Delta Neutral Bot SaaS (Privy-based auth)
-- Creates: schema_version, config, sessions, audit_log, setup_jobs, user_keys tables

-- Schema version tracking (already created by migrator, but ensure it exists)
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    checksum TEXT
);

-- Configuration table with encrypted field support
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,  -- Plaintext value for non-sensitive config
    value_encrypted BLOB,  -- Encrypted value for sensitive config (nonce || ciphertext || hmac)
    is_encrypted BOOLEAN DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User encryption keys (one per Privy user)
CREATE TABLE IF NOT EXISTS user_keys (
    privy_user_id TEXT PRIMARY KEY,
    encrypted_dek BLOB NOT NULL,  -- DEK encrypted by KEK (derived from user_id + server_secret)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sessions table for web authentication
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    privy_user_id TEXT NOT NULL,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    csrf_token TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires 
    ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_privy_user 
    ON sessions(privy_user_id);

-- Audit log (sanitized - no sensitive data)
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,
    user TEXT,
    ip_address TEXT,
    details TEXT,  -- Sanitized details
    success BOOLEAN DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
    ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action 
    ON audit_log(action);

-- Setup wizard jobs for async operations
CREATE TABLE IF NOT EXISTS setup_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed
    progress INTEGER DEFAULT 0,  -- 0-100
    params TEXT,  -- JSON parameters
    result TEXT,  -- JSON result on success
    error TEXT,   -- Error message on failure
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_setup_jobs_status 
    ON setup_jobs(status);

-- Bot state tracking (separate from core engine state.db)
CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initial setup flags
INSERT OR IGNORE INTO config (key, value, is_encrypted) VALUES 
    ('setup_completed', 'false', 0),
    ('privy_configured', 'false', 0),
    ('privy_authenticated', 'false', 0);
