# Security Policy

## Quick Security Checklist

- [ ] Never commit secrets - `secrets/` is git-ignored
- [ ] Use Privy for wallets - no local private keys
- [ ] Set permissions: `chmod 600 secrets/*`
- [ ] Use separate wallets for dev/prod
- [ ] PostgreSQL password changed from default
- [ ] Redis password set in production

---

## Wallet Security (Privy)

This bot uses **Privy** for secure wallet infrastructure. Private keys are **never stored locally**.

```
+------------------+     +------------------+     +------------------+
|  Your Server     |---->|  Privy API       |---->|  Secure Enclave  |
|  (Trading Bot)   |<----|  (TEE)           |<----|  (Key Shard)     |
+------------------+     +------------------+     +------------------+
         |
    Signs with auth key
    (privy_auth.pem - you control this)
```

**Benefits:**
- No local private keys
- Server-side signing via API
- SOC 2 compliant
- Export keys anytime for backup

---

## Required Secrets (7 Files)

Create in `secrets/` directory:

```bash
# External services
echo "key" > asgard_api_key.txt          # asgard.finance
echo "id" > privy_app_id.txt             # dashboard.privy.io
echo "secret" > privy_app_secret.txt     # dashboard.privy.io
echo "url" > solana_rpc_url.txt          # helius.dev
echo "url" > arbitrum_rpc_url.txt        # alchemy.com

# Generated locally
openssl rand -hex 32 > server_secret.txt
openssl ecparam -name prime256v1 -genkey -noout -out privy_auth.pem

# Set permissions
chmod 600 *.txt *.pem
```

---

## Infrastructure Security

### PostgreSQL

- Change default password (`POSTGRES_PASSWORD` in .env)
- Only accessible within Docker network (not exposed to host in production)
- Connection pooling via asyncpg (min 2, max 10 connections)

### Redis

- AOF persistence enabled for crash recovery
- Memory limited to 256MB with LRU eviction
- Used for: rate limiting, distributed locks, SSE pub/sub
- Not exposed to host in production

### Docker Hardening

| Feature | Implementation |
|---------|---------------|
| Non-root user | `botuser` (UID 1000) |
| Read-only filesystem | `read_only: true` |
| No privilege escalation | `no-new-privileges: true` |
| Minimal capabilities | `cap_drop: ALL` |
| tmpfs for temp files | `/tmp` and `.cache` directories |
| Resource limits | CPU and memory caps |
| Health checks | All services monitored |

---

## Application Security

### Authentication
- Privy Email + OTP (no passwords stored)
- JWT sessions in httpOnly, Secure, SameSite cookies
- Redis-backed rate limiting on auth endpoints

### Encryption
- AES-256-GCM field-level encryption for sensitive config
- KEK derived from HMAC(user_id, server_secret) - never persisted
- DEK stored encrypted by KEK in PostgreSQL

### API Security
- Security headers: HSTS, CSP, X-Frame-Options, X-Content-Type-Options
- CSRF protection on state-changing requests
- Request ID tracking for audit trail
- Structured JSON logging (PII sanitized)

### Transaction Validation
- Only allowed Solana programs can be called
- Only allowed Hyperliquid actions (order, updateLeverage, cancel)
- All transactions validated before Privy signing

---

## Privy Setup

1. **Create account**: [privy.io](https://privy.io)
2. **Generate auth key**: `openssl ecparam -name prime256v1 -genkey -noout -out privy_auth.pem`
3. **Register public key**:
   ```bash
   openssl ec -in privy_auth.pem -pubout -out privy_auth.pub.pem
   cat privy_auth.pub.pem  # Copy to Privy dashboard
   ```
4. **Enable**: Email login + embedded wallets (EVM + Solana)

---

## File Security

```bash
# Verify permissions
ls -la secrets/
# Should show: -rw------- (600)

# Verify gitignore
git status  # No secrets should appear
```

---

## Production Deployment

- Use dedicated server/VPS
- Use `docker-compose.prod.yml` with Nginx for TLS
- Restrict firewall: only ports 80/443 open
- No SSH password auth - use keys only
- Regular updates: `apt update && apt upgrade`
- Monitor health endpoints: `/health/live` and `/health/ready`

---

*Last updated: 2026-02-12*
