# Comprehensive Testing Plan

**Goal:** Achieve 100% test coverage for Security, Chain, and Dashboard sections

**Date:** 2026-02-07

---

## 1. Security Module Tests

### Target: `src/security/encryption.py` (461 lines, 0% coverage)

#### Test Categories:

**A. Key Derivation (derive_kek)**
- [ ] Test Argon2id key derivation with valid password/salt
- [ ] Test PBKDF2 fallback when Argon2 unavailable
- [ ] Test deterministic output (same inputs = same key)
- [ ] Test different salts produce different keys

**B. DEK Generation & Management**
- [ ] Test generate_dek() produces 32-byte random key
- [ ] Test encrypt_dek() with valid KEK
- [ ] Test decrypt_dek() with valid KEK
- [ ] Test decrypt_dek() fails with wrong KEK

**C. Field Encryption/Decryption**
- [ ] Test encrypt_field() produces valid EncryptedField
- [ ] Test decrypt_field() recovers original plaintext
- [ ] Test HMAC verification (tamper detection)
- [ ] Test tampered data raises TamperDetectedError
- [ ] Test wrong password raises DecryptionError
- [ ] Test corrupted data raises DecryptionError

**D. EncryptedField Dataclass**
- [ ] Test to_bytes() serialization
- [ ] Test from_bytes() deserialization
- [ ] Test from_bytes() with invalid data raises error

**E. EncryptionManager**
- [ ] Test initialization generates new DEK
- [ ] Test encrypt() produces valid ciphertext
- [ ] Test decrypt() recovers plaintext
- [ ] Test get_dek_public_hash() returns consistent hash
- [ ] Test export_encrypted_dek() / load_encrypted_dek()
- [ ] Test wrong password on load raises error

**F. Exception Handling**
- [ ] Test EncryptionError hierarchy
- [ ] Test error messages are descriptive

---

## 2. Chain Module Tests

### Target: `src/chain/solana.py` (215 lines, 31% coverage)

#### Test Categories:

**A. SolanaClient Initialization**
- [ ] Test init with default RPC URL
- [ ] Test init with custom RPC URL
- [ ] Test wallet_address property

**B. Balance Operations**
- [ ] Test get_balance() with default wallet
- [ ] Test get_balance() with custom pubkey
- [ ] Test get_balance() handles RPC errors
- [ ] Test get_token_balance() for USDC
- [ ] Test get_token_balance() when no account exists
- [ ] Test get_token_balance() with custom owner

**C. Blockhash & Transaction**
- [ ] Test get_latest_blockhash()
- [ ] Test get_latest_blockhash() handles errors
- [ ] Test confirm_transaction() success
- [ ] Test confirm_transaction() timeout
- [ ] Test confirm_transaction() failure

**D. Error Handling**
- [ ] Test retry logic on RPC failures
- [ ] Test proper error propagation

---

### Target: `src/chain/arbitrum.py` (168 lines, 48% coverage)

#### Test Categories:

**A. ArbitrumClient Initialization**
- [ ] Test init with default RPC URL
- [ ] Test init with custom RPC URL
- [ ] Test wallet_address property

**B. Balance Operations**
- [ ] Test get_balance() for ETH
- [ ] Test get_token_balance() for USDC
- [ ] Test get_usdc_balance() convenience method

**C. Gas & Transaction**
- [ ] Test get_gas_price()
- [ ] Test estimate_gas()
- [ ] Test wait_for_transaction_receipt() success
- [ ] Test wait_for_transaction_receipt() timeout

**D. Error Handling**
- [ ] Test retry logic on RPC failures
- [ ] Test proper error propagation

---

## 3. Dashboard Module Tests

### Target: `src/dashboard/auth.py` (471 lines, 0% coverage)

#### Test Categories:

**A. Session Management**
- [ ] Test Session creation
- [ ] Test Session.is_expired property
- [ ] Test Session.is_inactive property
- [ ] Test Session.touch() updates activity
- [ ] Test session timeout constants

**B. PrivyAuth**
- [ ] Test initialization with app_id/secret
- [ ] Test verify_token() with valid token
- [ ] Test verify_token() with invalid token
- [ ] Test verify_token() with expired token

**C. SessionManager**
- [ ] Test create_session() with valid auth
- [ ] Test get_session() with valid session_id
- [ ] Test get_session() with expired session
- [ ] Test get_session() with inactive session
- [ ] Test validate_csrf() success
- [ ] Test validate_csrf() failure
- [ ] Test destroy_session()
- [ ] Test cleanup_expired_sessions()

**D. Auth Dependencies**
- [ ] Test require_auth() with valid session
- [ ] Test require_auth() with no session
- [ ] Test require_auth() with expired session
- [ ] Test require_operator() role check
- [ ] Test require_admin() role check

---

### Target: `src/dashboard/api/positions.py` (111 lines, 0% coverage)

#### Test Categories:

**A. List Positions**
- [ ] Test GET /positions returns list
- [ ] Test requires viewer role
- [ ] Test handles bot unavailable

**B. Get Position Detail**
- [ ] Test GET /positions/{id} returns detail
- [ ] Test 404 for non-existent position
- [ ] Test requires viewer role

**C. Open Position**
- [ ] Test POST /open creates job
- [ ] Test job record created in DB
- [ ] Test requires operator role
- [ ] Test invalid data returns 400

**D. Job Status**
- [ ] Test GET /jobs/{job_id} returns status
- [ ] Test 404 for non-existent job
- [ ] Test lists user's jobs only

---

### Target: `src/dashboard/api/rates.py` (58 lines, 0% coverage)

#### Test Categories:

**A. Get Rates**
- [ ] Test GET /rates with default leverage
- [ ] Test GET /rates with custom leverage
- [ ] Test returns Asgard rates structure
- [ ] Test returns Hyperliquid rates structure
- [ ] Test handles Asgard API failure
- [ ] Test handles Hyperliquid API failure

---

### Target: `src/dashboard/api/settings.py` (68 lines, 0% coverage)

#### Test Categories:

**A. Get Settings**
- [ ] Test GET /settings returns defaults
- [ ] Test GET /settings returns saved values

**B. Save Settings**
- [ ] Test POST /settings saves to DB
- [ ] Test requires operator role
- [ ] Test invalid data validation

**C. Reset Settings**
- [ ] Test POST /settings/reset restores defaults
- [ ] Test requires operator role

---

## Test Implementation Strategy

### Phase 1: Security Tests (Highest Priority)
- Encryption is critical for security
- Start with core encryption/decryption
- Then key management
- Finally exception handling

### Phase 2: Chain Tests
- Mock RPC responses
- Test retry logic
- Test error handling

### Phase 3: Dashboard Tests
- Mock database
- Mock external APIs (Privy)
- Test auth flow
- Test API endpoints

### Running Tests

```bash
# Security only
pytest tests/unit/security/test_encryption.py -v --cov=src.security.encryption

# Chain only  
pytest tests/unit/chain/ -v --cov=src.chain

# Dashboard only
pytest tests/unit/dashboard/ -v --cov=src.dashboard

# All new tests
pytest tests/unit/security/test_encryption.py tests/unit/chain/ tests/unit/dashboard/ -v
```

---

## Success Criteria

- [ ] Security: 100% coverage of encryption.py
- [ ] Chain: 90%+ coverage of solana.py and arbitrum.py
- [ ] Dashboard: 90%+ coverage of all api/ files
- [ ] All tests passing
- [ ] No compromises - fix code if tests reveal issues
