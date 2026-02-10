# Privy Authentication Flow Specification

**Document Purpose:** Define the complete authentication flow using Privy for the Delta Neutral Bot dashboard.

**Target:** Server-rendered HTML dashboard (Jinja2 templates) with vanilla JavaScript.

---

## Original Questions & Answers

### Q1: Implementation Approach - Vanilla JS vs React?

**Answer:** Use Privy's **JavaScript SDK** (`@privy-io/privy-browser`) with vanilla JavaScript.

**Rationale:**
- The dashboard is already built with server-rendered Jinja2 templates
- Adding React would introduce unnecessary complexity and bundle size
- Privy's vanilla JS SDK provides the same authentication flow with full UI customization
- We can match Hyperliquid's modal design exactly with custom HTML/CSS

**Implementation:**
```html
<script src="https://unpkg.com/@privy-io/privy-browser@latest/dist/privy.min.js"></script>
```

---

### Q2: Deposit Modal Format - Text Only or QR Codes?

**Answer:** **Both QR codes AND copy-paste addresses** for best UX.

**Rationale:**
- QR codes are essential for mobile wallet apps
- Copy-paste addresses are needed for desktop users
- Most users will fund from mobile wallets (Phantom, MetaMask mobile)

**Format:**
```
┌─────────────────────────────────────┐
│  Deposit to Start Trading       [x] │
│                                     │
│  [Solana Logo] Solana (Asgard)      │
│  [QR Code]                          │
│  [Address text with copy btn]       │
│                                     │
│  [HL Logo] Hyperliquid (Arbitrum)   │
│  [QR Code]                          │
│  [Address text with copy btn]       │
│                                     │
│         [Go to Dashboard]           │
└─────────────────────────────────────┘
```

---

### Q3: Post-Login State - What Shows in Header?

**Answer:** Replace Connect button with "Deposit" button that will show the deposit modal when clicked
Add a settings cog next to the deposit button for users to access the bot' settings


**Header State Change:**
```
Before Login:                    After Login:
┌──────────────────┐            ┌──────────────────┐
│     Connect      │            │     Deposit      │
└──────────────────┘            └──────────────────┘
                                 Dropdown:
                                 - View Profile
                                 - Copy Address
                                 - Disconnect
```

---

### Q4: Can Users Skip Deposit?

**Answer:** **Yes**, provide "I'll deposit later" button.

**Rationale:**
- Users may want to explore the dashboard first
- They might need to transfer funds from CEX (takes time)
- Some users may already have positions (re-authenticating)
- Reduces friction in onboarding

**Behavior:**
- Skip button closes modal and goes to main dashboard
- Show a persistent banner: "⚠️ Fund your wallets to start trading"
- Banner disappears once both wallets have >$0 balance

---

### Q5: Automatic Wallet Creation?

**Answer:** **Yes**, create both wallets automatically on first login.

**Rationale:**
- Strategy requires both Solana (Asgard) and EVM (Hyperliquid) wallets
- Creating both upfront avoids mid-flow interruptions
- Privy supports multi-chain wallet creation in one call

**Chains to Enable:**
- Solana (for Asgard trading)
- Arbitrum One (for Hyperliquid)

---

## Additional Implementation Questions

### Q6: How to Handle Session Persistence?

**Answer:** Use **JWT tokens stored in httpOnly cookies**.

**Flow:**
1. Privy authentication returns auth token
2. Dashboard backend validates token and creates session
3. Session stored in httpOnly cookie (secure, XSS-protected)
4. Session duration: 7 days (refreshable)

**Backend Changes Needed:**
- New endpoint: `POST /api/v1/auth/privy` - validates Privy token, creates session
- New endpoint: `POST /api/v1/auth/logout` - clears session
- New endpoint: `GET /api/v1/auth/me` - returns user info + wallet addresses
- Middleware to check session on protected routes

---

### Q7: Where to Store Wallet Addresses?

**Question:** Does this need to be encrypted? What is a secure way for users not to be able to see other user's addresses?

**Answer:** **Database** - SQLite `users` table. **No encryption needed** for addresses (they're public), but strict **session-based access control** required.

**Schema:**
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,           -- Privy user ID
    email TEXT UNIQUE,              -- User's email
    solana_address TEXT,           -- Solana wallet
    evm_address TEXT,              -- EVM/Arbitrum wallet
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
```

**Rationale:**
- Avoids repeated Privy API calls for wallet addresses
- Enables dashboard to work offline (show cached addresses)
- Required for deposit modal (addresses needed immediately)

---

### Q8: What If User Already Has Privy Account?

**Answer:** **Seamless login** - check existing wallets, don't recreate.

**Flow:**
1. User enters email
2. Privy returns existing user or creates new one
3. Backend checks if user exists in our database
4. If existing user: fetch stored wallet addresses
5. If new user: call Privy to get/create wallets, store in DB
6. Skip deposit modal if wallets already funded

---

### Q9: How to Detect if Wallets Are Funded?

**Answer:** **Check balances on-chain** on login.

**Implementation:**
- Solana: Use Solana RPC to get SOL and USDC balance
- Arbitrum: Use Arbitrum RPC to get USDC balance
- Cache balances for 5 minutes to avoid RPC spam

**Deposit Modal Logic:**
```python
if user.is_new or sol_balance == 0 or usdc_balance == 0:
    show_deposit_modal()
else:
    go_to_dashboard()
```

---

### Q10: Error Handling for Failed Authentication?

**Answer:** **Inline error messages** in modal, no redirects.

**Error Scenarios:**
1. **Invalid email format** → Show "Please enter a valid email" under input
2. **Wrong OTP code** → Show "Invalid code. Please try again." with shake animation
3. **Expired OTP** → Show "Code expired. Click resend."
4. **Network error** → Show "Connection failed. Please try again."

**Modal Behavior:**
- Stay on same modal, show error inline
- Allow retry without closing modal
- Add "Resend code" link on OTP modal

---

### Q11: Close Button Behavior?

**Answer:** **X button closes modal, returns to dashboard**.

**States:**
- If not logged in: Show dashboard in "read-only" mode (can't trade)
- If in middle of auth flow: Discard progress, close modal
- If deposit modal: Allow closing, show funding banner

---

### Q12: Mobile Responsive Considerations?

**Answer:** **Full-screen modals on mobile**, centered on desktop.

**Desktop:**
- Modal: max-width 420px, centered, backdrop blur
- QR codes: full width of modal

**Mobile:**
- Modal: 100% width/height, slide up animation
- QR codes: larger for easier scanning
- Addresses: larger tap targets for copy buttons

---

## Technical Implementation Plan

### Phase 1: Backend Changes
1. Create `users` table migration
2. Create `/api/v1/auth/privy` endpoint
3. Create `/api/v1/auth/logout` endpoint
4. Create `/api/v1/auth/me` endpoint
5. Add session middleware

### Phase 2: Frontend Changes
1. Add Privy JS SDK to dashboard template
2. Create auth modals (Email, OTP, Deposit)
3. Implement `switchModal()` function
4. Add Connect button to header
5. Handle session state

### Phase 3: Integration
1. Wire up backend endpoints
2. Test full auth flow
3. Add error handling
4. Test responsive design

---

## Modal Flow State Machine

```
┌─────────────┐
│   CONNECT   │ ──click──▶ ┌─────────────────┐
│   BUTTON    │            │  EMAIL MODAL    │
└─────────────┘            │  (Image 3 style)│
                           └─────────────────┘
                                    │
                                    │ submit email
                                    ▼
                           ┌─────────────────┐
                           │  OTP MODAL      │
                           │  (Image 4 style)│
                           └─────────────────┘
                                    │
                                    │ verify code
                                    ▼
                           ┌─────────────────┐
                           │ CHECK IF NEW    │
                           │ USER            │
                           └─────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
              existing user                    new user
                    │                               │
                    ▼                               ▼
            ┌───────────────┐              ┌─────────────────┐
            │ CHECK BALANCE │              │  DEPOSIT MODAL  │
            └───────────────┘              │  (Both chains)  │
                    │                      └─────────────────┘
         ┌──────────┴──────────┐                    │
         │                     │                    │ skip/funded
    funded                not funded                 │
         │                     │                    ▼
         ▼                     ▼            ┌─────────────────┐
   ┌───────────┐         ┌───────────┐      │ CHECK BALANCE   │
   │ DASHBOARD │         │ DEPOSIT   │      └─────────────────┘
   └───────────┘         │ MODAL     │
                         └───────────┘
```

---

## Security Considerations

1. **httpOnly Cookies** - Prevent XSS access to session tokens
2. **CSRF Protection** - Add CSRF tokens to auth endpoints
3. **Rate Limiting** - Limit OTP attempts (5 per 15 min)
4. **Secure Headers** - Content Security Policy for Privy scripts
5. **Input Validation** - Sanitize email, validate OTP format (6 digits)

---

## Open Questions - ANSWERED

### Q1: Wallet Address Security ✅
**Answer:** Wallet addresses don't need encryption (public info). Use session-based access control so users only see their own addresses.

### Q2: Settings Cog Dropdown ✅
**Answer:** Dropdown menu with:
- View Profile
- Settings  
- Disconnect/Logout

### Q3: Address Display Format ✅
**Answer:** Full 42-character address: `0x1234567890abcdef1234567890abcdef12345678`

### Q4: QR Code Generation ✅
**Answer:** Use `qrcode.js` from unpkg CDN for client-side generation.

### Q5: Session Duration ✅
**Answer:** "Stay logged in" checkbox on login. When checked = 7 days, unchecked = 24 hours. Show note: "Stay logged in for 7 days"

### Q6: Logo Path ✅
**Answer:** Use `/Users/jo/Projects/BasisStrategy/docs/Asgard.png` for modal header.

---

## Final Implementation Notes

### Header State After Login
```
┌──────────────────────────────────┐
│  Delta Neutral Bot        Deposit ⚙️│
└──────────────────────────────────┘
                             Dropdown:
                             ├─ View Profile
                             ├─ Settings
                             └─ Disconnect
```

### Email Modal with Logo
```
┌─────────────────────────────┐
│  [X]                        │
│                             │
│     [Asgard.png Logo]       │
│                             │
│   Delta Neutral Bot         │
│   Log in or sign up         │
│                             │
│   ┌─────────────────────┐   │
│   │ ✉️  email@example.com│   │
│   └─────────────────────┘   │
│                             │
│        [Continue]           │
│                             │
│   ☐ Stay logged in          │
│      (for 7 days)           │
│                             │
│   Protected by 🔒 Privy     │
└─────────────────────────────┘
```

---

*Document Version: 1.1*
*Created: 2026-02-06*
*Status: ✅ FINALIZED - Ready for Implementation*
