# Security Policy

This document outlines security practices for the Delta Neutral Arb trading bot.

## Quick Start for Security

1. **Never commit secrets** - Use `secrets/` directory or environment variables
2. **Use Privy for wallet security** - No private keys stored locally
3. **Use separate wallets** - Different addresses for dev/staging/production
4. **Restrict file permissions** - `chmod 600` on credential files
5. **Review before sharing** - Run `git status` to verify no secrets are staged

---

## Wallet Infrastructure (Privy)

This bot uses **Privy** for secure wallet infrastructure. Private keys are **never stored locally**.

### How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Your Server    │────▶│  Privy API       │────▶│  Secure Enclave │
│  (Trading Bot)  │◀────│  (TEE)           │◀────│  (Key Shard)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │
    Signs with auth key
    (you control this - privy_auth.pem)
```

**Key Benefits:**
- ✅ **No local private keys** - Keys are sharded in Privy's TEE infrastructure
- ✅ **Server-side signing** - Automated signing for algorithmic trading
- ✅ **Policy controls** - Set limits on transaction amounts and destinations
- ✅ **SOC 2 compliant** - Enterprise-grade security
- ✅ **Key export** - You can export keys anytime for backup

### Setting Up Privy

1. **Create Account**: [https://privy.io](https://privy.io)
2. **Generate Auth Key**: `openssl ecparam -name prime256v1 -genkey -noout -out privy_auth.pem`
3. **Register Public Key**: Upload `privy_auth.pub` in Privy dashboard
4. **Create Wallets**: Use Privy dashboard or SDK to create EVM and Solana wallets

---

## Credential Storage

### Option 1: Secrets Directory (Recommended for Production)

Store credentials in individual files:

```bash
# Copy templates
cp secrets/asgard_api_key.txt.example secrets/asgard_api_key.txt
cp secrets/privy_app_id.txt.example secrets/privy_app_id.txt
cp secrets/privy_app_secret.txt.example secrets/privy_app_secret.txt
cp secrets/wallet_address.txt.example secrets/wallet_address.txt
cp secrets/solana_wallet_address.txt.example secrets/solana_wallet_address.txt

# Add actual credentials
echo "your_api_key" > secrets/asgard_api_key.txt
echo "your_privy_app_id" > secrets/privy_app_id.txt
echo "your_privy_app_secret" > secrets/privy_app_secret.txt
echo "0x...your_evm_address..." > secrets/wallet_address.txt
echo "...your_solana_address..." > secrets/solana_wallet_address.txt

# Copy your Privy authorization key
cp privy_auth.pem secrets/

# Set restrictive permissions
chmod 600 secrets/*.txt
chmod 600 secrets/*.pem
```

**Protected by .gitignore:**
- All files in `secrets/` are ignored except `.gitkeep`, `README.md`, and `*.example`
- Real credential files will never be committed

### Option 2: Environment Variables

```bash
# Export in your shell
export ASGARD_API_KEY="your_key"
export PRIVY_APP_ID="your_app_id"
export PRIVY_APP_SECRET="your_secret"
export WALLET_ADDRESS="0x...your_evm_address..."
export SOLANA_WALLET_ADDRESS="...your_solana_address..."
```

### Option 3: .env File (Development Only)

```bash
# Copy example
cp .env.example .env

# Edit with your credentials
# .env is git-ignored automatically
```

---

## Required Secrets

| Variable | Purpose | Source |
|----------|---------|--------|
| `ASGARD_API_KEY` | Asgard Finance API access | Asgard Dashboard |
| `PRIVY_APP_ID` | Privy application identifier | Privy Dashboard |
| `PRIVY_APP_SECRET` | Privy application secret | Privy Dashboard |
| `PRIVY_AUTH_KEY_PATH` | Path to your ECDSA auth key | Generated locally |
| `WALLET_ADDRESS` | EVM wallet address (for Hyperliquid) | Privy Dashboard |
| `SOLANA_WALLET_ADDRESS` | Solana wallet address (for Asgard) | Privy Dashboard |
| `HYPERLIQUID_WALLET_ADDRESS` | Hyperliquid wallet address | From wallet |
| `ADMIN_API_KEY` | Bot pause/resume API | Generate random string |

---

## Security Checklist

Before committing code:

```bash
# 1. Check what's being committed
git status

# 2. Review all staged files
git diff --cached --name-only

# 3. Ensure no secrets in diff
git diff --cached | grep -i -E "(key|secret|private|password)" | head -20

# 4. Verify .gitignore is working
git check-ignore -v secrets/asgard_api_key.txt
# Should output: .gitignore:44:secrets/*    secrets/asgard_api_key.txt

# 5. Verify no private key files exist
ls secrets/*private_key* 2>/dev/null && echo "WARNING: Found private key files!" || echo "✓ No private key files"
```

---

## What Gets Protected

### Automatically Ignored:
- `secrets/*` - All secret files (except templates)
- `.env` - Environment files
- `*.key`, `*.pem` - Key files
- `*.db`, `*.sqlite` - Databases
- `*.log` - Log files
- Files with "private", "secret", "credential" in name

### What IS Committed:
- `secrets/*.example` - Template files with placeholder values
- `secrets/README.md` - Documentation
- `secrets/.gitkeep` - Directory placeholder
- `.env.example` - Example environment file

---

## Key Security Principles

### 1. No Local Private Keys
**Previous approach (deprecated):**
```bash
# OLD - Private keys stored locally (DANGEROUS)
echo "private_key" > secrets/solana_private_key.txt
echo "private_key" > secrets/hyperliquid_private_key.txt
```

**New approach (Privy):**
```bash
# NEW - Only public addresses stored locally
echo "0x...address..." > secrets/wallet_address.txt
echo "...address..." > secrets/solana_wallet_address.txt
# Private keys are safely stored in Privy's TEE infrastructure
```

### 2. Key Separation
- **Never reuse wallets** across different environments
- **Separate wallets for Solana and Hyperliquid** (different chains)
- **Different wallets for dev/staging/production**

### 3. Privy Policy Controls
Set up policies in Privy dashboard to limit risk:

| Policy | Recommendation |
|--------|----------------|
| Daily spend limit | Set based on your trading volume |
| Contract allowlist | Only allow Hyperliquid and Asgard contracts |
| Transaction webhook | Alert on every transaction |
| 2-of-2 signing | Require manual approval for trades >$10K |

### 4. State Storage Security
- Only **signatures** are stored in SQLite (not full transactions)
- Signatures alone cannot be used to replay transactions
- Database file is git-ignored

### 5. Transaction Validation
All transactions are validated against allowlists before signing:
- Solana: Only known program IDs (Marginfi, Kamino, Solend, Drift, Asgard)
- Hyperliquid: EIP-712 domain and chain ID verification

---

## Incident Response

### If You Accidentally Commit a Secret:

1. **Immediately revoke/rotate the exposed credential**
   - Generate new API keys in Privy dashboard
   - Create new wallets if addresses were exposed (funds are safe, but privacy compromised)

2. **Remove from git history** (if pushed):
   ```bash
   git filter-branch --force --index-filter \
   'git rm --cached --ignore-unmatch path/to/secret' \
   --prune-empty --tag-name-filter cat -- --all
   ```

3. **Force push** (coordinate with team):
   ```bash
   git push origin --force --all
   ```

4. **Audit access logs** for any unauthorized usage

---

## Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. Contact the maintainers directly
3. Provide detailed description and reproduction steps
4. Allow time for patch before public disclosure

---

## Additional Resources

- [Privy Documentation](https://docs.privy.io/)
- [GitHub: Removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- [OWASP: Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
