# Secrets Directory

This directory contains sensitive API keys and configuration that should **NEVER** be committed to git.

## Security Warning

⚠️ **IMPORTANT**: Files in this directory contain sensitive credentials. Never commit them to version control.

## Overview

This bot uses **Privy** for secure wallet infrastructure. Unlike traditional setups, **no private keys are stored locally**. Only public wallet addresses and API credentials are stored here.

```
┌─────────────────────────────────────────────────────────────┐
│  YOUR SERVER                                                │
│  ├── secrets/wallet_address.txt          (public address)   │
│  ├── secrets/solana_wallet_address.txt   (public address)   │
│  ├── secrets/privy_app_id.txt            (app identifier)   │
│  └── secrets/privy_app_secret.txt        (app secret)       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  PRIVY INFRASTRUCTURE (Secure TEEs)                         │
│  ├── Private keys sharded across secure enclaves            │
│  ├── Keys never exposed, even to Privy employees            │
│  └── Server-side signing via API                            │
└─────────────────────────────────────────────────────────────┘
```

## Setup Instructions

### 1. Set Up Privy Account

Before configuring secrets, you need a Privy account:

1. Go to [https://privy.io](https://privy.io) and sign up
2. Create a new app
3. Get your App ID and App Secret
4. Generate an authorization key:
   ```bash
   openssl ecparam -name prime256v1 -genkey -noout -out privy_auth.pem
   ```
5. Register the public key in Privy dashboard
6. Create wallets (EVM for Hyperliquid, Solana for Asgard)

See [GETTING_STARTED.md](../GETTING_STARTED.md) for detailed instructions.

### 2. Copy and Configure Secret Files

```bash
# Copy the example files (remove `.example` suffix):
cp asgard_api_key.txt.example asgard_api_key.txt
cp privy_app_id.txt.example privy_app_id.txt
cp privy_app_secret.txt.example privy_app_secret.txt
cp wallet_address.txt.example wallet_address.txt
cp solana_wallet_address.txt.example solana_wallet_address.txt
cp hyperliquid_wallet_address.txt.example hyperliquid_wallet_address.txt
cp admin_api_key.txt.example admin_api_key.txt

# Copy your Privy authorization key
cp /path/to/privy_auth.pem .
```

### 3. Add Your Credentials

Replace placeholder values with your actual credentials in each `.txt` file:

```
# wallet_address.txt - EVM address from Privy
0x1234567890abcdef...

# solana_wallet_address.txt - Solana address from Privy
HN7cAB5L9j8rBZKF...

# privy_app_id.txt
your-privy-app-id
```

### 4. Set Restrictive Permissions

```bash
chmod 600 *.txt
chmod 600 *.pem
```

## File Format

Each `.txt` file should contain only the credential value, with no quotes, no newlines, and no extra formatting:

```
your_actual_api_key_here
```

## Required Secrets

| File | Purpose | Format | Example |
|------|---------|--------|---------|
| `asgard_api_key.txt` | Asgard Finance API key | String | `ag-...` |
| `privy_app_id.txt` | Privy application ID | String | `cl...` |
| `privy_app_secret.txt` | Privy application secret | String | `privy-secret-...` |
| `privy_auth.pem` | Your ECDSA private key for Privy auth | PEM file | Generated locally |
| `wallet_address.txt` | EVM wallet address (for Hyperliquid) | Hex address | `0x...` |
| `solana_wallet_address.txt` | Solana wallet address (for Asgard) | Base58 | `HN7...` |
| `hyperliquid_wallet_address.txt` | Hyperliquid wallet address | Hex address | `0x...` |
| `admin_api_key.txt` | Admin API key for pause/resume | String | Generate random |

## Optional Secrets

| File | Purpose | Format |
|------|---------|--------|
| `arbitrum_rpc_url.txt` | Custom Arbitrum RPC URL | URL |
| `solana_rpc_url.txt` | Custom Solana RPC URL | URL |
| `sentry_dsn.txt` | Sentry error tracking DSN | URL |

## Alternative: Environment Variables

Instead of using files in this directory, you can set credentials via environment variables in your `.env` file:

```bash
ASGARD_API_KEY=your_key_here
PRIVY_APP_ID=your_app_id
PRIVY_APP_SECRET=your_secret
PRIVY_AUTH_KEY_PATH=privy_auth.pem
WALLET_ADDRESS=0x...your_evm_address...
SOLANA_WALLET_ADDRESS=...your_solana_address...
HYPERLIQUID_WALLET_ADDRESS=0x...
ADMIN_API_KEY=your_secure_key
```

Environment variables take precedence over files in this directory.

## Backup Strategy

### Critical: Back Up Your Privy Authorization Key

The `privy_auth.pem` file is your access credential to Privy. If lost:
- Generate a new key pair: `openssl ecparam -name prime256v1 -genkey -noout -out privy_auth.pem`
- Register the new public key in Privy dashboard
- Update `secrets/privy_auth.pem`

### Wallet Backup

Your wallet private keys are stored securely in Privy's infrastructure:
1. **Export option**: You can export wallet keys from Privy dashboard anytime
2. **Recovery**: Use Privy's recovery mechanisms if needed
3. **Recommendation**: Document your wallet addresses and keep recovery info in a secure password manager

### API Key Backup

- **Asgard API Key**: Can be regenerated in Asgard dashboard
- **Privy App Secret**: Can be regenerated in Privy dashboard (requires updating config)
- **Admin API Key**: Self-generated, create a new one if lost

## Migration from Local Key Storage

If you previously used this bot with local private key storage:

1. **Remove old private key files**:
   ```bash
   rm solana_private_key.txt hyperliquid_private_key.txt
   ```

2. **Set up Privy** as described above

3. **Fund your new Privy wallets** with the same amounts

4. **Verify**: No files matching `*private_key*` should exist in this directory

## Loss of Access

If you lose access:

| Item | Recovery Method |
|------|-----------------|
| **Asgard API Key** | Generate new one in Asgard dashboard |
| **Privy Auth Key** | Generate new key pair and register in dashboard |
| **Privy App Secret** | Regenerate in Privy dashboard |
| **Wallet Access** | Use Privy's wallet export/recovery features |
| **Admin API Key** | Generate new random string |

## Important Reminders

- ✅ **No private keys stored locally** - Everything is in Privy's secure infrastructure
- ✅ **Regular backups** - Keep copies of your `privy_auth.pem` in secure locations
- ✅ **Separate environments** - Use different Privy apps for dev/staging/prod
- ✅ **Monitor usage** - Check Privy dashboard for signing activity
- ❌ **Never commit** - These files are git-ignored for a reason
- ❌ **Never share** - Don't share your `privy_auth.pem` or app secrets
