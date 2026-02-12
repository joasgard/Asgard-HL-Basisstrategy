-- Migration: Add position_jobs table for async position opening
-- Version: 3
-- PostgreSQL version

-- Table for tracking async position opening jobs
CREATE TABLE IF NOT EXISTS position_jobs (
    job_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    params JSONB NOT NULL,
    result JSONB,
    error TEXT,
    error_stage TEXT,
    position_id TEXT,
    asgard_pda TEXT,
    unwind_attempted BOOLEAN DEFAULT false,
    unwind_successful BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
    -- FK to users(id) added in migration 004 after users table exists
);

-- Index for querying user's jobs
CREATE INDEX IF NOT EXISTS idx_position_jobs_user ON position_jobs(user_id);

-- Index for querying by status
CREATE INDEX IF NOT EXISTS idx_position_jobs_status ON position_jobs(status);

-- Index for querying pending jobs
CREATE INDEX IF NOT EXISTS idx_position_jobs_pending ON position_jobs(status) WHERE status = 'pending';

-- DOWN
-- Drop position_jobs table and index
DROP INDEX IF EXISTS idx_position_jobs_pending;
DROP INDEX IF EXISTS idx_position_jobs_status;
DROP INDEX IF EXISTS idx_position_jobs_user;
DROP TABLE IF EXISTS position_jobs;
