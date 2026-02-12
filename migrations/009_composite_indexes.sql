-- Migration 009: Add composite indexes for common query patterns

-- position_jobs: frequently queried by user_id + status
CREATE INDEX IF NOT EXISTS idx_position_jobs_user_status
    ON position_jobs (user_id, status);

-- position_jobs: frequently queried by status alone (for recovery)
CREATE INDEX IF NOT EXISTS idx_position_jobs_status
    ON position_jobs (status) WHERE status = 'running';
