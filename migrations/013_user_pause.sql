-- Migration 013: Add per-user pause state (6.5)
--
-- Allows pausing individual users without affecting others.
-- Global kill switch remains separate (file-based).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS paused_reason TEXT;
