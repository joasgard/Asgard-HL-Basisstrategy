# Privy Migration Plan

**Date:** 2024-01-15  
**Status:** Planning  
**Impact:** High (touches core signing infrastructure)

---

## Overview

Migrate from local private key storage to [Privy](https://privy.io) embedded wallet infrastructure. This eliminates the need to store private keys locally while maintaining automated server-side signing.

---

## Current State

### Key Storage (Local)
```
secrets/
├── hyperliquid_private_key.txt    # Ethereum secp256k1 key
├── solana_private_key.txt         # Solana ed25519 key
└── hyperliquid_api_key.txt        # API credentials
```

### Signing Flow (Current)
```python
# Load key from file
settings = get_settings()
private_key = settings.hyperliquid_private_key  # From secrets/

# Create local signer
signer = HyperliquidSigner(private_key)
signed_tx = signer.sign_order(...)
```

---

## Target State

### Key Storage (Privy-Managed)
```
No local private keys stored!

.env
├── PRIVY_APP_ID=your-app-id
├── PRIVY_APP_SECRET=your-secret
├── PRIVY_AUTH_KEY_PATH=privy_auth.pem
├── WALLET_ADDRESS=0x...          # Public only
└── HYPERLIQUID_API_KEY=...       # API only, no trading key
```

### Signing Flow (Privy)
```python
# Call Privy API to sign
privy = PrivyClient(
    app_id=settings.privy_app_id,
    app_secret=settings.privy_app_secret,
    authorization_private_key_path=settings.privy_auth_key_path
)

signed_tx = await privy.wallet.sign_transaction(
    wallet_address=settings.wallet_address,
    transaction={...}
)
```

---

## Files to Modify

### 1. Configuration (`src/config/settings.py`)

**Remove:**
```python
# DELETE these fields
hyperliquid_private_key: str = Field(...)
solana_private_key: str = Field(...)
```

**Add:**
```python
# NEW fields for Privy
privy_app_id: str = Field(
    default_factory=lambda: get_secret("PRIVY_APP_ID", "privy_app_id.txt", ""),
    alias="PRIVY_APP_ID"
)
privy_app_secret: str = Field(
    default_factory=lambda: get_secret("PRIVY_APP_SECRET", "privy_app_secret.txt", ""),
    alias="PRIVY_APP_SECRET"
)
wallet_address: str = Field(
    default_factory=lambda: get_secret("WALLET_ADDRESS", "wallet_address.txt", ""),
    alias="WALLET_ADDRESS"
)
```

**Update:**
```python
def check_required_secrets(self) -> list[str]:
    missing = []
    
    # REMOVE
    # if not self.hyperliquid_private_key:
    #     missing.append("HYPERLIQUID_PRIVATE_KEY")
    
    # ADD
    if not self.privy_app_id:
        missing.append("PRIVY_APP_ID")
    if not self.privy_app_secret:
        missing.append("PRIVY_APP_SECRET")
    if not self.wallet_address:
        missing.append("WALLET_ADDRESS")
```

---

### 2. Hyperliquid Signer (`src/venues/hyperliquid/signer.py`)

**Current:** Signs locally with private key

**New:** Delegate to Privy

```python
from privy import PrivyClient
from src.config.settings import get_settings

class HyperliquidSigner:
    """Sign Hyperliquid transactions via Privy."""
    
    def __init__(self):
        settings = get_settings()
        
        self.privy = PrivyClient(
            app_id=settings.privy_app_id,
            app_secret=settings.privy_app_secret,
            authorization_private_key_path=settings.privy_auth_key_path
        )
        self.wallet_address = settings.wallet_address
    
    async def sign_order(
        self,
        coin: str,
        is_buy: bool,
        sz: str,
        limit_px: str,
        order_type: Dict[str, Any],
        reduce_only: bool = False,
    ) -> SignedOrder:
        """Sign order via Privy API."""
        
        # Build EIP-712 typed data
        action_data = {
            "actionType": "order",
            "orders": [{
                "coin": coin,
                "isBuy": is_buy,
                "sz": sz,
                "limitPx": limit_px,
                "orderType": self._order_type_to_string(order_type),
                "reduceOnly": reduce_only,
                "nonce": self.get_next_nonce(),
            }]
        }
        
        # Sign via Privy
        signature = await self.privy.wallet.sign_typed_data(
            wallet_address=self.wallet_address,
            domain=self.DOMAIN,
            types=self.ORDER_TYPES,
            value=action_data,
            primary_type="Action"
        )
        
        return SignedOrder(..., signature=signature)
```

---

### 3. Asgard Transactions (`src/venues/asgard/transactions.py`)

**Challenge:** Asgard uses Solana transactions, Privy supports Solana but with different API.

**Option A:** Use Privy's Solana support
```python
from privy import PrivyClient

class AsgardTransactionBuilder:
    def __init__(self):
        settings = get_settings()
        self.privy = PrivyClient(...)
        self.wallet_address = settings.wallet_address  # Solana address
    
    async def sign_transaction(self, unsigned_tx: bytes) -> SignResult:
        # Use Privy to sign Solana transaction
        signed_tx = await self.privy.wallet.sign_solana_transaction(
            wallet_address=self.wallet_address,
            transaction=unsigned_tx
        )
        return SignResult(...)
```

**Option B:** Use separate Privy wallet for Solana
- Create two wallets: one for EVM (Hyperliquid), one for SVM (Solana)
- Both managed by same Privy app

---

### 4. Chain Configuration (`src/chain/arbitrum.py`)

**Current:** May use private key for certain operations

**New:** All signing goes through Privy

```python
class ArbitrumClient:
    def __init__(self):
        self.privy = PrivyClient(...)
    
    async def send_transaction(self, tx_data: dict) -> str:
        # Sign via Privy
        signed_tx = await self.privy.wallet.sign_transaction(
            wallet_address=self.wallet_address,
            transaction=tx_data
        )
        
        # Broadcast
        return await self.web3.eth.send_raw_transaction(
            signed_tx.raw_transaction
        )
```

---

### 5. New Dependencies

**Add to `requirements/bot.txt`:**
```
# Privy SDK
privy>=0.1.0

# Remove (if no longer needed)
# eth-account is still needed for address derivation
# solders still needed for Solana types
```

---

## Test Updates Required

### 1. Unit Tests (`tests/unit/venues/test_hyperliquid_signer.py`)

**Current:**
```python
def test_sign_order():
    signer = HyperliquidSigner(private_key="0x1234...")
    signed = signer.sign_order(...)
    assert signed.signature.startswith("0x")
```

**New:**
```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_sign_order():
    # Mock Privy client
    mock_privy = AsyncMock()
    mock_privy.wallet.sign_typed_data.return_value = "0xabcd..."
    
    with patch('src.venues.hyperliquid.signer.PrivyClient', return_value=mock_privy):
        signer = HyperliquidSigner()
        signed = await signer.sign_order(...)
        
        assert signed.signature == "0xabcd..."
        mock_privy.wallet.sign_typed_data.assert_called_once()
```

### 2. Settings Tests (`tests/unit/config/test_settings.py`)

**Update:** Check for Privy fields instead of private keys
```python
def test_required_secrets():
    settings = Settings()
    missing = settings.check_required_secrets()
    
    # OLD
    # assert "HYPERLIQUID_PRIVATE_KEY" in missing
    
    # NEW
    assert "PRIVY_APP_ID" in missing
    assert "PRIVY_APP_SECRET" in missing
```

### 3. Integration Tests

**Update:** Mock Privy API responses
```python
@pytest.fixture
def mock_privy():
    with patch('privy.PrivyClient') as mock:
        instance = AsyncMock()
        instance.wallet.sign_transaction.return_value = Mock(
            raw_transaction=b'0xsigned...'
        )
        mock.return_value = instance
        yield instance

async def test_full_entry_flow(mock_privy):
    # Test uses mocked Privy
    ...
```

### 4. New Tests to Add

```python
# tests/unit/test_privy_integration.py

@pytest.mark.asyncio
async def test_privy_sign_hyperliquid_order():
    """Test signing Hyperliquid order via Privy."""
    pass

@pytest.mark.asyncio
async def test_privy_sign_solana_transaction():
    """Test signing Solana transaction via Privy."""
    pass

@pytest.mark.asyncio
async def test_privy_error_handling():
    """Test error handling when Privy API fails."""
    pass

def test_no_local_key_storage():
    """Verify no private keys are stored locally."""
    # Check that secrets/ directory doesn't contain *_private_key.txt
    pass
```

---

## Migration Steps

### Phase 1: Setup Privy (Pre-migration)

1. **Create Privy Account**
   ```bash
   # Sign up at https://privy.io
   # Create new app
   # Get App ID and App Secret
   ```

2. **Generate Authorization Key**
   ```bash
   openssl ecparam -name prime256v1 -genkey -noout -out privy_auth.pem
   openssl ec -in privy_auth.pem -pubout -out privy_auth.pub
   ```

3. **Register Public Key in Privy Dashboard**
   - Go to Authorization Keys section
   - Add new key quorum
   - Upload `privy_auth.pub`

4. **Create Wallets**
   ```python
   from privy import PrivyClient
   
   privy = PrivyClient(app_id="...", app_secret="...")
   
   # Create EVM wallet for Hyperliquid
   evm_wallet = privy.wallet.create(chain_type="ethereum")
   print(f"EVM Address: {evm_wallet.address}")
   
   # Create Solana wallet for Asgard
   sol_wallet = privy.wallet.create(chain_type="solana")
   print(f"Solana Address: {sol_wallet.address}")
   ```

5. **Fund Wallets**
   - Send USDC to EVM address (for Hyperliquid)
   - Send SOL + USDC to Solana address (for Asgard)

6. **Update Environment**
   ```bash
   # .env
   PRIVY_APP_ID=your-app-id
   PRIVY_APP_SECRET=your-secret
   WALLET_ADDRESS=0x...  # EVM address
   SOLANA_WALLET_ADDRESS=...  # Solana address
   ```

### Phase 2: Code Changes

1. **Update settings.py** (Remove old, add new fields)
2. **Refactor HyperliquidSigner** (Use Privy API)
3. **Refactor AsgardTransactionBuilder** (Use Privy API)
4. **Add Privy dependency**
5. **Update all tests**

### Phase 3: Testing

1. **Unit tests** (mock Privy)
2. **Integration tests** (testnet)
3. **Staging deployment** (small amounts)
4. **Production migration**

### Phase 4: Cleanup

1. **Remove old secrets**
   ```bash
   rm secrets/hyperliquid_private_key.txt
   rm secrets/solana_private_key.txt
   ```

2. **Update documentation**
3. **Rotate any exposed keys** (if applicable)

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Privy API downtime | High | Retry logic, circuit breaker, fallback to manual signing |
| Latency increase | Medium | Async calls, connection pooling |
| Rate limiting | Medium | Request batching, queue management |
| Vendor lock-in | Medium | Always maintain key export capability |
| Test flakiness | Low | Consistent mocking, no real API calls in tests |

---

## Effort Estimate

| Task | Hours |
|------|-------|
| Settings refactor | 2 |
| HyperliquidSigner refactor | 4 |
| AsgardTransactionBuilder refactor | 4 |
| Chain module updates | 3 |
| Test updates | 6 |
| Integration testing | 4 |
| Documentation | 2 |
| **Total** | **~25 hours** |

---

## Open Questions

1. **Does Privy support Solana as well as EVM?**
   - Yes, but need to verify exact API

2. **How do we handle nonce management?**
   - Privy should handle this internally
   - May need to verify for Hyperliquid (custom EIP-712)

3. **What about Hyperliquid's custom EIP-712 domain?**
   - Need to pass custom domain to Privy's `sign_typed_data`

4. **Backup strategy?**
   - Export keys from Privy and store in cold storage
   - Document recovery process

---

## Acceptance Criteria

- [ ] No private keys stored in `secrets/` directory
- [ ] All signing goes through Privy API
- [ ] Unit tests pass with mocked Privy
- [ ] Integration tests pass on testnet
- [ ] Staging deployment successful
- [ ] Production deployment successful
- [ ] Old private key files removed
- [ ] Documentation updated
