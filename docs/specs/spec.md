# Delta Neutral Bot - Technical Specification v3.5 (SaaS)

**Product**: Delta Neutral Funding Rate Arbitrage Bot  
**Deployment Model**: Multi-user Authentication with Single-Tenant Execution (Hybrid SaaS)  
**Wallet Infrastructure**: Privy Embedded Wallets (server-side signing)  
**Authentication**: Privy Email-Only with Custom Modals (v3.5)  
**Primary Interface**: Web Dashboard with Connect → Email → OTP → Deposit Flow  
**Version**: 3.5 (Custom Privy Auth Flow)

> **⚠️ Architecture Clarification:**
> 
> Current implementation is **multi-user auth + single-tenant execution**:
> - ✅ Multiple users can authenticate via Privy
> - ✅ Each user has their own wallets and settings
> - ⚠️ Position execution is NOT multi-tenant (single bot instance)
> - ⚠️ NOT a true multi-tenant SaaS (one deployment per user required)
>
> For true multi-tenant SaaS (one instance serving many users), see Section 11 "Future SaaS Enhancements".

> **v3.5 Change Log:**
> - **Authentication**: New custom modal flow (email-only, inline OTP, deposit modal)
> - **Header**: Connect button → Deposit + Settings dropdown after login
> - **Session**: "Stay logged in" option (7 days vs 24 hours)
> - **New User Flow**: Automatic deposit modal with QR codes for both chains
> - **See**: [PRIVY_AUTH_SPEC.md](../PRIVY_AUTH_SPEC.md) for detailed auth specification  

---

## 1. Executive Summary

A delta-neutral funding rate arbitrage system deployed as single-tenant containers. Users run their own isolated instance through a web-based setup wizard, with embedded wallets managed via Privy. This specification covers the complete technical implementation including security architecture, authentication, backup/recovery, and operational procedures.

### Strategy Overview

```
┌────────────────────────────────────────────────────────────────┐
│                    ASGARD (Solana)                             │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  LONG Spot Margin Position                           │     │
│  │  • Asset: SOL or SOL LST (jitoSOL, jupSOL, INF)      │     │
│  │  • Direction: LONG (0)                               │     │
│  │  • Leverage: 3-4x (default 3x)                       │     │
│  │  • Protocol: Best rate from Marginfi/Kamino/Solend   │     │
│  └──────────────────────────────────────────────────────┘     │
└────────────────────────┬───────────────────────────────────────┘
                         │ Delta Neutral (Equal Leverage)
┌────────────────────────▼───────────────────────────────────────┐
│               HYPERLIQUID (Arbitrum)                           │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  SHORT Perpetual Position                            │     │
│  │  • Asset: SOL-PERP (SOLUSD)                          │     │
│  │  • Leverage: 3-4x (matches long side)                │     │
│  │  • Funding: Received hourly (1/8 of 8hr rate)        │     │
│  └──────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────┘
```

**Yield Formula**: Hyperliquid funding earned - Asgard net borrowing cost + LST staking yield

---

## 2. SaaS Architecture

### 2.1 Deployment Model

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER BROWSER                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Setup Wizard │  │   Dashboard  │  │   Monitoring UI      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS
┌──────────────────────────▼──────────────────────────────────────┐
│              USER'S DOCKER CONTAINER (Single Tenant)            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  FastAPI + Jinja2/HTMX Dashboard                        │   │
│  │  • Setup wizard endpoints                               │   │
│  │  • Authentication & session management                  │   │
│  │  • Bot control APIs                                     │   │
│  │  • Real-time monitoring (SSE)                           │   │
│  │  • Backup/restore APIs                                  │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         │                                       │
│  ┌──────────────────────▼──────────────────────────────────┐   │
│  │  DeltaNeutralBot Core                                   │   │
│  │  • Opportunity detection                                │   │
│  │  • Position management                                  │   │
│  │  • Risk engine                                          │   │
│  │  • Transaction signing via Privy                        │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         │                                       │
│  ┌──────────────────────▼──────────────────────────────────┐   │
│  │  SQLite (state.db)                                      │   │
│  │  • Encrypted configuration (field-level AES-256-GCM)    │   │
│  │  • Position state                                       │   │
│  │  • Transaction history                                  │   │
│  │  • Audit logs (sanitized)                               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┴───────────────┐
           ▼                               ▼
┌─────────────────────┐        ┌─────────────────────┐
│   PRIVY (Wallets)   │        │   EXTERNAL APIS     │
│  • EVM wallet       │        │  • Asgard Finance   │
│  • Solana wallet    │        │  • Hyperliquid      │
│  • Server signing   │        │  • Solana RPC       │
└─────────────────────┘        └─────────────────────┘
```

### 2.2 Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Tenancy** | Single-tenant | User controls data, simpler security model |
| **Wallets** | Privy embedded | No private keys in container, recoverable, TEE-backed |
| **Setup** | **4-step wizard** (v3.4) | Auth → Wallets → Exchange → Dashboard |
| **Config Storage** | SQLite + field-level encryption | Encrypted at rest, single file backup |
| **State** | SQLite | Unified storage for config + state |
| **UI** | Jinja2 + HTMX + SSE | Server-rendered, minimal JS |
| **Auth** | **Privy OAuth** (shared app) | Email/Google/Twitter login, no config needed |
| **KEK Derivation** | HMAC(user_id, server_secret) | Unique per user |
| **Backup** | **Handled by Privy** | Account recovery via email |
| **Dashboard** | **Trade monitor + action hub** (v3.4) | View status, fund wallets, launch strategy |
| **Access** | Localhost-only + SSH tunnel | Secure by default |

### 2.3 Wallet Infrastructure (Privy)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Privy Key Architecture                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Key Creation                                                            │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐           │
│   │   Shard 1    │     │   Shard 2    │     │   Shard 3    │           │
│   │  (User)      │     │  (Privy)     │     │  (TEE)       │           │
│   │  Device      │     │  Server      │     │  Enclave     │           │
│   └──────┬───────┘     └──────┬───────┘     └──────┬───────┘           │
│          │                    │                    │                    │
│          └────────────────────┴────────────────────┘                    │
│                              │                                          │
│                    Shamir Secret Sharing                               │
│                    (e.g., 2-of-3 threshold)                            │
│                                                                          │
│   Signing Transaction                                                     │
│   ┌─────────────────────────────────────────────────────────┐          │
│   │              TEE (Trusted Execution Environment)          │          │
│   │  ┌─────────────────────────────────────────────────────┐  │          │
│   │  │  • Shards reconstituted inside secure enclave       │  │          │
│   │  │  • Private key never exists in plaintext outside    │  │          │
│   │  │  • Signature computed, key immediately destroyed    │  │          │
│   │  └─────────────────────────────────────────────────────┘  │          │
│   └─────────────────────────────────────────────────────────┘          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Security Properties:**
- ✅ Keys are **sharded** across multiple parties
- ✅ **TEE isolation**: Keys reconstituted only in secure hardware
- ✅ **No plaintext exposure**: Private key never in memory/logs
- ✅ **Non-custodial**: Privy cannot access keys without user shard
- ✅ **Exportable**: Users can export keys for self-custody anytime

**Rate Limiting Considerations:**
- 50K signatures/month on free tier
- Typical usage: 20-40 signatures/day at 5 trades/day
- Tracking: Monitor usage, alert at 80% threshold
- Fallback: Pause trading if limits approached, suggest Privy upgrade

---

## 3. Authentication & Encryption

> **v3.2 Update:** Authentication changed from password-based to Privy OAuth. No user password required.

### 3.1 Two-Tier Key Hierarchy (Privy-Based)

```
┌─────────────────────────────────────────────────────────────┐
│                  ENCRYPTION ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Key Encryption Key (KEK)                            │   │
│  │  • Derived from: HMAC_SHA256(privy_user_id, secret)  │   │
│  │  • Server secret from env (DASHBOARD_SESSION_SECRET) │   │
│  │  • NEVER persisted - only in memory during session   │   │
│  │  • Used to encrypt/decrypt the DEK                   │   │
│  │  • Unique per user+server combination                │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Data Encryption Key (DEK)                           │   │
│  │  • Random 256-bit key generated on first setup       │   │
│  │  • Stored in SQLite encrypted by KEK                 │   │
│  │  • Used for field-level AES-256-GCM encryption       │   │
│  │  • Same DEK encrypts all sensitive fields            │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Encrypted Fields (SQLite)                           │   │
│  │  • privy_app_id, privy_app_secret                    │   │
│  │  • privy_auth_key (PEM)                              │   │
│  │  • asgard_api_key                                    │   │
│  │  • Each field: nonce (12B) || ciphertext || HMAC     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Authentication Flow (Privy Email-Only v3.5)

> **v3.5 Update:** New authentication flow with custom modals. Email-only (no Google/Twitter), inline OTP verification, deposit modal for new users.

**Authentication Flow:**

```
┌─────────────────────────────────────────────────────────────────┐
│  DASHBOARD HEADER                                               │
├─────────────────────────────────────────────────────────────────┤
│  Delta Neutral Bot                           [Connect]          │
│                                    ↓                            │
│                            Click Connect                        │
│                                    ↓                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  EMAIL LOGIN MODAL                                       │   │
│  │  [X]                                                     │   │
│  │                                                          │   │
│  │       [Asgard.png Logo]                                  │   │
│  │                                                          │   │
│  │     Delta Neutral Bot                                    │   │
│  │     Log in or sign up                                    │   │
│  │                                                          │   │
│  │     ┌─────────────────────────┐                          │   │
│  │     │ ✉️  email@example.com   │                          │   │
│  │     └─────────────────────────┘                          │   │
│  │                                                          │   │
│  │           [Continue]                                     │   │
│  │                                                          │   │
│  │     ☐ Stay logged in (for 7 days)                        │   │
│  │                                                          │   │
│  │     Protected by 🔒 Privy                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                    ↓                            │
│                           Submit Email                          │
│                                    ↓                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  OTP VERIFICATION MODAL                                  │   │
│  │  [←] [X]                                                 │   │
│  │                                                          │   │
│  │              [✉️]                                        │   │
│  │                                                          │   │
│  │     Enter confirmation code                              │   │
│  │     Please check your email for a code from privy.io     │   │
│  │                                                          │   │
│  │     [□] [□] [□] [□] [□] [□]                              │   │
│  │                                                          │   │
│  │     Didn't get an email? Resend code (60s)               │   │
│  │                                                          │   │
│  │     Protected by 🔒 Privy                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                    ↓                            │
│                         Enter 6-Digit Code                      │
│                                    ↓                            │
│                         Check: New or Existing?                 │
│                                    ↓                            │
│              ┌─────────────────────┼─────────────────────┐     │
│              │                     │                     │     │
│         Existing User          New User              Existing   │
│              │                     │                     │       │
│              ▼                     ▼                     ▼       │
│  ┌─────────────────┐    ┌─────────────────────────┐    ┌──────┐│
│  │ Check Balance   │    │ DEPOSIT MODAL           │    │ Dash-││
│  │                 │    │                         │    │ board││
│  │ Funded? → Go to │    │  Deposit to Start       │    │      ││
│  │ Dashboard       │    │  Trading            [X] │    │      ││
│  │                 │    │                         │    │      ││
│  │ Not funded? →   │    │  [◎] Solana (Asgard)    │    │      ││
│  │ Show Deposit    │    │  [QR Code]              │    │      ││
│  │ Modal           │    │  0x1234...5678 [Copy]   │    │      ││
│  └─────────────────┘    │                         │    │      ││
│                         │  [◉] Hyperliquid         │    │      ││
│                         │  [QR Code]              │    │      ││
│                         │  0x5678...1234 [Copy]   │    │      ││
│                         │                         │    │      ││
│                         │     [Go to Dashboard]   │    │      ││
│                         └─────────────────────────┘    └──────┘│
└─────────────────────────────────────────────────────────────────┘

POST-LOGIN HEADER STATE:
┌─────────────────────────────────────────────────────────────────┐
│  Delta Neutral Bot                         [Deposit] [⚙️]        │
│                                              ↓ Dropdown          │
│                                              ├─ View Profile     │
│                                              ├─ Settings         │
│                                              └─ Disconnect       │
└─────────────────────────────────────────────────────────────────┘
```

**First-Time Setup (New User):**
1. User clicks "Connect" in dashboard header
2. Email login modal opens (blur backdrop, centered)
3. User enters email, clicks "Continue"
4. Privy sends OTP to email
5. OTP modal appears with 6-digit input
6. User enters code, Privy validates
7. Backend creates user record with Privy user ID
8. Backend calls Privy to create Solana + EVM wallets
9. Wallets stored in `users` table (addresses are public)
10. **NEW:** Deposit modal shows for new users
    - Display both wallet addresses with QR codes
    - Solana address (for Asgard) + Arbitrum address (for Hyperliquid)
    - "Go to Dashboard" button (can skip deposit)
11. Session cookie issued (HTTP-only, Secure, SameSite=Strict)
    - Duration: 7 days if "Stay logged in" checked, else 24 hours

**Returning User:**
1. Click "Connect" → Email modal → OTP modal
2. Backend finds existing user by Privy user ID
3. Check wallet balances on-chain
4. If funded → Go directly to dashboard
5. If not funded → Show deposit modal
6. Session issued with unlocked encryption manager

**Key Implementation Details:**

| Aspect | Implementation |
|--------|---------------|
| **SDK** | Privy JavaScript SDK (`@privy-io/privy-browser`) via CDN |
| **UI** | Custom HTML/CSS modals (not Privy pre-built) |
| **Session** | JWT in httpOnly cookie (7 days or 24 hours) |
| **Wallets** | Auto-created on first login (Solana + Arbitrum) |
| **Address Display** | Full 42-character address + QR code |
| **Resend Cooldown** | 60 seconds |
| **Logo** | Asgard.png in modal header |
| **Badge** | "Protected by Privy" at bottom |

**Backend Endpoints:**
```python
# Authentication
POST /api/v1/auth/privy/initiate     # Start email auth, returns session
POST /api/v1/auth/privy/verify       # Verify OTP code
POST /api/v1/auth/refresh            # Refresh session
POST /api/v1/auth/logout             # Clear session
GET  /api/v1/auth/me                 # Get current user + wallet addresses

# Session Management
class SessionManager:
    SESSION_SHORT_HOURS = 24      # Unchecked "Stay logged in"
    SESSION_LONG_DAYS = 7         # Checked "Stay logged in"
    
    async def create_session(
        self, 
        privy_user_id: str,
        email: str,
        stay_logged_in: bool,
        server_secret: str
    ) -> Session:
        """Create new session after successful Privy OTP verification."""
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        
        # Derive KEK and get/create DEK
        kek = self._derive_kek(privy_user_id, server_secret)
        encrypted_dek = await self._get_or_create_dek(privy_user_id, kek)
        
        # Calculate expiration based on "Stay logged in"
        if stay_logged_in:
            expires_at = now() + timedelta(days=self.SESSION_LONG_DAYS)
        else:
            expires_at = now() + timedelta(hours=self.SESSION_SHORT_HOURS)
        
        # Store session
        await self.db.execute(
            """INSERT INTO sessions 
               (id, privy_user_id, email, created_at, expires_at, csrf_token) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, privy_user_id, email, now(), expires_at, csrf_token)
        )
        
        return Session(...)
```

**Database Schema (Updated):**
```sql
-- Users table (stores wallet addresses, public info)
CREATE TABLE users (
    id TEXT PRIMARY KEY,           -- Privy user ID
    email TEXT UNIQUE,              -- User's email (from Privy)
    solana_address TEXT,           -- Solana wallet address
    evm_address TEXT,              -- EVM/Arbitrum wallet address
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_new_user BOOLEAN DEFAULT TRUE  -- For showing deposit modal
);

-- Sessions table (unchanged)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    privy_user_id TEXT REFERENCES users(id),
    email TEXT,
    created_at TIMESTAMP,
    expires_at TIMESTAMP,
    csrf_token TEXT
);
```

**Security Considerations:**
1. **httpOnly Cookies** - Session token not accessible via JavaScript
2. **CSRF Protection** - CSRF token required for state-changing requests
3. **Rate Limiting** - 5 OTP attempts per 15 minutes
4. **Input Validation** - Email format validation, OTP 6-digit numeric
5. **CSP Headers** - Content Security Policy for Privy scripts
6. **User Isolation** - Users can only see their own wallet addresses via `/auth/me`

**Previous Authentication (v3.3 and earlier):**
- Used Privy OAuth with Google/Twitter options
- Required redirect to Privy's hosted page
- See [PRIVY_AUTH_SPEC.md](../PRIVY_AUTH_SPEC.md) for detailed comparison

### 3.3 Privy OAuth Providers

Supported authentication methods:
- **Email** - Magic link sent to email
- **Google** - OAuth via Google account
- **Twitter/X** - OAuth via Twitter/X account

**Benefits:**
- ✅ No password for user to remember
- ✅ No Privy app configuration needed
- ✅ Wallets automatically recovered via email
- ✅ Same user = same wallets across sessions
- ✅ Enterprise-grade MPC security

### 3.4 Tamper Detection

All encrypted fields include HMAC-SHA256:
```python
def encrypt_field(plaintext: str, dek: bytes) -> bytes:
    """Encrypt with AES-256-GCM + HMAC for tamper detection."""
    nonce = os.urandom(12)
    aesgcm = AESGCM(dek)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    
    # Compute HMAC of ciphertext
    hmac_key = dek[:32]  # First half of DEK
    h = hmac.HMAC(hmac_key, hashes.SHA256())
    h.update(ciphertext)
    field_hmac = h.finalize()
    
    return nonce + ciphertext + field_hmac

def decrypt_field(encrypted: bytes, dek: bytes) -> str:
    """Decrypt and verify HMAC."""
    nonce = encrypted[:12]
    field_hmac = encrypted[-32:]
    ciphertext = encrypted[12:-32]
    
    # Verify HMAC
    hmac_key = dek[:32]
    h = hmac.HMAC(hmac_key, hashes.SHA256())
    h.update(ciphertext)
    h.verify(field_hmac)  # Raises InvalidSignature if tampered
    
    # Decrypt
    aesgcm = AESGCM(dek)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()
```

---

## 4. Setup Wizard Flow

### 4.1 Security-First Approach

| Feature | Implementation | Rationale |
|---------|---------------|-----------|
| **Wallet Security** | Privy embedded wallets (TEE-sharded keys) | No private keys stored locally |
| **Session Management** | Time-bounded (30 min), localhost-only | Limits attack window |
| **Input Validation** | Server-side + client-side validation | Prevents injection attacks |
| **Data Transmission** | Encrypted via HTTPS/TLS | Prevents eavesdropping |
| **Configuration Storage** | SQLite with field-level encryption | Encrypted at rest |
| **Audit Logging** | PII sanitized, actions logged | Accountability without exposure |
| **Auth Key Backup** | Mandatory encrypted backup before completion | Prevents lockout |

### 4.2 Simplified Flow (4 Steps + Dashboard)

> **v3.4 Update:** Streamlined UX. Both exchanges work with wallet-based authentication (no API keys required). Funding and Strategy are dashboard actions, not setup steps.

```
SETUP WIZARD (3 Steps)
======================

Step 1: Authentication
├── OAuth: Email, Google, or Twitter/X login via Privy
├── Derive: KEK from HMAC(privy_user_id, server_secret)
├── Generate: DEK, encrypt with KEK
└── Status: ✅ Authenticated

Step 2: Wallet Creation
├── Create: EVM wallet (Hyperliquid) via Privy
├── Create: Solana wallet (Asgard) via Privy
├── Display: Wallet addresses
└── Status: ✅ Wallets ready

Step 3: Exchange Configuration (Optional API Keys)
├── Asgard: Public access (1 req/sec) or add API key for unlimited
├── Hyperliquid: Wallet-based auth (EIP-712 signatures)
├── Test: Connections to both exchanges
├── Encrypt: API credentials with DEK (if provided)
└── Status: ✅ Exchanges connected

→ Dashboard Access
├── User lands on main dashboard
├── View: Trade status, positions, PnL
└── Status: ✅ Ready for funding & launch

DASHBOARD (Main Interface) - 2 Tab Layout
========================================

TAB 1: HOME (Position Management)
=================================
┌─────────────────────────────────────────────────────────────┐
│  [🏠 Home] [⚙️ Settings]                                     │  ← Tab navigation
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  DESIRED LEVERAGE                                           │
│  [========|==========] 3.0x                                 │  ← Slider 2x-4x
│                                                             │
│  ┌──────────────────────────┬──────────────────────────┐   │
│  │  🏛️ ASGARD RATES         │  ⚡ HYPERLIQUID          │   │
│  │  Net APY @ 3.0x          │  Funding Rate @ 3.0x     │   │
│  │                          │                          │   │
│  │  SOL                     │  SOL-PERP: -12.5%        │   │
│  │  ├─ Kamino: 12.5%        │  Predicted: -14.8%       │   │
│  │  └─ Drift: 11.8%         │                          │   │
│  │                          │                          │   │
│  │  jitoSOL (~8% staking)   │                          │   │
│  │  ├─ Kamino: 18.2%        │                          │   │
│  │  └─ Drift: 17.5%         │                          │   │
│  │                          │                          │   │
│  │  jupSOL (~7.5% staking)  │                          │   │
│  │  ├─ Kamino: 16.5%        │                          │   │
│  │  └─ Drift: 15.8%         │                          │   │
│  │                          │                          │   │
│  │  INF (~7% staking)       │                          │   │
│  │  ├─ Kamino: 15.2%        │                          │   │
│  │  └─ Drift: 14.5%         │                          │   │
│  │                          │                          │   │
│  └──────────────────────────┴──────────────────────────┘   │
│                                                             │
│  ACTIVE POSITIONS                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Asset    Size      Leverage    PnL        Action     │  │
│  │ jitoSOL  $10,000  3.0x       +$234.50   [Close]     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  [      🔴 FUND WALLETS      ]  [    🟢 OPEN POSITION    ] │
└─────────────────────────────────────────────────────────────┘

TAB 2: SETTINGS (Strategy Configuration)
========================================
┌─────────────────────────────────────────────────────────────┐
│  PRESETS                                                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐  [💾 Save] [↺ Reset] │
│  │Preset 1 │ │Preset 2 │ │Preset 3 │                      │
│  │3x/$50k  │ │Not Set  │ │Not Set  │                      │
│  └─────────┘ └─────────┘ └─────────┘                      │
├─────────────────────────────────────────────────────────────┤
│  POSITION SETTINGS                                          │
│  • Default Leverage: [3.0]                                  │
│  • Max Position Size: [$50000]                              │
│  • Min Position Size: [$1000]                               │
│  • Max Positions/Asset: [1]                                 │
│                                                             │
│  ENTRY CRITERIA                                             │
│  • Min Opportunity APY: [1.0%]                              │
│  • Max Funding Volatility: [50%]                            │
│                                                             │
│  RISK MANAGEMENT                                            │
│  • Price Deviation: [0.5%]                                  │
│  • Delta Drift: [0.5%]                                      │
│  • [✓] Enable Auto-Exit                                     │
│  • [✓] Enable Circuit Breakers                              │
│                                                             │
│                              [  Save Settings  ]            │
└─────────────────────────────────────────────────────────────┘

FUNDING (Click 🔴 FUND WALLETS button)
======================================
├── Display: Wallet addresses with copy buttons
├── Show: Required minimums (USDC on Arbitrum, SOL + USDC on Solana)
├── Real-time: Balance checking
└── User: Deposits funds, clicks "Done"
```
```

### 4.3 Long-Running Operations

Wallet creation and connection tests may take seconds. Use async job pattern:

```python
class SetupJobManager:
    """Manages async setup operations with progress tracking."""
    
    async def create_job(self, job_type: str, params: dict) -> str:
        """Create job, return job ID for polling."""
        job_id = str(uuid.uuid4())
        await self.db.execute(
            "INSERT INTO setup_jobs (id, type, status, params) VALUES (?, ?, ?, ?)",
            (job_id, job_type, "pending", json.dumps(params))
        )
        # Start background task
        asyncio.create_task(self._run_job(job_id, job_type, params))
        return job_id
    
    async def get_status(self, job_id: str) -> JobStatus:
        """Get current job status for polling."""
        row = await self.db.fetchone(
            "SELECT status, progress, result, error FROM setup_jobs WHERE id = ?",
            (job_id,)
        )
        return JobStatus(**row)
    
    async def _run_job(self, job_id: str, job_type: str, params: dict):
        """Execute job and update status."""
        try:
            await self._update_status(job_id, "running", progress=0)
            
            if job_type == "create_wallets":
                result = await self._create_wallets(params)
            elif job_type == "test_exchange":
                result = await self._test_exchange(params)
            
            await self._update_status(job_id, "completed", progress=100, result=result)
        except Exception as e:
            await self._update_status(job_id, "failed", error=str(e))
```

**HTMX Integration:**
```html
<button hx-post="/setup/wallets" hx-trigger="click">
  Create Wallets
</button>

<!-- Returns 202 Accepted with job ID -->
<!-- HTMX polls for status -->
<div hx-get="/setup/status/{job_id}" 
     hx-trigger="every 500ms"
     hx-target="#progress">
  <progress id="progress" value="0" max="100"></progress>
</div>
```

### 4.4 Validation & Testing

```python
class SetupValidator:
    """Validates configuration at each wizard step."""
    
    async def validate_privy_credentials(
        self, 
        app_id: str, 
        app_secret: str
    ) -> ValidationResult:
        """Test Privy API connectivity."""
        try:
            client = PrivyClient(app_id, app_secret)
            await client.health_check()
            return ValidationResult(valid=True)
        except PrivyAuthError:
            return ValidationResult(
                valid=False, 
                error="Invalid credentials"
            )
    
    async def validate_wallet_funding(
        self, 
        evm_address: str, 
        solana_address: str,
        min_evm_usdc: Decimal = Decimal("100"),
        min_solana_sol: Decimal = Decimal("0.1"),
        min_solana_usdc: Decimal = Decimal("100")
    ) -> FundingStatus:
        """Check wallet balances across chains."""
        evm_balance = await self.arbitrum_client.get_usdc_balance(evm_address)
        solana_sol = await self.solana_client.get_sol_balance(solana_address)
        solana_usdc = await self.solana_client.get_usdc_balance(solana_address)
        
        return FundingStatus(
            evm_funded=evm_balance >= min_evm_usdc,
            solana_sol_funded=solana_sol >= min_solana_sol,
            solana_usdc_funded=solana_usdc >= min_solana_usdc,
            balances={
                "evm_usdc": evm_balance,
                "solana_sol": solana_sol,
                "solana_usdc": solana_usdc
            }
        )
```

### 4.5 Input Sanitization

```python
class SecretSanitizer:
    """Sanitizes sensitive data for logging."""
    
    SENSITIVE_PATTERNS = [
        (r'0x[a-fA-F0-9]{64}', '[PRIVATE_KEY]'),
        (r'[a-zA-Z0-9]{88}', '[SOLANA_KEY]'),
        (r'[a-zA-Z0-9]{32,}', '[API_KEY]'),
        (r'pass(?:word|wd)?["\']?\s*[:=]\s*["\']?[^"\'\s]+', '[PASSWORD]'),
        (r'secret["\']?\s*[:=]\s*["\']?[^"\'\s]+', '[SECRET]'),
    ]
    
    @classmethod
    def sanitize(cls, text: str) -> str:
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text
```

---

## 5. Backup & Recovery

### 5.1 Backup Requirements

**What must be backed up:**
1. **SQLite database** (state.db) - contains all encrypted configuration
2. **Privy authorization key** - server signing key (encrypted backup)

**What does NOT need backup:**
- Wallet private keys (managed by Privy, recoverable via their systems)
- Session data (ephemeral)

### 5.2 Backup API

```python
class BackupManager:
    """Manages encrypted database backups."""
    
    async def create_backup(self, include_logs: bool = False) -> bytes:
        """Create encrypted backup of database."""
        # Create temp copy of SQLite DB
        backup_path = f"/tmp/backup_{uuid.uuid4()}.db"
        await self.db.execute(f"VACUUM INTO '{backup_path}'")
        
        # Compress
        with open(backup_path, 'rb') as f:
            db_data = f.read()
        compressed = gzip.compress(db_data)
        
        # Encrypt with DEK
        encrypted = encrypt_field(compressed, self.dek)
        
        # Add header
        header = {
            "version": "3.1",
            "created_at": datetime.utcnow().isoformat(),
            "includes_logs": include_logs
        }
        
        return json.dumps(header).encode() + b"\n" + encrypted
    
    async def restore_backup(self, backup_data: bytes, kek: bytes) -> bool:
        """Restore database from encrypted backup."""
        # Parse header
        header_line, encrypted = backup_data.split(b"\n", 1)
        header = json.loads(header_line)
        
        # Decrypt
        dek = await self._decrypt_dek_from_backup(encrypted, kek)
        compressed = decrypt_field(encrypted, dek)
        db_data = gzip.decompress(compressed)
        
        # Validate SQLite
        if not self._validate_sqlite(db_data):
            raise ValueError("Invalid backup file")
        
        # Restore with atomic swap
        temp_path = "/data/state.db.tmp"
        with open(temp_path, 'wb') as f:
            f.write(db_data)
        os.rename(temp_path, "/data/state.db")
        
        return True
```

### 5.3 Automated Backups

```python
class AutomatedBackup:
    """Runs scheduled backups."""
    
    BACKUP_INTERVAL_HOURS = 24
    MAX_BACKUPS = 7  # Keep one week
    
    async def run(self):
        while True:
            await asyncio.sleep(self.BACKUP_INTERVAL_HOURS * 3600)
            
            backup = await self.backup_manager.create_backup()
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = f"/data/backups/state_{timestamp}.db.enc"
            
            with open(path, 'wb') as f:
                f.write(backup)
            
            # Clean old backups
            await self._rotate_backups()
```

### 5.4 Privy Auth Key Backup

The authorization key is critical - losing it means losing wallet access through the API.

**Backup Process:**
1. Generate auth key during setup
2. Encrypt with KEK
3. Offer download as `.enc` file + BIP39 mnemonic encoding
4. Force user to confirm download before completing setup

**Recovery Process:**
1. User provides encrypted backup file + password
2. System derives KEK, decrypts auth key
3. Validates key against Privy API
4. Re-encrypts with new KEK for storage

---

## 6. Emergency Stop Mechanisms

### 6.1 Kill Switch Options

| Method | Speed | Use Case | Effect |
|--------|-------|----------|--------|
| Docker stop | Immediate | Complete container termination | Bot stops, positions stay open |
| API endpoint | <1s | Remote/scripted stop | Bot pauses, positions stay open |
| File-based | 5s | Dashboard inaccessible | Bot pauses, positions stay open |
| Manual close | 30-120s/position | Exit specific positions | Actually closes positions |

**Important:** Kill switches PAUSE the bot (stop new positions) but do NOT close existing positions. Positions must be closed manually or via the close position API.

### 6.2 Implementation

**Docker Stop:**
```bash
docker stop -t 30 delta-neutral-bot
# SIGTERM -> graceful shutdown
# SIGKILL after 30s if not exited
```

**API Endpoint - Pause:**
```python
@app.post("/api/v1/control/pause")
async def pause_bot(
    request: PauseRequest,
    current_user: User = Depends(get_current_user)
):
    """Pause bot operations (stop new positions)."""
    await bot.pause(reason=request.reason)
    return {"status": "paused", "message": "Bot paused. Existing positions remain open."}
```

**API Endpoint - Close Position (works even when bot paused):**
```python
@app.post("/api/v1/positions/{position_id}/close")
async def close_position(
    position_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Close a specific position. Works even if bot is paused/stopped.
    This is the ONLY way to actually close positions.
    """
    result = await position_manager.close_position(position_id)
    return {"success": result.success, "position_id": position_id}
```

**File-Based Kill Switch:**
```python
class KillSwitchMonitor:
    """
    Monitors for emergency stop file.
    
    When triggered: PAUSES bot (stops new positions)
    Does NOT: Close existing positions
    
    Use case: Stop the bleeding during bad market data / API issues
    """
    
    KILL_SWITCH_PATH = "/data/emergency.stop"
    CHECK_INTERVAL = 5
    
    async def monitor(self):
        while self.running:
            if os.path.exists(self.KILL_SWITCH_PATH):
                logger.critical("Kill switch detected - EMERGENCY PAUSE!")
                await bot.pause(reason="Kill switch file detected")
                os.remove(self.KILL_SWITCH_PATH)  # Clean up
                
                # Log that positions are still open
                open_positions = await bot.get_positions()
                logger.warning(f"Bot paused. {len(open_positions)} positions STILL OPEN.")
                logger.info("Use dashboard or API to close positions manually.")
                break
            await asyncio.sleep(self.CHECK_INTERVAL)
```

### 6.3 Manual Position Close (Bot-Independent)

**Critical Feature:** Users can close positions even if the bot is stopped/paused.

```python
class PositionCloseService:
    """
    Standalone service for closing positions.
    Does not depend on bot running state.
    """
    
    async def close_position(self, position_id: str) -> CloseResult:
        """
        Close a position directly via venue APIs.
        Works even if bot is stopped.
        """
        position = await self.db.get_position(position_id)
        
        # Close Hyperliquid short
        hl_result = await self.hyperliquid.close_short(position)
        
        # Close Asgard long
        asgard_result = await self.asgard.close_position(position)
        
        return CloseResult(
            hyperliquid=hl_result,
            asgard=asgard_result
        )
```

**Dashboard Close Button:**
- Available even when bot shows "PAUSED" or "STOPPED"
- User confirms via modal
- Async job executes closure directly
- Status polling shows progress

---

## 7. Core Components

### 7.1 Opportunity Detection

```python
class OpportunityDetector:
    """
    Scans for delta-neutral opportunities.
    Only enters when current AND predicted funding favor shorts.
    """
    
    ALLOWED_ASSETS = ["SOL", "jitoSOL", "jupSOL", "INF"]
    FUNDING_LOOKBACK_HOURS = 168  # 1 week
    
    async def scan(self) -> List[ArbitrageOpportunity]:
        """
        1. Fetch Asgard rates for all SOL/LST pairs
        2. Fetch Hyperliquid SOL-PERP funding
        3. Check both current AND predicted funding < 0
        4. Calculate total APY = |funding| + net_carry
        5. Filter: total APY > min_threshold
        """
```

### 7.2 Execution Flow

```
1. PRE-FLIGHT CHECKS
   ├── Price consensus check (< 0.5% deviation)
   ├── Wallet balance validation
   ├── Fee market check (Solana CUP < threshold)
   ├── Protocol capacity check
   └── Simulate both legs

2. EXECUTE ASGARD LONG
   ├── Build: POST /create-position
   ├── Sign: Via Privy Solana API
   ├── Submit: POST /submit-create-position-tx
   └── Confirm: Poll /refresh-positions

3. EXECUTE HYPERLIQUID SHORT
   ├── Set leverage to match Asgard
   ├── Place market short order
   ├── Sign: Via Privy EVM API (EIP-712)
   └── Confirm: Query clearinghouseState

4. POST-EXECUTION VALIDATION
   ├── Verify both positions confirmed
   ├── Check fill price deviation < 0.5%
   ├── Calculate actual delta
   └── Store position state
```

### 7.3 Risk Management

```yaml
risk_limits:
  # Position
  max_position_size_usd: 500000
  max_positions_per_asset: 1
  default_leverage: 3.0
  max_leverage: 4.0
  
  # Asgard
  min_health_factor: 0.20
  liquidation_proximity: 0.20
  
  # Hyperliquid  
  margin_fraction_threshold: 0.10
  
  # Execution
  max_price_deviation: 0.005
  max_slippage_entry_bps: 50
  max_slippage_exit_bps: 100
  max_delta_drift: 0.005
  
  # Gas protection
  max_solana_priority_fee_sol: 0.01
  max_solana_emergency_fee_sol: 0.02
  
  # LST Monitoring
  lst_warning_premium: 0.03
  lst_critical_premium: 0.05
  lst_velocity_warning: 0.02    # 2% per hour
  lst_velocity_critical: 0.05   # 5% per hour
```

---

## 8. Dashboard & API

### 8.1 Dashboard Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│  Delta Neutral Bot Dashboard                              [⚙] [👤] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  STATUS OVERVIEW                                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │   │
│  │  │  Status  │ │ Positions│ │  PnL 24h │ │  Health  │       │   │
│  │  │ RUNNING  │ │    2     │ │ +$123.45│ │   OK     │       │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐   │
│  │  ACTIVE POSITIONS        │  │  QUICK CONTROLS              │   │
│  │  ┌────────────────────┐  │  │                              │   │
│  │  │ SOL  |  3x  | +$45 │  │  │  [Pause Entry]              │   │
│  │  │ HF: 28%  MF: 15%   │  │  │  [Pause All]                │   │
│  │  └────────────────────┘  │  │  [Emergency Stop]           │   │
│  │  ┌────────────────────┐  │  │                              │   │
│  │  │jitoSOL| 3x | +$78 │  │  │  Last Update: 2s ago        │   │
│  │  │ HF: 25%  MF: 12%   │  │  │                              │   │
│  │  └────────────────────┘  │  └──────────────────────────────┘   │
│  └──────────────────────────┘                                     │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  FUNDING RATES & OPPORTUNITIES                              │   │
│  │  • SOL-PERP: -15.2% (predicted: -14.8%)  ✅ ENTERED         │   │
│  │  • jitoSOL net carry: +8.3%                                 │   │
│  │  • Total expected APY: 23.5%                                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  RECENT ACTIVITY                                            │   │
│  │  • 12:05:23 - Position opened: jitoSOL @ 3x                 │   │
│  │  • 12:00:00 - Funding payment received: $2.34               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Real-Time Updates (SSE)

```python
@app.get("/api/v1/events")
async def event_stream(request: Request):
    """Server-sent events for real-time updates."""
    async def event_generator():
        while True:
            # Check for new events
            event = await event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            
    return EventSourceResponse(event_generator())
```

**HTMX Integration:**
```html
<div hx-sse="connect:/api/v1/events swap:message">
  <div sse-swap="position_update"></div>
  <div sse-swap="funding_update"></div>
</div>
```

### 8.3 API Endpoints (v3.4 - Simplified)

#### Authentication (Privy OAuth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/setup/privy/auth` | Show Privy OAuth login |
| POST | `/setup/privy/callback` | Handle OAuth callback |
| POST | `/logout` | Destroy session |

#### Setup Wizard (4 Steps)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/setup/status` | Current setup progress |
| POST | `/setup/wallets` | Step 2: Create wallets |
| POST | `/setup/exchange` | Step 3: Configure APIs (Asgard + Hyperliquid) |

#### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dashboard` | Main dashboard (trade status, balances) |
| GET | `/dashboard/funding` | Funding page (deposit addresses) |
| GET | `/dashboard/strategy` | Strategy config page |

#### Bot Control
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/control/start` | **Start bot trading** |
| POST | `/api/v1/control/pause` | Pause operations |
| POST | `/api/v1/control/resume` | Resume operations |
| POST | `/api/v1/control/stop` | Stop bot |
| POST | `/api/v1/control/emergency-stop` | Emergency stop |

#### Real-time Data (SSE)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/events/stream` | **SSE stream** for live updates (position opened/closed, PnL, rates) |
| GET | `/api/v1/events/status` | Event system status (subscriber count) |
| GET | `/api/v1/status` | Bot status |
| GET | `/api/v1/positions` | Current positions |
| GET | `/api/v1/positions/jobs/{job_id}` | Job status for open/close operations |
| GET | `/api/v1/balances` | Wallet balances |
| GET | `/api/v1/rates` | Current funding rates |

**SSE Event Types:**
```
position_opened  → New position created
position_closed  → Position closed with PnL
position_update  → PnL or health factor changed
rate_update      → Funding rates updated
bot_status       → Bot paused/resumed/connected
balance_update   → Wallet balance changed
ping             → Keepalive (every 30s)
error            → Error notification
```

---

## 9. Security Model

### 9.1 Container Security

- **Single tenant**: Each user has their own isolated container
- **No SSH**: No remote shell access to running containers
- **Non-root user**: Container runs as UID 1000
- **Read-only filesystem**: Except for `/data` volume
- **No secrets in env**: All sensitive data encrypted in SQLite
- **Network isolation**: Only binds to localhost (127.0.0.1)
- **Resource limits**: CPU/memory caps to prevent DoS

**Docker Compose:**
```yaml
services:
  bot:
    image: delta-neutral-bot:latest
    user: "1000:1000"
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
    volumes:
      - ./data:/data:rw
    ports:
      - "127.0.0.1:8080:8080"
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
```

### 9.2 Remote Access (SSH Tunnel)

Dashboard binds to localhost only. For remote access:

```bash
# On local machine, tunnel to remote server
ssh -L 8080:localhost:8080 user@server

# Then access http://localhost:8080 locally
```

This ensures:
- TLS termination via SSH
- No exposed ports on server
- User controls access

### 9.3 Transaction Validation

```python
class TransactionValidator:
    """Validates all transactions before signing."""
    
    ALLOWED_SOLANA_PROGRAMS = [
        "MFv2hWf31T...",  # Marginfi
        "KLend2g3cP...",  # Kamino
        "So1end1111...",  # Solend
        "dRiftyHA39...",  # Drift
        "Asgard...",      # Asgard
    ]
    
    ALLOWED_HYPERLIQUID_ACTIONS = ["order", "updateLeverage", "cancel"]
    
    async def validate(self, tx, chain: str) -> bool:
        if chain == "solana":
            return self._validate_solana_tx(tx)
        elif chain == "hyperliquid":
            return self._validate_hyperliquid_tx(tx)
```

---

## 10. Monitoring & Alerting

### 10.1 Health Checks

| Check | Interval | Action on Failure |
|-------|----------|-------------------|
| Privy API | 60s | Alert, pause entries |
| Privy rate limit | 300s | Alert at 80% threshold |
| Asgard API | 30s | Alert, check alternatives |
| Hyperliquid API | 30s | Alert, pause entries |
| Solana RPC | 30s | Alert, switch RPC |
| Position health | 30s | Auto-close if critical |
| Funding rates | 60s | Alert only |

### 10.2 Alert Channels

- **In-app**: Real-time notifications via SSE
- **Webhook**: User-configurable HTTP endpoint with retry
- **Telegram**: Optional bot integration
- **Logs**: Structured JSON to stdout

**Webhook Retry Policy:**
- 3 immediate retries (1s, 2s, 4s)
- Then hourly for 24 hours
- Persist failed alerts to SQLite

### 10.3 Log Management

```yaml
logging:
  retention_days: 30
  sanitized_retention_days: 365
  levels:
    - DEBUG: Development only
    - INFO: Normal operations
    - WARNING: Deviations
    - ERROR: Failures
    - CRITICAL: Emergency
  sanitization:
    - Remove private keys
    - Remove API secrets
    - Mask wallet addresses (show first/last 4)
```

---

## 11. Database Schema & Migrations

### 11.1 Schema Version Tracking

```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    checksum TEXT  -- SHA256 of migration script
);

-- Current version
INSERT INTO schema_version (version, checksum) 
VALUES (1, 'abc123...');
```

### 11.2 Migration Process

```python
class SchemaMigrator:
    """Handles database schema migrations."""
    
    MIGRATIONS_DIR = "migrations"
    
    async def migrate(self, target_version: int):
        current = await self._get_current_version()
        
        for version in range(current + 1, target_version + 1):
            migration = self._load_migration(version)
            
            async with self.db.transaction():
                # Run migration
                await migration.up(self.db)
                
                # Record
                await self.db.execute(
                    "INSERT INTO schema_version (version, checksum) VALUES (?, ?)",
                    (version, migration.checksum)
                )
```

### 11.3 Core Tables

```sql
-- Configuration (encrypted fields)
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value_encrypted BLOB,  -- nonce || ciphertext || hmac
    is_encrypted BOOLEAN DEFAULT 1
);

-- Sessions
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    expires_at TIMESTAMP,
    csrf_token TEXT,
    ip_address TEXT
);

-- Positions
CREATE TABLE positions (
    id TEXT PRIMARY KEY,
    asset TEXT,
    status TEXT,  -- open, closing, closed
    asgard_protocol INTEGER,
    asgard_position_pda TEXT,
    hyperliquid_position_size DECIMAL,
    entry_prices TEXT,  -- JSON
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Audit log (sanitized)
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    action TEXT,
    user TEXT,
    details TEXT  -- Sanitized
);
```

### 11.4 Known Schema Issues (SaaS Migration)

> **⚠️ Critical Bug - Migration 003:**
> 
> File: `migrations/003_position_jobs.sql` line 22
> ```sql
> FOREIGN KEY (user_id) REFERENCES users(user_id)  -- WRONG
> ```
> Should be:
> ```sql
> FOREIGN KEY (user_id) REFERENCES users(id)      -- CORRECT
> ```
> 
> **Impact:** Database constraint errors when creating position jobs for any user.
> **Fix Status:** Needs migration fix - either patch 003 or create 005 fix migration.
> **Priority:** HIGH - blocks SaaS deployment.

---

## 12. Future SaaS Enhancements

> **Current Architecture:** Multi-user auth + single-tenant execution (hybrid).
> This section documents what is needed for true multi-tenant SaaS.

### 12.1 Architecture Gap Analysis

| Component | Current | True SaaS Required | Effort |
|-----------|---------|-------------------|--------|
| **Authentication** | ✅ Privy multi-user | ✅ Already done | - |
| **Position Storage** | ❌ Global `Dict[str, Position]` | ✅ `Dict[user_id, Dict[str, Position]]` | 3-5 days |
| **Bot Execution** | ❌ Single bot loop | ✅ Per-user bot instances or multi-tenant scheduler | 1-2 weeks |
| **Settings Storage** | ❌ Global config | ✅ Per-user leverage/risk settings | 3-5 days |
| **Database** | ⚠️ SQLite (single user) | ✅ PostgreSQL with user-scoped tables | 1 week |
| **Billing/Usage** | ❌ Not implemented | ✅ Plan limits, usage tracking | 2-3 weeks |
| **Isolated Execution** | ❌ Shared process | ✅ Container-per-user or sandboxed | 2-3 weeks |

### 12.2 Option A: Single-Tenant Per User (Current Path)

**Model:** One Docker container per user.

```
User A → Container A (bot + dashboard) → User A's positions
User B → Container B (bot + dashboard) → User B's positions
User C → Container C (bot + dashboard) → User C's positions
```

**Pros:**
- Perfect isolation (security, resource limits)
- Simple to understand and debug
- Can customize per user
- Easy to migrate to self-hosted

**Cons:**
- Higher infrastructure costs
- More complex orchestration needed
- Slower user onboarding (container spin-up time)
- Harder to manage at scale

**Implementation:**
- Keep current architecture
- Add orchestrator to spin up/down containers per user
- Each container has own SQLite DB
- Shared Privy app (already implemented)

### 12.3 Option B: True Multi-Tenant (Future)

**Model:** Single deployment serves all users with data isolation.

```
                    ┌─────────────────────────────────┐
                    │         Load Balancer           │
                    └─────────────┬───────────────────┘
                                  │
                    ┌─────────────▼───────────────────┐
                    │     FastAPI Dashboard           │
                    │  (auth, settings, API)          │
                    └─────────────┬───────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
   ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
   │  User Bot   │        │  User Bot   │        │  User Bot   │
   │  Instance A │        │  Instance B │        │  Instance C │
   └──────┬──────┘        └──────┬──────┘        └──────┬──────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  │
                    ┌─────────────▼───────────────────┐
                    │    PostgreSQL + Row-Level       │
                    │    Security (per-user data)     │
                    └─────────────────────────────────┘
```

**Required Changes:**

#### 1. Database Schema Fixes

```sql
-- Fix migration 003 (urgent)
ALTER TABLE position_jobs DROP CONSTRAINT fk_position_jobs_user;
ALTER TABLE position_jobs ADD CONSTRAINT fk_position_jobs_user 
    FOREIGN KEY (user_id) REFERENCES users(id);

-- Add user_id to all relevant tables
ALTER TABLE positions ADD COLUMN user_id TEXT REFERENCES users(id);
ALTER TABLE config ADD COLUMN user_id TEXT REFERENCES users(id);

-- Add row-level security for PostgreSQL
CREATE POLICY user_positions_isolation ON positions
    USING (user_id = current_setting('app.current_user_id'));
```

#### 2. Position Manager Refactor

```python
class MultiTenantPositionManager:
    """Per-user position storage with isolation."""
    
    def __init__(self):
        # user_id -> {position_id -> CombinedPosition}
        self._positions: Dict[str, Dict[str, CombinedPosition]] = {}
    
    def get_positions(self, user_id: str) -> Dict[str, CombinedPosition]:
        """Get positions only for the specified user."""
        return self._positions.get(user_id, {})
    
    def add_position(self, user_id: str, position: CombinedPosition):
        """Add position scoped to user."""
        if user_id not in self._positions:
            self._positions[user_id] = {}
        self._positions[user_id][position.position_id] = position
```

#### 3. Bot Execution Model

```python
class PerUserBotScheduler:
    """Manages bot instances per user."""
    
    def __init__(self):
        self._user_bots: Dict[str, DeltaNeutralBot] = {}
        self._executor = ThreadPoolExecutor(max_workers=100)
    
    async def start_user_bot(self, user_id: str, config: UserConfig):
        """Start a dedicated bot for a user."""
        bot = DeltaNeutralBot(
            user_id=user_id,
            position_manager=self._get_user_position_manager(user_id),
            config=config
        )
        self._user_bots[user_id] = bot
        await bot.start()
    
    async def stop_user_bot(self, user_id: str):
        """Stop a user's bot."""
        if user_id in self._user_bots:
            await self._user_bots[user_id].stop()
            del self._user_bots[user_id]
```

#### 4. Settings Isolation

```python
class PerUserSettings:
    """User-scoped configuration with defaults."""
    
    DEFAULTS = {
        "max_leverage": 4.0,
        "min_leverage": 2.0,
        "default_leverage": 3.0,
        "max_position_size_usd": 10000,
        "max_positions_per_asset": 2
    }
    
    async def get_setting(self, user_id: str, key: str) -> Any:
        """Get setting for user, fallback to default."""
        user_config = await self.db.get_user_config(user_id)
        return user_config.get(key, self.DEFAULTS[key])
```

### 12.4 Migration Path

**Phase 1 (Current):** Fix critical bugs, deploy as single-tenant-per-user
- Fix FK bug in migration 003
- Complete test coverage
- Docker hardening

**Phase 2:** Shared infrastructure with container-per-user
- Add orchestrator service
- Implement container lifecycle management
- Add usage tracking for billing

**Phase 3:** True multi-tenant (optional, based on scale needs)
- Migrate to PostgreSQL
- Implement per-user bot scheduler
- Add row-level security

---

## 13. Testing Strategy

### 12.1 Test Infrastructure

| Component | Approach | Tools |
|-----------|----------|-------|
| Unit tests | Mock external APIs | pytest, AsyncMock |
| Integration tests | Testnet where available | pytest-asyncio |
| UI tests | Browser automation | Playwright |
| Load tests | Simulate high frequency | locust |
| Security tests | SAST, dependency scan | bandit, safety |

### 12.2 Mock Servers

```python
# tests/mocks/privy_mock.py
class MockPrivyServer:
    """Flask-based mock of Privy API for testing."""
    
    def create_wallet(self):
        return {
            "address": "0x" + secrets.token_hex(20),
            "id": str(uuid.uuid4())
        }
    
    def sign_transaction(self, wallet_id, tx):
        return {"signature": "0x" + secrets.token_hex(64)}
```

### 12.3 Demo Mode

Setup wizard includes "Demo Mode" toggle:
- Uses mock services
- Fake balances
- Simulated trades
- No real transactions

---

## 13. Roadmap

### Phase 1: Foundation (Current)
- ✅ Privy wallet integration
- ✅ Core delta-neutral engine
- ✅ Risk management & circuit breakers
- ✅ Authentication & encryption
- 🔄 Web-based setup wizard
- 🔄 Dashboard UI

### Phase 2: Enhanced Control
- Paper trading mode
- Advanced exit logic (patience mode)
- Funding rate simulation testing
- Improved close timeout handling

### Phase 3: Advanced Features
- Multi-venue support
- Enhanced LST management
- Dead man's switch / watchdog
- API key rotation

### Phase 4: Scale
- Multi-strategy support
- Institutional features
- Machine learning enhancements

---

## 14. Technical Reference

### 14.1 Project Structure

```
BasisStrategy/
├── src/
│   ├── core/              # Bot engine
│   │   ├── bot.py
│   │   ├── opportunity_detector.py
│   │   ├── position_manager.py
│   │   └── risk_engine.py
│   ├── venues/            # Exchange integrations
│   │   ├── asgard/
│   │   └── hyperliquid/
│   ├── privy/             # Wallet infrastructure
│   │   └── client.py
│   ├── dashboard/         # Web interface
│   │   ├── main.py        # FastAPI app
│   │   ├── auth.py        # Authentication
│   │   ├── setup.py       # Setup wizard
│   │   ├── backup.py      # Backup/restore
│   │   ├── api/           # API routes
│   │   └── templates/     # Jinja2 templates
│   ├── config/            # Configuration
│   │   └── settings.py
│   └── security/          # Encryption, validation
│       ├── encryption.py
│       └── validation.py
├── migrations/            # Database migrations
├── docker/
└── tests/
```

### 14.2 Configuration Reference

| Variable | Source | Encrypted | Notes |
|----------|--------|-----------|-------|
| `PRIVY_APP_ID` | **Environment** | N/A | Shared Privy app (configured by operator) |
| `PRIVY_APP_SECRET` | **Environment** | N/A | Shared app secret (v3.3: moved to env) |
| `PRIVY_AUTH_KEY` | SQLite | ✅ | Server signing key (per-user) |
| `WALLET_ADDRESS_EVM` | SQLite | ❌ | Public address |
| `WALLET_ADDRESS_SOLANA` | SQLite | ❌ | Public address |
| `ASGARD_API_KEY` | SQLite | ✅ | Exchange API key |
| `PRIVY_USER_ID` | SQLite | ❌ | Privy user identifier (not secret) |
| `DEK` | SQLite | ✅ | Encrypted by KEK per user |
| `DASHBOARD_SESSION_SECRET` | Environment | N/A | Server secret for KEK derivation |

**v3.3 Updates:**
- `PRIVY_APP_ID`/`PRIVY_APP_SECRET` moved to environment variables (shared app)
- Removed `ADMIN_PASSWORD_HASH` (no passwords)
- Removed backup key storage (Privy handles recovery)

### 14.3 API References

- **Asgard Finance**: https://github.com/asgardfi/api-docs
- **Hyperliquid**: https://hyperliquid.gitbook.io/hyperliquid-docs/
- **Privy**: https://docs.privy.io/

---

*Document Version: 3.5 (Custom Privy Auth Flow)*  
*Last Updated: 2026-02-10*  
*Auth Specification: [PRIVY_AUTH_SPEC.md](../PRIVY_AUTH_SPEC.md)*

---

## Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| v3.5.1 | 2026-02-10 | Added Section 11.4 (Known Schema Issues), Section 12 (Future SaaS Enhancements), clarified hybrid multi-user/single-tenant architecture |
