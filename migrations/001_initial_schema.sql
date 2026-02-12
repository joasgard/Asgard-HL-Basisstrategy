-- Initial schema for Delta Neutral Bot SaaS (Privy-based auth)
-- PostgreSQL version
-- Creates: schema_version, config, sessions, audit_log, setup_jobs, user_keys tables

-- Schema version tracking (already created by migrator, but ensure it exists)
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT NOW(),
    checksum TEXT
);

-- Configuration table with encrypted field support
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,
    value_encrypted BYTEA,
    is_encrypted BOOLEAN DEFAULT false,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- User encryption keys (one per Privy user)
CREATE TABLE IF NOT EXISTS user_keys (
    privy_user_id TEXT PRIMARY KEY,
    encrypted_dek BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Sessions table for web authentication
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    privy_user_id TEXT NOT NULL,
    email TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP DEFAULT NOW(),
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
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    action TEXT NOT NULL,
    "user" TEXT,
    ip_address TEXT,
    details TEXT,
    success BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp
    ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action
    ON audit_log(action);

-- Setup wizard jobs for async operations
CREATE TABLE IF NOT EXISTS setup_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    params JSONB,
    result JSONB,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_setup_jobs_status
    ON setup_jobs(status);

-- Bot state tracking (separate from core engine state.db)
CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Initial setup flags
INSERT INTO config (key, value, is_encrypted) VALUES
    ('setup_completed', 'false', false),
    ('privy_configured', 'false', false),
    ('privy_authenticated', 'false', false)
ON CONFLICT (key) DO NOTHING;
