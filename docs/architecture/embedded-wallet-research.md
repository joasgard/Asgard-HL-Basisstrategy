# Embedded Wallet Infrastructure Research

**Date:** 2024-01-15  
**Status:** ✅ IMPLEMENTED (2026-02-05)
**Purpose:** Evaluate external wallet services for BasisStrategy trading bot  
**Key Requirement:** Server-side automated signing for algorithmic trading

> **Implementation Complete:** This bot now uses **Privy** for all wallet operations. See [privy-migration-plan.md](privy-migration-plan.md) for migration details.

---

## Executive Summary

For a trading bot requiring automated server-side signing, **Privy** is the recommended choice based on:
- Best pricing for high-frequency signing (50K free, then $0.001-0.005/sig)
- Mature server-side signing APIs
- Strong security (TEEs, key sharding)
- Multi-chain support (Arbitrum, Hyperliquid)

**Alternative:** Self-hosted solution (more secure, more operational burden)

---

## Service Comparison

### 1. Privy ⭐ Recommended

**Website:** https://privy.io  
**Best For:** Server-side automated signing, high-frequency trading

#### Features
- ✅ **Server-side signing** via NodeJS SDK or REST API
- ✅ **Multi-chain:** EVM (Arbitrum), Solana, Bitcoin, 100+ chains
- ✅ **Self-custodial:** Users control keys, Privy never sees them
- ✅ **Policy engine:** Restrict what server can do (amount limits, contract allowlists)
- ✅ **Secure enclaves (TEEs):** Keys sharded, reconstituted in secure hardware
- ✅ **Key quorums:** m-of-n signing (e.g., server + user both required)

#### Pricing
| Tier | Cost | Includes |
|------|------|----------|
| Developer | Free | 50K signatures/month |
| Enterprise | Custom | $0.001-0.005/signature |

**For trading bot:**
- 10 trades/day × 30 days = 300 signatures
- 300 sigs × 2 chains = 600 signatures/month
- **Cost: FREE** (well under 50K limit)

#### Server-Side Signing Architecture
```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Your Server    │────▶│  Privy API       │────▶│  Secure Enclave │
│  (Trading Bot)  │◀────│  (TEE)           │◀────│  (Key Shard)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │
    Signs with auth key
    (you control this)
```

**Implementation:**
```python
from privy import PrivyClient

# Initialize with app authorization key
privy = PrivyClient(
    app_id="your-app-id",
    app_secret="your-secret",
    authorization_private_key="your-ecdsa-key.pem"
)

# Sign transaction server-side
signed_tx = await privy.wallet.sign_transaction(
    wallet_address="0x...",
    transaction={
        "to": "0x...",
        "value": "1000000000000000000",
        "data": "0x..."
    }
)
```

#### Pros
- Cheapest for high-frequency signing
- Mature documentation
- Policy controls limit blast radius
- Can require user + server both sign (2-of-2)
- SOC 2 compliant

#### Cons
- Third-party dependency
- Vendor lock-in (proprietary infrastructure)
- Requires internet connection for signing

---

### 2. Dynamic (by Fireblocks)

**Website:** https://dynamic.xyz  
**Best For:** User-facing wallets, mobile apps

#### Features
- ✅ Server wallets ("Server Wallets")
- ✅ MPC with threshold signing (TSS)
- ✅ 100+ EVM chains
- ✅ Fireblocks security inheritance
- ✅ Smart wallets (ERC-4337)

#### Pricing
| Tier | Cost | Includes |
|------|------|----------|
| Free | $0 | 1,000 MAUs, 1,000 ops/month |
| Growth | Custom | 5,000 MAUs, 5,000 ops/month |
| Scale | Custom | 10,000+ MAUs |

**"Operations" =** generating, signing, backing up, recovering

**For trading bot:**
- 10 trades/day × 30 days = 300 operations
- **Cost: FREE** (under 1,000 ops/month)

#### Server Wallet Implementation
```typescript
const evmClient = await authenticatedEvmClient({
  authToken: AUTH_TOKEN,
  environmentId: ENVIRONMENT_ID,
});

// Create server-controlled wallet
const { accountAddress, walletId } = await evmClient.createWalletAccount({
  thresholdSignatureScheme: ThresholdSignatureScheme.TWO_OF_TWO,
  password: "optional-password"
});

// Sign transaction
const signedTx = await evmClient.signTransaction({
  walletId,
  transaction: { /* tx data */ }
});
```

#### Pros
- Backed by Fireblocks (institutional security)
- Strong MPC implementation
- Smart account support (ERC-4337)
- Good for mobile/web apps

#### Cons
- More expensive than Privy at scale
- Newer server wallet feature (less mature)
- Pricing less transparent

---

### 3. Turnkey

**Website:** https://turnkey.com  
**Best For:** Enterprises, compliance-heavy environments

#### Features
- ✅ Secure enclaves (AWS Nitro)
- ✅ Passkey authentication
- ✅ Key import/export
- ✅ Policy engine

#### Pricing
| Tier | Cost | Includes |
|------|------|----------|
| Free | $0 | 25 signatures |
| Pro | Custom | $0.01/signature (bulk) |
| Enterprise | Custom | Custom pricing |

**For trading bot:**
- 300 signatures/month
- **Cost: ~$27.50** (275 sigs × $0.10)
- Or upgrade to Pro for better rates

#### Pros
- Very secure (AWS Nitro enclaves)
- Good compliance features
- Fast signing (50-100ms)

#### Cons
- **Most expensive option**
- Limited free tier
- Newer player (less battle-tested)

---

### 4. Web3Auth

**Website:** https://web3auth.io  
**Best For:** User authentication, social logins

#### Pricing
| Tier | Cost | Includes |
|------|------|----------|
| Base | Free | Limited MAWs |
| Growth | $69/month | 3,000 MAWs |
| Scale | $399/month | More MAWs |

**For trading bot:**
- Not ideal—focused on user auth, not server signing
- More expensive for automated use

#### Verdict
❌ **Not recommended** for pure server-side trading

---

### 5. Self-Hosted (DIY MPC)

**Options:**
- Fystack (https://fystack.io)
- Open-source MPC libraries (DKG, threshold signatures)
- HashiCorp Vault with Ethereum plugin

#### Architecture
```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Bot Logic  │────▶│  Your MPC Node  │────▶│  Key Shard 1    │
└─────────────┘     │  (Self-hosted)  │     │  (HSM/Secure)   │
                    │                 │     ├─────────────────┤
                    │  Shamir Secret  │────▶│  Key Shard 2    │
                    │  Sharing (TSS)  │     │  (HSM/Secure)   │
                    │                 │     ├─────────────────┤
                    │  Threshold = 2  │────▶│  Key Shard 3    │
                    │                 │     │  (Offline/cold) │
                    └─────────────────┘     └─────────────────┘
```

#### Pros
- ✅ **Maximum security** (you control everything)
- ✅ No vendor lock-in
- ✅ No per-transaction fees
- ✅ Can run air-gapped

#### Cons
- ❌ **High operational complexity**
- ❌ Need DevOps/security expertise
- ❌ You're responsible for backups, HA, monitoring
- ❌ Slow to implement

#### When to Choose
- Managing >$10M AUM
- Institutional/compliance requirements
- Have dedicated DevOps team

---

## Recommendation Matrix

| Scenario | Recommended | Why |
|----------|-------------|-----|
| **MVP/Startup** (< $1M AUM) | Privy | Free tier sufficient, fast setup |
| **Growth** ($1-10M AUM) | Privy or Dynamic | Both scale well, good policies |
| **Enterprise** (>$10M AUM) | Self-hosted or Turnkey | Maximum control, compliance |
| **High-frequency** (1000+ tx/day) | Privy | Best per-signature pricing |
| **DeFi protocol** | Self-hosted | Decentralization ethos |
| **Regulated entity** | Turnkey or Self-hosted | Compliance features |

---

## Recommendation for BasisStrategy

### Phase 1: MVP (Now)
**Use: Privy**

**Rationale:**
1. **Free** for your expected volume (300-600 sigs/month)
2. **Fastest time-to-market** (days vs weeks)
3. **Server-side signing** mature and well-documented
4. **Policy controls** limit risk if bot is compromised
5. **Can require 2-of-2** (user + server) for large trades

**Setup:**
```python
# Trading bot signs automatically for small trades
if trade_size < $10K:
    # Server-only signature
    signed_tx = await privy.wallet.sign_transaction(wallet_address, tx)
else:
    # Require user approval (2-of-2)
    signed_tx = await privy.wallet.sign_with_quorum(wallet_address, tx, quorum_id)
```

### Phase 2: Scale (Future)
**Evaluate: Self-hosted MPC**

**Trigger:** When AUM > $5M or transaction volume > 10K/month

**Migration path:**
1. User exports key from Privy
2. Import to self-hosted MPC
3. Gradual migration with testing

---

## Security Considerations

### With Privy/Dynamic

**Threat Model:**
| Threat | Mitigation |
|--------|------------|
| Service compromise | Keys sharded in TEEs, no single point of failure |
| Your server hacked | Policy limits (max amount, contract allowlist) |
| Insider at Privy | TEEs prevent even Privy from accessing keys |
| Network interception | TLS 1.3, certificate pinning |
| Privy shutdown | User can export keys anytime |

**Best Practices:**
1. **Policy limits:** Set max transaction amount per day
2. **Contract allowlist:** Only allow trading on specific DEXs
3. **Webhook notifications:** Alert on every transaction
4. **Multi-sig for large trades:** Require user approval >$10K

### With Self-Hosted

**Critical requirements:**
1. **HSMs** (Hardware Security Modules) for key shards
2. **Air-gapped backup** of recovery key
3. **Monitoring:** Alerts on failed signing attempts
4. **DR plan:** Test key recovery quarterly

---

## Implementation Plan

### Option A: Privy (Recommended)

**Week 1:**
- [ ] Create Privy account
- [ ] Generate app authorization key
- [ ] Integrate NodeJS SDK
- [ ] Implement basic signing

**Week 2:**
- [ ] Set up policies (spend limits, contract allowlist)
- [ ] Implement webhook monitoring
- [ ] Test with small amounts

**Week 3:**
- [ ] Production deployment
- [ ] Document export process for users

**Ongoing costs:** $0 (under 50K sigs/month)

### Option B: Self-Hosted

**Month 1-2:**
- [ ] Research MPC libraries (TSS, DKG)
- [ ] Set up HSM infrastructure
- [ ] Implement key ceremony

**Month 3:**
- [ ] Testing and auditing
- [ ] Documentation

**Ongoing costs:** HSM infrastructure ($500-2000/month)

---

## Open Questions

1. **Volume projection:** How many trades/day expected?
2. **AUM target:** What's the 12-month asset target?
3. **Compliance needs:** Any regulatory requirements (KYC, AML)?
4. **Multi-sig preference:** Should large trades require user approval?

---

## Conclusion

**Start with Privy.** It's free for your volume, secure, and lets you focus on building the trading logic rather than wallet infrastructure. The policy controls provide safety rails, and you can always migrate to self-hosted later as you scale.

**Decision tree:**
```
AUM < $5M and want fast launch?
├── YES → Use Privy (free, fast, secure)
└── NO  → Evaluate self-hosted MPC
    ├── Have DevOps team? → Self-hosted
    └── Need compliance? → Turnkey
```
