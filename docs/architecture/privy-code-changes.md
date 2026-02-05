# Privy Migration - Specific Code Changes

**This document provides the exact code changes needed for each file.**

---

## File 1: `src/config/settings.py`

### Lines to Remove (116-119, 126-129, 184-189)

```python
# REMOVE:
solana_private_key: str = Field(
    default_factory=lambda: get_secret("SOLANA_PRIVATE_KEY", "solana_private_key.txt", ""),
    alias="SOLANA_PRIVATE_KEY"
)

hyperliquid_private_key: str = Field(
    default_factory=lambda: get_secret("HYPERLIQUID_PRIVATE_KEY", "hyperliquid_private_key.txt", ""),
    alias="HYPERLIQUID_PRIVATE_KEY"
)
```

### Lines to Add (after line 119)

```python
# Privy Configuration
privy_app_id: str = Field(
    default_factory=lambda: get_secret("PRIVY_APP_ID", "privy_app_id.txt", ""),
    alias="PRIVY_APP_ID"
)
privy_app_secret: str = Field(
    default_factory=lambda: get_secret("PRIVY_APP_SECRET", "privy_app_secret.txt", ""),
    alias="PRIVY_APP_SECRET"
)
privy_auth_key_path: str = Field(
    default="privy_auth.pem",
    alias="PRIVY_AUTH_KEY_PATH"
)
wallet_address: str = Field(
    default_factory=lambda: get_secret("WALLET_ADDRESS", "wallet_address.txt", ""),
    alias="WALLET_ADDRESS"
)
solana_wallet_address: str = Field(
    default_factory=lambda: get_secret("SOLANA_WALLET_ADDRESS", "solana_wallet_address.txt", ""),
    alias="SOLANA_WALLET_ADDRESS"
)
```

### Update `check_required_secrets()` method (lines 171-191)

```python
def check_required_secrets(self) -> list[str]:
    """Check if all required secrets are configured."""
    missing = []
    
    if not self.asgard_api_key:
        missing.append("ASGARD_API_KEY")
    if not self.solana_rpc_url:
        missing.append("SOLANA_RPC_URL")
    if not self.hyperliquid_wallet_address:
        missing.append("HYPERLIQUID_WALLET_ADDRESS")
    
    # NEW: Privy requirements
    if not self.privy_app_id:
        missing.append("PRIVY_APP_ID")
    if not self.privy_app_secret:
        missing.append("PRIVY_APP_SECRET")
    if not self.wallet_address:
        missing.append("WALLET_ADDRESS")
    
    # Check auth key file exists
    auth_key_path = Path(self.privy_auth_key_path)
    if not auth_key_path.exists():
        missing.append(f"PRIVY_AUTH_KEY ({self.privy_auth_key_path} not found)")
    
    return missing
```

---

## File 2: `src/venues/hyperliquid/signer.py`

### Complete Refactor - Replace entire file

```python
"""
Hyperliquid Transaction Signer via Privy.

Delegates all signing operations to Privy's secure infrastructure.
"""
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from privy import PrivyClient

from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OrderSpec:
    """Order specification for signing."""
    coin: str
    is_buy: bool
    sz: str
    limit_px: str
    order_type: Dict[str, Any]
    reduce_only: bool = False


@dataclass
class SignedOrder:
    """Signed order ready for submission."""
    coin: str
    is_buy: bool
    sz: str
    limit_px: str
    order_type: Dict[str, Any]
    reduce_only: bool
    signature: str
    nonce: int


class HyperliquidSigner:
    """
    EIP-712 signer for Hyperliquid transactions via Privy.
    
    All signing operations are delegated to Privy's secure infrastructure.
    No private keys are stored or used locally.
    """
    
    DOMAIN = {
        "name": "Hyperliquid",
        "version": "1",
        "chainId": 1337,
        "verifyingContract": "0x0000000000000000000000000000000000000000",
    }
    
    ORDER_TYPES = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Order": [
            {"name": "coin", "type": "string"},
            {"name": "isBuy", "type": "bool"},
            {"name": "sz", "type": "string"},
            {"name": "limitPx", "type": "string"},
            {"name": "orderType", "type": "string"},
            {"name": "reduceOnly", "type": "bool"},
            {"name": "nonce", "type": "uint64"},
        ],
        "Action": [
            {"name": "actionType", "type": "string"},
            {"name": "orders", "type": "Order[]"},
        ],
    }
    
    def __init__(self):
        """Initialize signer with Privy client."""
        settings = get_settings()
        
        self.privy = PrivyClient(
            app_id=settings.privy_app_id,
            app_secret=settings.privy_app_secret,
            authorization_private_key_path=settings.privy_auth_key_path
        )
        self.wallet_address = settings.wallet_address
        self._nonce = int(time.time() * 1000)
        
        logger.info(f"Hyperliquid signer initialized for address: {self.wallet_address}")
    
    @property
    def address(self) -> str:
        """Get the signer address."""
        return self.wallet_address
    
    def get_next_nonce(self) -> int:
        """Get next nonce for signing."""
        self._nonce += 1
        return self._nonce
    
    async def sign_order(
        self,
        coin: str,
        is_buy: bool,
        sz: str,
        limit_px: str,
        order_type: Dict[str, Any],
        reduce_only: bool = False,
        nonce: Optional[int] = None,
    ) -> SignedOrder:
        """Sign order via Privy API."""
        if nonce is None:
            nonce = self.get_next_nonce()
        
        # Build order data
        order_data = {
            "coin": coin,
            "isBuy": is_buy,
            "sz": sz,
            "limitPx": limit_px,
            "orderType": self._order_type_to_string(order_type),
            "reduceOnly": reduce_only,
            "nonce": nonce,
        }
        
        action_data = {
            "actionType": "order",
            "orders": [order_data],
        }
        
        # Sign via Privy
        signature = await self.privy.wallet.sign_typed_data(
            wallet_address=self.wallet_address,
            domain=self.DOMAIN,
            types=self.ORDER_TYPES,
            value=action_data,
            primary_type="Action"
        )
        
        logger.debug(f"Signed order: {coin} {'buy' if is_buy else 'sell'} {sz} @ {limit_px}")
        
        return SignedOrder(
            coin=coin,
            is_buy=is_buy,
            sz=sz,
            limit_px=limit_px,
            order_type=order_type,
            reduce_only=reduce_only,
            signature=signature,
            nonce=nonce,
        )
    
    def _order_type_to_string(self, order_type: Dict[str, Any]) -> str:
        """Convert order type dict to string."""
        if "limit" in order_type:
            tif = order_type["limit"].get("tif", "Gtc")
            return f"Limit({tif})"
        elif "market" in order_type:
            return "Market"
        return "Unknown"
```

---

## File 3: `src/venues/asgard/transactions.py`

### Key Changes (lines 68-106)

```python
class AsgardTransactionBuilder:
    """Builder for Asgard margin position transactions via Privy."""
    
    def __init__(
        self,
        client: Optional[AsgardClient] = None,
        state_machine: Optional[TransactionStateMachine] = None,
    ):
        self.client = client or AsgardClient()
        self.state_machine = state_machine or TransactionStateMachine()
        
        # NEW: Load wallet address from settings (not keypair)
        settings = get_settings()
        self.wallet_address = settings.solana_wallet_address
        
        # NEW: Initialize Privy for Solana signing
        from privy import PrivyClient
        self.privy = PrivyClient(
            app_id=settings.privy_app_id,
            app_secret=settings.privy_app_secret,
            authorization_private_key_path=settings.privy_auth_key_path
        )
```

### Update `sign_transaction()` method (lines 195-251)

```python
async def sign_transaction(
    self,
    intent_id: str,
    unsigned_tx: bytes,
) -> SignResult:
    """Sign a versioned transaction via Privy."""
    logger.info(f"Signing transaction: intent={intent_id}")
    
    self.state_machine.transition(intent_id, TransactionState.SIGNING)
    
    try:
        # NEW: Sign via Privy instead of local keypair
        signed_tx = await self.privy.wallet.sign_solana_transaction(
            wallet_address=self.wallet_address,
            transaction=unsigned_tx
        )
        
        # Get signature (first signature in transaction)
        signature = str(signed_tx.signatures[0])
        
        result = SignResult(
            intent_id=intent_id,
            signed_tx=bytes(signed_tx),
            signature=signature,
        )
        
        self.state_machine.transition(
            intent_id,
            TransactionState.SIGNED,
            signature=signature
        )
        
        logger.info(f"Signed transaction: intent={intent_id}, signature={signature[:16]}...")
        return result
        
    except Exception as e:
        logger.error(f"Failed to sign transaction: {e}")
        self.state_machine.transition(
            intent_id,
            TransactionState.FAILED,
            error=str(e)
        )
        raise
```

### Update `build_create_position()` (line 150)

```python
# OLD: "owner": str(self.keypair.pubkey())
# NEW:
"owner": self.wallet_address,
```

---

## File 4: New File `src/venues/privy_client.py`

### Create new shared Privy client

```python
"""
Shared Privy client configuration.

Provides a singleton Privy client instance for use across the application.
"""
from functools import lru_cache
from privy import PrivyClient

from src.config.settings import get_settings


@lru_cache()
def get_privy_client() -> PrivyClient:
    """
    Get or create singleton Privy client instance.
    
    Returns:
        Configured PrivyClient instance
    """
    settings = get_settings()
    
    return PrivyClient(
        app_id=settings.privy_app_id,
        app_secret=settings.privy_app_secret,
        authorization_private_key_path=settings.privy_auth_key_path
    )
```

---

## File 5: `tests/unit/venues/test_hyperliquid_signer.py`

### Complete replacement with mocked tests

```python
"""Tests for Hyperliquid signer via Privy."""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.venues.hyperliquid.signer import HyperliquidSigner, SignedOrder


@pytest.fixture
def mock_privy_client():
    """Create mocked Privy client."""
    with patch('src.venues.hyperliquid.signer.PrivyClient') as mock:
        client = Mock()
        client.wallet = AsyncMock()
        client.wallet.sign_typed_data = AsyncMock(return_value="0xsignature123")
        mock.return_value = client
        yield client


@pytest.fixture
def mock_settings():
    """Mock settings with Privy config."""
    with patch('src.venues.hyperliquid.signer.get_settings') as mock:
        settings = Mock()
        settings.privy_app_id = "test-app-id"
        settings.privy_app_secret = "test-secret"
        settings.privy_auth_key_path = "test_auth.pem"
        settings.wallet_address = "0x1234567890abcdef"
        mock.return_value = settings
        yield settings


class TestHyperliquidSigner:
    """Test Hyperliquid signer with Privy."""
    
    def test_init(self, mock_privy_client, mock_settings):
        """Test signer initialization."""
        signer = HyperliquidSigner()
        
        assert signer.address == "0x1234567890abcdef"
        mock_privy_client.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_sign_order(self, mock_privy_client, mock_settings):
        """Test signing an order via Privy."""
        signer = HyperliquidSigner()
        
        signed = await signer.sign_order(
            coin="SOL",
            is_buy=False,
            sz="10.0",
            limit_px="100.0",
            order_type={"limit": {"tif": "Gtc"}},
        )
        
        assert isinstance(signed, SignedOrder)
        assert signed.signature == "0xsignature123"
        assert signed.coin == "SOL"
        assert not signed.is_buy
        
        # Verify Privy was called
        mock_privy_client.wallet.sign_typed_data.assert_called_once()
        call_args = mock_privy_client.wallet.sign_typed_data.call_args
        assert call_args.kwargs['wallet_address'] == "0x1234567890abcdef"
    
    @pytest.mark.asyncio
    async def test_sign_order_error(self, mock_privy_client, mock_settings):
        """Test error handling when Privy fails."""
        mock_privy_client.wallet.sign_typed_data.side_effect = Exception("Privy error")
        
        signer = HyperliquidSigner()
        
        with pytest.raises(Exception, match="Privy error"):
            await signer.sign_order(
                coin="SOL",
                is_buy=True,
                sz="1.0",
                limit_px="50.0",
                order_type={"market": {}},
            )
```

---

## File 6: `tests/unit/config/test_settings.py`

### Update existing tests

```python
"""Tests for settings configuration."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.config.settings import Settings, get_settings


class TestSettings:
    """Test settings with Privy configuration."""
    
    @patch('src.config.settings.get_secret')
    @patch('pathlib.Path.exists')
    def test_check_required_secrets_privy(self, mock_exists, mock_get_secret):
        """Test that Privy secrets are checked."""
        # Mock auth key file exists
        mock_exists.return_value = True
        
        # Mock empty secrets
        mock_get_secret.return_value = ""
        
        settings = Settings()
        missing = settings.check_required_secrets()
        
        # Should require Privy fields
        assert any("PRIVY_APP_ID" in m for m in missing)
        assert any("PRIVY_APP_SECRET" in m for m in missing)
        assert any("WALLET_ADDRESS" in m for m in missing)
    
    @patch('src.config.settings.get_secret')
    @patch('pathlib.Path.exists')
    def test_check_required_secrets_no_auth_key(self, mock_exists, mock_get_secret):
        """Test missing auth key file is detected."""
        mock_exists.return_value = False
        mock_get_secret.return_value = "exists"
        
        settings = Settings()
        missing = settings.check_required_secrets()
        
        assert any("PRIVY_AUTH_KEY" in m for m in missing)
    
    @patch('src.config.settings.get_secret')
    @patch('pathlib.Path.exists')
    def test_all_secrets_present(self, mock_exists, mock_get_secret):
        """Test no missing secrets when all present."""
        mock_exists.return_value = True
        mock_get_secret.return_value = "present"
        
        settings = Settings()
        missing = settings.check_required_secrets()
        
        # Should not have old private key fields
        assert not any("HYPERLIQUID_PRIVATE_KEY" in m for m in missing)
        assert not any("SOLANA_PRIVATE_KEY" in m for m in missing)
```

---

## File 7: `.env.example` Update

### Replace private key examples with Privy config

```bash
# BasisStrategy Bot Configuration
# Copy to .env and fill in your values

# Environment
ENVIRONMENT=development
PAPER_TRADING=true
LOG_LEVEL=INFO

# HyperLiquid API (for reading market data)
HYPERLIQUID_API_KEY=your-hyperliquid-api-key
HYPERLIQUID_API_SECRET=your-hyperliquid-secret

# Arbitrum RPC
ARBITRUM_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/YOUR_KEY

# Privy Configuration (REQUIRED)
# Get these from https://dashboard.privy.io
PRIVY_APP_ID=your-privy-app-id
PRIVY_APP_SECRET=your-privy-app-secret
PRIVY_AUTH_KEY_PATH=privy_auth.pem

# Wallet Addresses (from Privy)
WALLET_ADDRESS=0x...your-evm-address...
SOLANA_WALLET_ADDRESS=...your-solana-address...

# Asgard API
ASGARD_API_KEY=your-asgard-api-key
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Admin
ADMIN_API_KEY=your-secure-admin-key
```

---

## File 8: `requirements/bot.txt` Update

### Add Privy dependency

```txt
# ... existing requirements ...

# Privy for secure wallet infrastructure
privy>=0.1.0

# Keep these (still needed)
eth-account>=0.8.0
solders>=0.20.0
```

---

## Summary of All Changes

| File | Change Type | Lines |
|------|-------------|-------|
| `src/config/settings.py` | Remove 2 fields, add 5 fields | ~20 changed |
| `src/venues/hyperliquid/signer.py` | Complete refactor | ~150 new |
| `src/venues/asgard/transactions.py` | Remove keypair, use Privy | ~20 changed |
| `src/venues/privy_client.py` | New file | ~20 new |
| `tests/unit/venues/test_hyperliquid_signer.py` | New mocked tests | ~100 new |
| `tests/unit/config/test_settings.py` | Update assertions | ~20 changed |
| `.env.example` | Update examples | ~15 changed |
| `requirements/bot.txt` | Add dependency | ~1 added |

**Total:** ~8 files modified, ~350 lines changed
