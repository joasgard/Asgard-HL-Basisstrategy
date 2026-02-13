-- Migration: Add server wallet columns to users table
-- Version: 11
-- Adds Privy server wallet IDs and addresses for per-user server wallets.
-- UNIQUE constraints prevent duplicate wallet assignment (N1).

ALTER TABLE users ADD COLUMN IF NOT EXISTS server_evm_wallet_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS server_evm_address TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS server_solana_wallet_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS server_solana_address TEXT;

-- Prevent duplicate wallet assignment (N1: concurrent provisioning guard)
-- A wallet should only be assigned to one user.
ALTER TABLE users ADD CONSTRAINT uq_server_evm_wallet UNIQUE (server_evm_wallet_id);
ALTER TABLE users ADD CONSTRAINT uq_server_solana_wallet UNIQUE (server_solana_wallet_id);

-- Index for looking up users by server wallet address
CREATE INDEX IF NOT EXISTS idx_users_server_evm ON users(server_evm_address);
CREATE INDEX IF NOT EXISTS idx_users_server_solana ON users(server_solana_address);

-- DOWN
ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_server_evm_wallet;
ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_server_solana_wallet;
DROP INDEX IF EXISTS idx_users_server_evm;
DROP INDEX IF EXISTS idx_users_server_solana;
ALTER TABLE users DROP COLUMN IF EXISTS server_evm_wallet_id;
ALTER TABLE users DROP COLUMN IF EXISTS server_evm_address;
ALTER TABLE users DROP COLUMN IF EXISTS server_solana_wallet_id;
ALTER TABLE users DROP COLUMN IF EXISTS server_solana_address;
