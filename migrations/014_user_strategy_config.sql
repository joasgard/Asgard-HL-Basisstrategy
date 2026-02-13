-- Migration 014: Per-user strategy configuration (7.1.1)
--
-- Stores each user's autonomous trading parameters.
-- Defaults produce a conservative strategy (see shared/config/strategy_defaults.py).
-- Supports optimistic locking via `version` column (C5)
-- and cooldown bypass prevention via `cooldown_at_close` (N6).

CREATE TABLE IF NOT EXISTS user_strategy_config (
    user_id           TEXT PRIMARY KEY REFERENCES users(id),
    enabled           BOOLEAN   DEFAULT FALSE,

    -- Asset / pair configuration
    assets            TEXT[]    DEFAULT ARRAY['SOL'],
    protocols         TEXT[]    DEFAULT NULL,

    -- Entry thresholds
    min_carry_apy         REAL DEFAULT 15.0,
    min_funding_rate_8hr  REAL DEFAULT 0.005,
    max_funding_volatility REAL DEFAULT 0.5,

    -- Position sizing
    max_position_pct          REAL    DEFAULT 0.25,
    max_concurrent_positions  INTEGER DEFAULT 2,
    max_leverage              REAL    DEFAULT 3.0,

    -- Exit thresholds
    min_exit_carry_apy  REAL DEFAULT 5.0,
    take_profit_pct     REAL DEFAULT NULL,
    stop_loss_pct       REAL DEFAULT 10.0,

    -- Recurse
    auto_reopen       BOOLEAN DEFAULT TRUE,
    cooldown_minutes  INTEGER DEFAULT 30,

    -- Cooldown enforcement (N6)
    last_close_time   TIMESTAMP DEFAULT NULL,
    cooldown_at_close INTEGER   DEFAULT NULL,

    -- Optimistic locking (C5)
    version           INTEGER   DEFAULT 1,

    -- Metadata
    updated_at        TIMESTAMP DEFAULT NOW(),
    paused_at         TIMESTAMP DEFAULT NULL,
    paused_reason     TEXT      DEFAULT NULL
);
