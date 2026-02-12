-- Migration: Add users table for Privy authentication
-- Version: 4
-- PostgreSQL version

-- Pending auth table for OTP flow
CREATE TABLE IF NOT EXISTS pending_auth (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    session_duration_hours INTEGER DEFAULT 24,
    ip_address TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_auth_email ON pending_auth(email);
CREATE INDEX IF NOT EXISTS idx_pending_auth_created ON pending_auth(created_at);

-- Users table for storing wallet addresses and auth info
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    solana_address TEXT,
    evm_address TEXT,
    is_new_user BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    session_duration_hours INTEGER DEFAULT 24
);

-- Index for email lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Index for wallet address lookups
CREATE INDEX IF NOT EXISTS idx_users_solana ON users(solana_address);
CREATE INDEX IF NOT EXISTS idx_users_evm ON users(evm_address);

-- Add FK from position_jobs to users (deferred from migration 003)
ALTER TABLE position_jobs ADD CONSTRAINT fk_position_jobs_user FOREIGN KEY (user_id) REFERENCES users(id);

-- DOWN
-- Drop indexes and tables
DROP INDEX IF EXISTS idx_pending_auth_created;
DROP INDEX IF EXISTS idx_pending_auth_email;
DROP TABLE IF EXISTS pending_auth;
DROP INDEX IF EXISTS idx_users_evm;
DROP INDEX IF EXISTS idx_users_solana;
DROP INDEX IF EXISTS idx_users_email;
DROP TABLE IF EXISTS users;
