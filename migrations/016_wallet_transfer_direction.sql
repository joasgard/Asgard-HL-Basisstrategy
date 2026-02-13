-- Migration 016: Allow 'wallet_transfer' direction in deposit_history
--
-- The "From Wallet" USDC withdraw flow now routes through the backend
-- (server-side signing) instead of client-side embedded wallet signing.
-- These jobs use direction = 'wallet_transfer'.

ALTER TABLE deposit_history
    DROP CONSTRAINT IF EXISTS deposit_history_direction_check;

ALTER TABLE deposit_history
    ADD CONSTRAINT deposit_history_direction_check
    CHECK (direction IN ('deposit', 'withdraw', 'wallet_transfer'));
