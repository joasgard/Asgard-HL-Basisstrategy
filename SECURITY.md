# Security Policy

This document outlines security practices for the Delta Neutral Arb trading bot.

## Quick Start for Security

1. **Never commit secrets** - Use `secrets/` directory or environment variables
2. **Use separate wallets** - Different keys for dev/staging/production
3. **Restrict file permissions** - `chmod 600` on credential files
4. **Review before sharing** - Run `git status` to verify no secrets are staged

## Credential Storage

### Option 1: Secrets Directory (Recommended for Production)

Store credentials in individual files:

```bash
# Copy templates
cp secrets/asgard_api_key.txt.example secrets/asgard_api_key.txt
cp secrets/solana_private_key.txt.example secrets/solana_private_key.txt
cp secrets/hyperliquid_private_key.txt.example secrets/hyperliquid_private_key.txt

# Add actual credentials
echo "your_api_key" > secrets/asgard_api_key.txt
echo "your_private_key" > secrets/solana_private_key.txt

# Set restrictive permissions
chmod 600 secrets/*.txt
```

**Protected by .gitignore:**
- All files in `secrets/` are ignored except `.gitkeep`, `README.md`, and `*.example`
- Real credential files will never be committed

### Option 2: Environment Variables

```bash
# Export in your shell
export ASGARD_API_KEY="your_key"
export SOLANA_PRIVATE_KEY="your_key"
export HYPERLIQUID_PRIVATE_KEY="your_key"
```

### Option 3: .env File (Development Only)

```bash
# Copy example
cp .env.example .env

# Edit with your credentials
# .env is git-ignored automatically
```

## Required Secrets

| Variable | Purpose | Source |
|----------|---------|--------|
| `ASGARD_API_KEY` | Asgard Finance API access | Asgard Dashboard |
| `SOLANA_PRIVATE_KEY` | Solana wallet for transactions | Generate new or use existing |
| `HYPERLIQUID_PRIVATE_KEY` | Hyperliquid wallet (separate from Solana) | Generate new - must be secp256k1 |
| `HYPERLIQUID_WALLET_ADDRESS` | Hyperliquid wallet address | From wallet |
| `ADMIN_API_KEY` | Bot pause/resume API | Generate random string |

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
```

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

## Key Security Principles

### 1. Key Separation
- **Never reuse keys** across different environments
- **Separate keys for Solana and Hyperliquid** (different curve types)
- **Different keys for dev/staging/production**

### 2. Hardware Wallets (Production)
For production deployments:
- Store private keys in hardware wallets (Ledger/Trezor)
- Use AWS KMS or similar for cloud deployments
- Never store production keys in plain text files

### 3. State Storage Security
- Only **signatures** are stored in SQLite (not full transactions)
- Signatures alone cannot be used to replay transactions
- Database file is git-ignored

### 4. Transaction Validation
All transactions are validated against allowlists before signing:
- Solana: Only known program IDs (Marginfi, Kamino, Solend, Drift, Asgard)
- Hyperliquid: EIP-712 domain and chain ID verification

## Incident Response

### If You Accidentally Commit a Secret:

1. **Immediately revoke/rotate the exposed credential**
   - Generate new API keys
   - Transfer funds to new wallets if private keys exposed

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

## Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. Contact the maintainers directly
3. Provide detailed description and reproduction steps
4. Allow time for patch before public disclosure

## Additional Resources

- [GitHub: Removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- [OWASP: Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
