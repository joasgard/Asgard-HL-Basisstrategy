-- 015: Per-user risk tracking (7.3.1–7.3.3)
--
-- Tracks: peak balance (drawdown), daily trade count, consecutive failures.
-- Used by UserRiskManager to enforce risk limits and auto-pause users.

CREATE TABLE IF NOT EXISTS user_risk_tracking (
    user_id              TEXT PRIMARY KEY REFERENCES users(id),

    -- 7.3.1: Drawdown tracking
    peak_balance_usd     NUMERIC     DEFAULT 0,
    current_balance_usd  NUMERIC     DEFAULT 0,

    -- 7.3.2: Daily trade count
    daily_trade_count    INTEGER     DEFAULT 0,
    daily_trade_date     DATE        DEFAULT CURRENT_DATE,

    -- 7.3.3: Consecutive failure circuit breaker
    consecutive_failures INTEGER     DEFAULT 0,
    last_failure_reason  TEXT        DEFAULT NULL,
    last_failure_at      TIMESTAMP   DEFAULT NULL,

    updated_at           TIMESTAMP   DEFAULT NOW()
);

-- Index for monitor queries (find users needing drawdown check)
CREATE INDEX IF NOT EXISTS idx_user_risk_tracking_peak
    ON user_risk_tracking (user_id) WHERE peak_balance_usd > 0;
