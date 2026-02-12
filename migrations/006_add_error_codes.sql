-- Migration: Add error_code column to position_jobs table
-- Version: 6
-- PostgreSQL version

-- Add error_code column for structured error handling
ALTER TABLE position_jobs ADD COLUMN IF NOT EXISTS error_code TEXT;

-- Index for querying by error code
CREATE INDEX IF NOT EXISTS idx_position_jobs_error_code ON position_jobs(error_code);

-- DOWN
-- DROP INDEX IF EXISTS idx_position_jobs_error_code;
-- ALTER TABLE position_jobs DROP COLUMN IF EXISTS error_code;
