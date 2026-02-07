-- Migration: Add position_jobs table for async position opening
-- Version: 3
-- Date: 2026-02-07

-- Table for tracking async position opening jobs
CREATE TABLE IF NOT EXISTS position_jobs (
    job_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    params TEXT NOT NULL,  -- JSON of OpenPositionRequest
    result TEXT,           -- JSON result on completion
    error TEXT,            -- Error message if failed
    error_stage TEXT,      -- Where it failed (preflight, asgard_open, hyperliquid_open, validation)
    position_id TEXT,      -- Set on success
    asgard_pda TEXT,       -- Asgard position PDA if opened
    unwind_attempted BOOLEAN DEFAULT 0,  -- Whether unwind was attempted on failure
    unwind_successful BOOLEAN,           -- Whether unwind succeeded
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,  -- When job started executing
    completed_at TIMESTAMP, -- When job finished
    
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Index for querying user's jobs
CREATE INDEX IF NOT EXISTS idx_position_jobs_user ON position_jobs(user_id);

-- Index for querying by status
CREATE INDEX IF NOT EXISTS idx_position_jobs_status ON position_jobs(status);

-- Index for querying pending jobs
CREATE INDEX IF NOT EXISTS idx_position_jobs_pending ON position_jobs(status) WHERE status = 'pending';

-- Update schema version
INSERT OR REPLACE INTO schema_version (version, applied_at, description)
VALUES (3, CURRENT_TIMESTAMP, 'Add position_jobs table for async position opening');
