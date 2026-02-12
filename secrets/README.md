# Required Secrets

Minimal configuration for Asgard Basis.

## Required Files

| File | Purpose | How to Get |
|------|---------|------------|
| `asgard_api_key.txt` | Asgard Finance API | asgard.finance |
| `privy_app_id.txt` | Privy app ID | dashboard.privy.io |
| `privy_app_secret.txt` | Privy app secret | dashboard.privy.io |
| `solana_rpc_url.txt` | Solana RPC | helius.dev or quicknode.com |
| `arbitrum_rpc_url.txt` | Arbitrum RPC | alchemy.com or infura.io |
| `privy_auth.pem` | Signing key | Generate locally |
| `server_secret.txt` | Internal auth | Generate locally |

## Quick Setup

```bash
cd secrets

# 1. Create your secrets (get values from respective services)
echo "your-asgard-api-key" > asgard_api_key.txt
echo "your-privy-app-id" > privy_app_id.txt
echo "your-privy-app-secret" > privy_app_secret.txt
echo "https://your-solana-rpc.com" > solana_rpc_url.txt
echo "https://your-arbitrum-rpc.com" > arbitrum_rpc_url.txt

# 2. Generate local secrets
openssl rand -hex 32 > server_secret.txt
openssl ecparam -name prime256v1 -genkey -noout -out privy_auth.pem

# 3. Register public key in Privy dashboard
openssl ec -in privy_auth.pem -pubout -out privy_auth.pub.pem
cat privy_auth.pub.pem  # Copy this to Privy dashboard

# 4. Set permissions
chmod 600 *.txt *.pem
```

## Verify

```bash
ls -la *.txt *.pem
```

You should have 7 files total.
