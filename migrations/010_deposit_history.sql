-- Migration 010: Deposit/withdrawal history tracking
--
-- Tracks user-initiated USDC bridge deposits (Arb → HL) and
-- withdrawals (HL → Arb) with status and transaction hashes.

CREATE TABLE IF NOT EXISTS deposit_history (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    direction TEXT NOT NULL CHECK (direction IN ('deposit', 'withdraw')),
    amount_usdc REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    approve_tx_hash TEXT,
    bridge_tx_hash TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_deposit_history_user
    ON deposit_history(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_deposit_history_status
    ON deposit_history(status)
    WHERE status IN ('pending', 'running');
