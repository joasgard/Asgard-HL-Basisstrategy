-- Migration 012: Add deposit_stage column for bridge reconciliation (N3)
--
-- Tracks granular deposit progress:
--   initiated      → job created, not yet submitted
--   bridge_confirmed → on-chain tx confirmed, waiting for HL credit
--   hl_credited    → HL clearinghouse received the funds
--
-- Enables detection and reconciliation of deposits stuck at bridge_confirmed.

ALTER TABLE deposit_history
    ADD COLUMN IF NOT EXISTS deposit_stage TEXT
    DEFAULT 'initiated'
    CHECK (deposit_stage IN ('initiated', 'bridge_confirmed', 'hl_credited'));

-- Index for finding stuck deposits efficiently
CREATE INDEX IF NOT EXISTS idx_deposit_history_stage
    ON deposit_history(deposit_stage, completed_at)
    WHERE direction = 'deposit' AND deposit_stage = 'bridge_confirmed';
