-- Migration: Add job durability columns for crash recovery and retry tracking
-- Version: 8
-- PostgreSQL version

-- Add retry tracking and error details to position_jobs
ALTER TABLE position_jobs ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
ALTER TABLE position_jobs ADD COLUMN IF NOT EXISTS last_error TEXT;

-- Index for finding stuck jobs on startup recovery
CREATE INDEX IF NOT EXISTS idx_position_jobs_running
    ON position_jobs(status) WHERE status = 'running';

-- DOWN
-- DROP INDEX IF EXISTS idx_position_jobs_running;
-- ALTER TABLE position_jobs DROP COLUMN IF EXISTS retry_count;
-- ALTER TABLE position_jobs DROP COLUMN IF EXISTS last_error;
