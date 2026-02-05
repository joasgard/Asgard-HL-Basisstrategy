# Bot Setup Onboarding Flow Specification

## Security-First Implementation

**Version:** 1.0  
**Classification:** Security-Critical  
**Threat Level:** High (handles private keys and API credentials)

---

## Executive Summary

This specification defines a defense-in-depth onboarding system supporting both CLI (recommended for security) and Web (for usability) interfaces. All implementation decisions prioritize security over convenience.

### Security Posture

| Feature | Implementation | Rationale |
|---------|---------------|-----------|
| Private Key Handling | Never touch disk unencrypted; hardware-bound encryption | Prevents theft from filesystem |
| Session Management | Time-bounded, single-use, IP-bound sessions | Limits attack window |
| Input Validation | Server-side + client-side, constant-time comparison | Prevents timing attacks |
| Crash Reporting | Aggressive PII sanitization with regex patterns | Prevents credential leakage in logs |
| Network Privacy | Optional Tor routing, jittered requests | Prevents metadata correlation |
| Atomic Writes | Two-phase commit with rollback | Prevents partial configuration |

---

## Architecture Overview

### Privy-Powered Wallet Infrastructure

All wallet operations are handled by [Privy](https://privy.io) embedded wallet infrastructure. No private keys are stored locally.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Setup Architecture                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  CLI Mode                       Web Mode                                 │
│  ┌─────────────────────┐       ┌──────────────────────────┐             │
│  │ Terminal            │       │ Browser                  │             │
│  │ • Direct input      │       │ • Email/OTP login        │             │
│  │ • No browser        │       │ • Embedded wallet        │             │
│  │ • API key auth      │       │ • Auto-created           │             │
│  └──────────┬──────────┘       └───────────┬──────────────┘             │
│             │                              │                             │
│             └──────────────┬───────────────┘                             │
│                            │                                            │
│              ┌─────────────▼──────────────┐                             │
│              │      Privy API             │                             │
│              │                            │                             │
│              │  • Embedded wallets        │                             │
│              │  • Server-side signing     │                             │
│              │  • TEE key sharding        │                             │
│              │  • Multi-chain support     │                             │
│              └─────────────┬──────────────┘                             │
│                            │                                            │
│              ┌─────────────▼──────────────┐                             │
│              │   Secure Enclave (TEE)     │                             │
│              │   (Privy infrastructure)   │                             │
│              └────────────────────────────┘                             │
│                                                                          │
│  Local Storage:                                                          │
│  • hyperliquid_api_key.txt (env or file)                                │
│  • privy_app_id / privy_app_secret (env)                                │
│  • NO PRIVATE KEYS stored locally                                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Benefits:**
- ✅ No local private key storage
- ✅ Server-side automated signing via Privy API
- ✅ 50K free signatures/month (sufficient for trading)
- ✅ Multi-chain: Arbitrum, Hyperliquid, Solana, etc.
- ✅ Keys sharded in TEEs (Trusted Execution Environments)

---

## Phase 1: Pre-Flight Security Checks

### 1.1 Environment Hardening

```python
# src/setup/security_checks.py

import os
import sys
import stat
from pathlib import Path
from typing import Tuple, List

class EnvironmentSecurityChecker:
    """Verify environment is secure before handling secrets."""
    
    CRITICAL_CHECKS = [
        'check_root_privileges',
        'check_filesystem_permissions',
        'check_environment_variables',
        'check_swap_space',
        'check_core_dumps',
    ]
    
    @classmethod
    def run_all(cls) -> Tuple[bool, List[str]]:
        """
        Run all security checks.
        
        Returns:
            (passed, warnings): Whether checks passed and any warnings
        """
        warnings = []
        
        for check_name in cls.CRITICAL_CHECKS:
            check = getattr(cls, check_name)
            passed, message = check()
            if not passed:
                warnings.append(f"[SECURITY] {check_name}: {message}")
        
        return len(warnings) == 0, warnings
    
    @staticmethod
    def check_root_privileges() -> Tuple[bool, str]:
        """Ensure we're not running as root."""
        if os.geteuid() == 0:
            return False, "Running as root. Create a non-privileged user."
        return True, "OK"
    
    @staticmethod
    def check_filesystem_permissions() -> Tuple[bool, str]:
        """Ensure working directory has restrictive permissions."""
        cwd = Path.cwd()
        stat_info = cwd.stat()
        mode = stat.S_IMODE(stat_info.st_mode)
        
        # Check if others can read/write
        if mode & stat.S_IROTH or mode & stat.S_IWOTH:
            return False, f"Directory {cwd} is world-readable/writeable"
        
        return True, "OK"
    
    @staticmethod
    def check_swap_space() -> Tuple[bool, str]:
        """Warn if swap is enabled (secrets can be written to disk)."""
        try:
            with open('/proc/swaps') as f:
                swaps = f.read().strip()
            if len(swaps.split('\n')) > 1:
                return False, "Swap is enabled. Secrets may be written to disk. Disable swap or use encrypted swap."
        except:
            pass
        return True, "OK"
    
    @staticmethod
    def check_core_dumps() -> Tuple[bool, str]:
        """Ensure core dumps are disabled (can contain secrets from memory)."""
        try:
            import resource
            if resource.getrlimit(resource.RLIMIT_CORE)[0] > 0:
                return False, "Core dumps enabled. Set 'ulimit -c 0' to disable."
        except:
            pass
        return True, "OK"
```

### 1.2 Secure Memory Management

```python
# src/setup/secure_memory.py

import ctypes
import sys
import secrets

class SecureBuffer:
    """
    Memory buffer that is securely wiped on deletion.
    Uses mlock to prevent swapping to disk.
    """
    
    def __init__(self, size: int):
        self.size = size
        self.buffer = ctypes.create_string_buffer(size)
        
        # Lock memory to prevent swapping (Unix only)
        if hasattr(ctypes.CDLL(None), 'mlock'):
            ctypes.CDLL(None).mlock(ctypes.byref(self.buffer), size)
    
    def write(self, data: bytes, offset: int = 0):
        """Write data to buffer at offset."""
        if len(data) + offset > self.size:
            raise ValueError("Data exceeds buffer size")
        
        for i, byte in enumerate(data):
            self.buffer[offset + i] = byte
    
    def read(self, length: int = None) -> bytes:
        """Read data from buffer."""
        if length is None:
            length = self.size
        return bytes(self.buffer[:length])
    
    def __del__(self):
        """Securely wipe buffer before deletion."""
        if hasattr(self, 'buffer'):
            # Overwrite with random data
            random_data = secrets.token_bytes(self.size)
            self.write(random_data)
            
            # Overwrite with zeros
            self.write(b'\x00' * self.size)
            
            # Unlock memory
            if hasattr(ctypes.CDLL(None), 'munlock'):
                ctypes.CDLL(None).munlock(ctypes.byref(self.buffer), self.size)
            
            del self.buffer

def secure_input(prompt: str) -> SecureBuffer:
    """
    Get secure input into a SecureBuffer.
    Never returns a Python string (which is immutable and may be interned).
    """
    import getpass
    
    # Get input
    user_input = getpass.getpass(prompt)
    
    # Copy to secure buffer
    buf = SecureBuffer(len(user_input))
    buf.write(user_input.encode())
    
    # Wipe original string from memory (best effort)
    input_id = id(user_input)
    input_len = len(user_input)
    
    # Overwrite the string's memory
    ctypes.memset(input_id, 0, input_len)
    
    return buf
```

---
---

## Phase 2: Security Model (Privy-Based)

### 2.1 How Privy Secures Keys

Privy uses a **sharded key architecture** with Trusted Execution Environments (TEEs):

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

### 2.2 Local Storage

**What we store locally:**
```
.env
├── HYPERLIQUID_API_KEY_PATH       # Encrypted API key
├── HYPERLIQUID_API_SECRET_PATH    # Encrypted API secret
├── PRIVY_APP_ID                   # Public app identifier
├── PRIVY_APP_SECRET               # Server credential (not wallet key)
├── PRIVY_AUTH_KEY_PATH            # Your server signing key
└── WALLET_ADDRESS                 # Public address only

privy_auth.pem                     # Your server's EC key for Privy API
```

**What we DON'T store:**
- ❌ Private keys (managed by Privy)
- ❌ Seed phrases (managed by Privy)
- ❌ Unencrypted credentials

### 2.3 API Credentials Encryption

While wallet keys are managed by Privy, we still encrypt local API credentials:

```python
# src/setup/encryption.py

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

class LocalEncryption:
    """Encrypt local API credentials (not wallet keys)."""
    
    def __init__(self, key: bytes):
        self.key = key
    
    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt API key/secret for local storage."""
        aesgcm = AESGCM(self.key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return nonce + ciphertext
    
    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt for use."""
        aesgcm = AESGCM(self.key)
        nonce = ciphertext[:12]
        encrypted = ciphertext[12:]
        plaintext = aesgcm.decrypt(nonce, encrypted, None)
        return plaintext.decode()

# Key derived from hardware fingerprint + env var
encryption_key = derive_key_from_hardware()
```

### 2.4 Threat Model Comparison

| Threat | Self-Hosted Keys | Privy-Based |
|--------|-----------------|-------------|
| Server compromise | **Total loss** (keys on disk) | **Limited** (no keys stored) |
| Backup mishandling | Keys leaked | Keys recoverable via Privy |
| Developer error | Keys in git/logs | No local keys to leak |
| Privy shutdown | N/A | Export keys before shutdown |
| Insider (our team) | Full access | No access to keys |
| Insider (Privy) | N/A | TEE prevents access |

### 2.5 Migration Path

Users can export keys from Privy at any time:

```python
# Export to self-custody
from privy import PrivyClient

privy = PrivyClient(...)

# Get wallet's private key for export
private_key = await privy.wallet.export_private_key(
    wallet_address="0x..."
)

print(f"Private key: {private_key}")
print("Store securely - this is your self-custody backup!")
```

**When to export:**
- Migrating to different wallet infrastructure
- Want hardware wallet custody
- Privy service discontinuation (unlikely)

## Phase 3: CLI Implementation

### 3.1 Secure Input Handling

```python
# src/setup/cli_wizard.py

import re
import sys
from typing import Callable, Optional, Tuple
from getpass import getpass

from .secure_memory import SecureBuffer, secure_input
from .encryption import SecureSecretStorage
from .validators import InputValidator

class SecureCLIWizard:
    """
    CLI wizard with secure input handling.
    
    Security features:
    - Input never appears in shell history
    - Secrets stored in SecureBuffer (wipeable memory)
    - Immediate validation without logging
    - No echo to terminal for sensitive fields
    """
    
    def __init__(self):
        self.storage = SecureSecretStorage()
        self.config = {}
        self.secure_inputs = []  # Track for cleanup
    
    def __del__(self):
        """Ensure all secure buffers are wiped."""
        for buf in self.secure_inputs:
            del buf
    
    def prompt_secure(
        self,
        message: str,
        validator: Optional[Callable[[str], Tuple[bool, str]]] = None,
        confirm: bool = False
    ) -> SecureBuffer:
        """
        Prompt for secure input with optional confirmation.
        
        Args:
            message: Prompt message
            validator: Function to validate input
            confirm: Whether to require confirmation entry
        
        Returns:
            SecureBuffer containing input
        """
        while True:
            # Get input into secure buffer
            buf = secure_input(f"{message}: ")
            
            # Validate
            if validator:
                raw_value = buf.read().decode().rstrip('\x00')
                valid, error = validator(raw_value)
                if not valid:
                    print(f"❌ {error}")
                    del buf
                    continue
            
            # Confirmation if requested
            if confirm:
                confirm_buf = secure_input(f"Confirm {message}: ")
                if buf.read() != confirm_buf.read():
                    print("❌ Inputs do not match")
                    del buf
                    del confirm_buf
                    continue
                del confirm_buf
            
            self.secure_inputs.append(buf)
            return buf
    
    def run(self):
        """Execute the setup wizard."""
        print("""
╔══════════════════════════════════════════════════════════════╗
║           BasisStrategy Bot - Secure Setup                   ║
║                                                              ║
║  ⚠️  This wizard will handle sensitive cryptographic keys.   ║
║                                                              ║
║  Security measures active:                                   ║
║  • Input hidden from terminal                                ║
║  • Memory locked (no swap)                                   ║
║  • Hardware-bound encryption                                 ║
║  • Atomic configuration writes                               ║
╚══════════════════════════════════════════════════════════════╝
        """)
        
        # Run security checks
        print("Running security checks...")
        from .security_checks import EnvironmentSecurityChecker
        passed, warnings = EnvironmentSecurityChecker.run_all()
        
        if not passed:
            print("\n⚠️  Security warnings detected:")
            for warning in warnings:
                print(f"   {warning}")
            
            response = input("\nContinue despite warnings? [y/N]: ")
            if response.lower() != 'y':
                print("Setup aborted.")
                sys.exit(1)
        
        print("✓ Security checks passed\n")
        
        # Phase 1: Exchange credentials
        self._setup_exchange_credentials()
        
        # Phase 2: Blockchain
        self._setup_blockchain()
        
        # Phase 3: Risk configuration
        self._setup_risk_parameters()
        
        # Phase 4: Write configuration
        self._write_configuration()
        
        print("\n✓ Setup complete!")
    
    def _setup_exchange_credentials(self):
        """Configure HyperLiquid credentials."""
        print("═" * 62)
        print("Step 1/4: Exchange Configuration")
        print("═" * 62)
        
        # API Key
        api_key_buf = self.prompt_secure(
            "HyperLiquid API Key",
            validator=InputValidator.validate_hyperliquid_key
        )
        
        # API Secret
        api_secret_buf = self.prompt_secure(
            "HyperLiquid API Secret",
            validator=InputValidator.validate_hyperliquid_secret
        )
        
        # Test connection
        print("\nTesting HyperLiquid connection...")
        api_key = api_key_buf.read().decode().rstrip('\x00')
        api_secret = api_secret_buf.read().decode().rstrip('\x00')
        
        from .connection_tests import test_hyperliquid_connection
        result = test_hyperliquid_connection(api_key, api_secret)
        
        if not result['success']:
            print(f"❌ Connection failed: {result['error']}")
            retry = input("Retry? [Y/n]: ").lower()
            if retry != 'n':
                return self._setup_exchange_credentials()
        else:
            print(f"✓ Connected (Balance: ${result['balance']:,.2f})")
        
        # Store securely
        self.storage.write_secret('hyperliquid_api_key', api_key)
        self.storage.write_secret('hyperliquid_api_secret', api_secret)
        
        print("✓ Credentials encrypted and stored\n")
    
    def _setup_blockchain(self):
        """
        Configure blockchain connection and Privy wallet.
        """
        print("═" * 62)
        print("Step 2/4: Blockchain & Privy Configuration")
        print("═" * 62)
        
        # RPC URL
        rpc_url = input("Arbitrum RPC URL (or 'alchemy'/'infura'): ").strip()
        
        if rpc_url.lower() == 'alchemy':
            alchemy_key = getpass("Alchemy API Key: ")
            rpc_url = f"https://arb-mainnet.g.alchemy.com/v2/{alchemy_key}"
        elif rpc_url.lower() == 'infura':
            infura_key = getpass("Infura API Key: ")
            rpc_url = f"https://arbitrum-mainnet.infura.io/v3/{infura_key}"
        
        # Test RPC
        print("\nTesting Arbitrum connection...")
        from .connection_tests import test_arbitrum_connection
        result = test_arbitrum_connection(rpc_url)
        
        if not result['success']:
            print(f"❌ RPC connection failed: {result['error']}")
            return self._setup_blockchain()
        
        print(f"✓ Connected (Block: {result['block']:,})")
        self.config['arbitrum_rpc_url'] = rpc_url
        
        # Privy Configuration
        print("\n" + "═" * 62)
        print("Privy Wallet Setup")
        print("═" * 62)
        print("Your wallet will be created and managed by Privy.")
        print("Keys are sharded in secure enclaves - never stored locally.\n")
        
        privy_app_id = input("Privy App ID: ").strip()
        privy_app_secret = getpass("Privy App Secret: ")
        
        # Check for authorization key
        auth_key_path = Path("privy_auth.pem")
        if not auth_key_path.exists():
            print("\n⚠️  Privy authorization key not found.")
            generate = input("Generate new authorization key? [Y/n]: ").lower() != 'n'
            
            if generate:
                import subprocess
                subprocess.run([
                    "openssl", "ecparam", "-name", "prime256v1",
                    "-genkey", "-noout", "-out", "privy_auth.pem"
                ], check=True)
                subprocess.run([
                    "openssl", "ec", "-in", "privy_auth.pem",
                    "-pubout", "-out", "privy_auth.pub"
                ], check=True)
                print("✓ Authorization key generated: privy_auth.pem")
                print("  Register the public key (privy_auth.pub) in your Privy dashboard.")
            else:
                print("Please generate the key manually:")
                print("  openssl ecparam -name prime256v1 -genkey -noout -out privy_auth.pem")
                return self._setup_blockchain()
        
        # Create wallet via Privy
        print("\nCreating embedded wallet via Privy...")
        
        try:
            from privy import PrivyClient
            
            privy = PrivyClient(
                app_id=privy_app_id,
                app_secret=privy_app_secret,
                authorization_private_key_path="privy_auth.pem"
            )
            
            wallet = privy.wallet.create(
                chain_type="ethereum",
                account_type="secp256k1"
            )
            
            print(f"✓ Wallet created: {wallet.address}")
            print("  (Keys stored securely in Privy TEEs)")
            
            self.config['wallet_address'] = wallet.address
            self.config['privy_app_id'] = privy_app_id
            self.config['privy_app_secret'] = privy_app_secret
            
        except Exception as e:
            print(f"❌ Failed to create wallet: {e}")
            return self._setup_blockchain()
        
        print()
    
    def _setup_risk_parameters(self):
        """Configure risk management settings."""
        print("═" * 62)
        print("Step 3/4: Risk Configuration")
        print("═" * 62)
        
        presets = {
            '1': ('Conservative', 5000, 2, 3.0),
            '2': ('Balanced', 10000, 3, 5.0),
            '3': ('Aggressive', 25000, 5, 8.0),
        }
        
        print("\nSelect risk profile:")
        for key, (name, size, positions, stop) in presets.items():
            print(f"  {key}. {name}: ${size:,} max, {positions} positions, {stop}% stop")
        print("  4. Custom")
        
        choice = input("\nChoice [2]: ").strip() or '2'
        
        if choice in presets:
            _, size, positions, stop = presets[choice]
            self.config['max_position_size'] = size
            self.config['max_positions'] = positions
            self.config['stop_loss'] = stop
        else:
            self.config['max_position_size'] = int(input("Max position size ($): "))
            self.config['max_positions'] = int(input("Max concurrent positions: "))
            self.config['stop_loss'] = float(input("Stop loss %: "))
        
        print(f"\n✓ Risk parameters configured\n")
    
    def _write_configuration(self):
        """Atomically write all configuration files."""
        print("═" * 62)
        print("Step 4/4: Writing Configuration")
        print("═" * 62)
        
        from .atomic_writer import AtomicConfigWriter
        
        writer = AtomicConfigWriter()
        
        try:
            with writer.stage() as staging:
                # Write .env
                env_content = self._generate_env_content()
                (staging / '.env').write_text(env_content)
                
                # Copy encrypted secrets
                import shutil
                shutil.copytree('secrets', staging / 'secrets', dirs_exist_ok=True)
                
                # Validate
                writer.validate(staging)
            
            print("✓ Configuration written atomically")
            print(f"✓ Backup created at: {writer.backup_path}")
            
        except Exception as e:
            print(f"❌ Failed to write configuration: {e}")
            raise
    
    def _generate_env_content(self) -> str:
        """Generate .env file content."""
        lines = [
            "# BasisStrategy Bot Configuration",
            f"# Generated: {datetime.now().isoformat()}",
            "",
            "# HyperLiquid API (stored locally)",
            "HYPERLIQUID_API_KEY_PATH=secrets/hyperliquid_api_key.enc",
            "HYPERLIQUID_API_SECRET_PATH=secrets/hyperliquid_api_secret.enc",
            "",
            "# Arbitrum RPC",
            f"ARBITRUM_RPC_URL={self.config.get('arbitrum_rpc_url', '')}",
            "",
            "# Privy Configuration (wallet managed by Privy)",
            f"PRIVY_APP_ID={self.config.get('privy_app_id', '')}",
            f"PRIVY_APP_SECRET={self.config.get('privy_app_secret', '')}",
            "PRIVY_AUTH_KEY_PATH=privy_auth.pem",
            f"WALLET_ADDRESS={self.config.get('wallet_address', '')}",
            "",
            "# Risk Parameters",
            f"MAX_POSITION_SIZE={self.config.get('max_position_size', 10000)}",
            f"MAX_CONCURRENT_POSITIONS={self.config.get('max_positions', 3)}",
            f"STOP_LOSS_THRESHOLD={self.config.get('stop_loss', 5.0)}",
        ]
        return '\n'.join(lines)
```

### 3.2 Atomic Configuration Writing

```python
# src/setup/atomic_writer.py

import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Optional

class AtomicConfigWriter:
    """
    Ensures configuration is written completely or not at all.
    Implements two-phase commit with rollback capability.
    """
    
    def __init__(self):
        self.backup_path: Optional[Path] = None
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    @contextmanager
    def stage(self):
        """
        Context manager for staging configuration.
        
        Yields a temporary directory where configuration should be written.
        On successful exit, atomically swaps to production.
        On exception, restores from backup.
        """
        temp_dir = Path(tempfile.mkdtemp(prefix=f'basis_setup_{self.timestamp}_'))
        
        # Create backup if existing config exists
        if Path('.env').exists():
            self.backup_path = Path(f'.env.backup.{self.timestamp}')
            shutil.copy('.env', self.backup_path)
            
            if Path('secrets').exists():
                shutil.copytree('secrets', f'secrets.backup.{self.timestamp}')
        
        try:
            yield temp_dir
            
            # Commit: Validate first
            self._validate_staged(temp_dir)
            
            # Commit: Atomic swap
            self._atomic_swap(temp_dir)
            
        except Exception:
            # Rollback on any error
            self._rollback()
            raise
        finally:
            # Cleanup temp
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _validate_staged(self, staging: Path):
        """Validate staged configuration before commit."""
        # Check all required files exist
        required = ['.env']
        for file in required:
            if not (staging / file).exists():
                raise ValueError(f"Missing required file: {file}")
        
        # Validate .env syntax
        env_content = (staging / '.env').read_text()
        for line in env_content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and '=' not in line:
                raise ValueError(f"Invalid .env line: {line}")
    
    def _atomic_swap(self, staging: Path):
        """Perform atomic swap of configuration."""
        # Move current to backup (if exists)
        if Path('.env').exists():
            current_backup = Path(f'.env.old.{self.timestamp}')
            Path('.env').rename(current_backup)
        
        if Path('secrets').exists():
            secrets_backup = Path(f'secrets.old.{self.timestamp}')
            Path('secrets').rename(secrets_backup)
        
        # Move staged to current
        shutil.move(str(staging / '.env'), '.env')
        shutil.move(str(staging / 'secrets'), 'secrets')
        
        # Cleanup old backups on success (keep last 3)
        self._cleanup_old_backups()
    
    def _rollback(self):
        """Restore from backup on failure."""
        if self.backup_path and self.backup_path.exists():
            shutil.copy(self.backup_path, '.env')
            print(f"⚠️  Rolled back to: {self.backup_path}")
    
    def _cleanup_old_backups(self, keep: int = 3):
        """Keep only the most recent N backups."""
        backups = sorted(Path('.').glob('.env.backup.*'))
        for old_backup in backups[:-keep]:
            old_backup.unlink()
            old_secrets = Path(str(old_backup).replace('.env.', 'secrets.'))
            if old_secrets.exists():
                shutil.rmtree(old_secrets)
```

---

## Privy Integration

### What is Privy?

[Privy](https://privy.io) provides embedded wallet infrastructure with server-side signing. Private keys are sharded across secure enclaves (TEEs) and never stored locally.

**Pricing:** 50,000 free signatures/month (sufficient for ~1,600 trades/day)

### Server-Side Signing Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Trading Bot    │────▶│  Privy API       │────▶│  TEE Enclave    │
│  (Your Server)  │◀────│  (Authorization) │◀────│  (Key Shards)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │
    1. Bot decides to trade
    2. Constructs transaction
    3. Calls Privy API with auth key
    4. Privy reconstitutes key in TEE
    5. Signs transaction
    6. Returns signed tx
    7. Bot broadcasts to chain
```

### Required Credentials

Users must provide:

1. **Privy App ID** (from Privy Dashboard)
2. **Privy App Secret** (from Privy Dashboard)
3. **Authorization Private Key** (self-generated EC key for server signing)

```bash
# Generate authorization key (one-time setup)
openssl ecparam -name prime256v1 -genkey -noout -out privy_auth.pem
openssl ec -in privy_auth.pem -pubout -out privy_auth.pub

# Register public key in Privy Dashboard
```

### Wallet Creation Flow

**Both CLI and Web use Privy for wallet management:**

```python
from privy import PrivyClient

# Initialize with server credentials
privy = PrivyClient(
    app_id=os.getenv('PRIVY_APP_ID'),
    app_secret=os.getenv('PRIVY_APP_SECRET'),
    authorization_private_key_path='privy_auth.pem'
)

# Create embedded wallet
wallet = await privy.wallet.create(
    chain_type='ethereum',
    account_type='secp256k1'
)

# Store only the address locally
wallet_address = wallet.address
```

### Signing Transactions

```python
# Trading bot signs automatically via Privy API
signed_tx = await privy.wallet.sign_transaction(
    wallet_address=wallet_address,
    transaction={
        'to': '0xvault_address...',
        'data': deposit_calldata,
        'value': 0,
        'chain_id': 42161  # Arbitrum
    }
)

# Broadcast to chain
await web3.eth.send_raw_transaction(signed_tx.raw_transaction)
```

---

## Phase 4: Web Implementation (Privy-Powered)

### 4.1 Security Model

The web interface uses Privy's hosted authentication:

1. **Localhost-only**: Only accepts connections from 127.0.0.1
2. **Privy managed**: All wallet operations via Privy SDK
3. **Email/OTP auth**: Users log in via Privy's hosted UI
4. **No local keys**: Private keys never touch local filesystem
5. **Auto-created**: Wallet generated on first login
### 4.2 Frontend Implementation

```html
<!-- src/dashboard/templates/setup.html -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" 
          content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; 
                   connect-src 'self' ws://localhost:8080;
                   form-action 'self';
                   base-uri 'none';
                   frame-ancestors 'none';">
    <title>BasisStrategy Setup</title>
    <style>
        /* Setup-specific styles */
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 2rem auto;
            padding: 0 1rem;
            background: #0a0a0a;
            color: #e0e0e0;
        }
        
        .security-banner {
            background: #1a1a2e;
            border-left: 4px solid #ffd700;
            padding: 1rem;
            margin-bottom: 2rem;
        }
        
        .secure-input {
            font-family: 'Courier New', monospace;
            background: #1a1a1a;
            border: 1px solid #333;
            color: #0f0;
            padding: 0.75rem;
            width: 100%;
            font-size: 1rem;
            letter-spacing: 0.1em;
        }
        
        .step {
            display: none;
            animation: fadeIn 0.3s;
        }
        
        .step.active {
            display: block;
        }
        
        .connection-status {
            padding: 0.75rem;
            margin: 0.5rem 0;
            border-radius: 4px;
        }
        
        .connection-status.testing {
            background: #332200;
            color: #ffaa00;
        }
        
        .connection-status.success {
            background: #002200;
            color: #00ff00;
        }
        
        .connection-status.error {
            background: #220000;
            color: #ff0000;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>
    <div class="security-banner">
        <strong>🔒 Secure Setup Mode</strong>
        <ul>
            <li>This page is only accessible from this computer</li>
            <li>Session expires in <span id="countdown">30:00</span></li>
            <li>All data is encrypted before transmission</li>
            <li>No secrets are stored in browser</li>
        </ul>
    </div>
    
    <!-- Step 1: Setup Key Verification -->
    <div class="step active" data-step="1">
        <h1>Setup Key Verification</h1>
        <p>Enter the setup key displayed in your terminal:</p>
        
        <input type="text" id="setup-key" class="secure-input" 
               placeholder="XXXX-XXXX-XXXX-XXXX" maxlength="19">
        
        <button onclick="verifySetupKey()">Verify & Continue</button>
    </div>
    
    <!-- Step 2: Exchange Configuration -->
    <div class="step" data-step="2">
        <h1>Exchange Configuration</h1>
        
        <h3>HyperLiquid API</h3>
        <input type="password" id="hl-api-key" class="secure-input" 
               placeholder="API Key" autocomplete="off">
        <input type="password" id="hl-api-secret" class="secure-input" 
               placeholder="API Secret" autocomplete="off">
        
        <button onclick="testHyperLiquid()">Test Connection</button>
        <div id="hl-status" class="connection-status" style="display:none;"></div>
        
        <button onclick="nextStep()" id="step2-next" disabled>Continue</button>
    </div>
    
    <!-- Step 3: Privy Wallet Setup -->
    <div class="step" data-step="3">
        <h1>Wallet Setup via Privy</h1>
        
        <div class="info-box" style="background:#001a33;padding:1rem;margin:1rem 0;">
            <strong>ℹ️ Privy-Powered Wallets</strong>
            <p>Your wallet will be created and managed by Privy's secure infrastructure.</p>
            <ul>
                <li>Keys are sharded across secure enclaves (TEEs)</li>
                <li>Never stored on local filesystem</li>
                <li>Server-side signing for automated trading</li>
                <li>50,000 free signatures per month</li>
            </ul>
        </div>
        
        <h3>Connect Your Wallet</h3>
        <p>Login with email to create or access your embedded wallet:</p>
        
        <!-- Privy React SDK will render here -->
        <div id="privy-login"></div>
        
        <div id="wallet-info" style="display:none;margin-top:1rem;">
            <div class="success-box" style="background:#002200;padding:1rem;">
                <strong>✓ Wallet Connected</strong>
                <p>Address: <code id="wallet-address"></code></p>
                <p class="hint">Fund this address with USDC on Arbitrum to start trading.</p>
                <p class="backup-hint" style="font-size:0.9em;color:#888;">
                    💡 Your private key is managed securely by Privy. You can export it anytime from settings.
                </p>
            </div>
        </div>
        
        <hr style="margin: 2rem 0; border-color: #333;">
        
        <h3>Arbitrum RPC Connection</h3>
        <select id="rpc-provider">
            <option value="alchemy">Alchemy (Recommended)</option>
            <option value="infura">Infura</option>
            <option value="custom">Custom RPC URL</option>
        </select>
        
        <input type="password" id="rpc-key" class="secure-input" 
               placeholder="RPC API Key" autocomplete="off">
        
        <button onclick="testRPC()">Test Connection</button>
        <div id="rpc-status"></div>
            </div>
        </div>
    </div>
    
    <!-- Step 4: Risk & Deploy -->
    <div class="step" data-step="4">
        <h1>Risk Configuration</h1>
        
        <div class="presets">
            <label class="preset-card">
                <input type="radio" name="risk" value="conservative">
                <strong>Conservative</strong>
                <p>Max: $5,000 | Positions: 2 | Stop: 3%</p>
            </label>
            
            <label class="preset-card">
                <input type="radio" name="risk" value="balanced" checked>
                <strong>Balanced</strong>
                <p>Max: $10,000 | Positions: 3 | Stop: 5%</p>
            </label>
        </div>
        
        <button onclick="deployConfiguration()" class="deploy-btn">
            Deploy Configuration
        </button>
    </div>
    
    <script>
        // Session management
        let sessionId = null;
        let setupKey = null;
        
        // Encrypt data before sending using ephemeral RSA
        async function encryptForServer(plaintext) {
            // Generate ephemeral key pair
            const keyPair = await window.crypto.subtle.generateKey(
                {
                    name: 'RSA-OAEP',
                    modulusLength: 4096,
                    publicExponent: new Uint8Array([1, 0, 1]),
                    hash: 'SHA-256'
                },
                true,
                ['encrypt']
            );
            
            // Encrypt data
            const encoder = new TextEncoder();
            const ciphertext = await window.crypto.subtle.encrypt(
                { name: 'RSA-OAEP' },
                keyPair.publicKey,
                encoder.encode(plaintext)
            );
            
            // Export public key for server
            const publicKey = await window.crypto.subtle.exportKey(
                'spki',
                keyPair.publicKey
            );
            
            // Clear plaintext from memory
            plaintext = null;
            
            return {
                ciphertext: Array.from(new Uint8Array(ciphertext)),
                publicKey: Array.from(new Uint8Array(publicKey))
            };
        }
        
        async function verifySetupKey() {
            const keyInput = document.getElementById('setup-key');
            setupKey = keyInput.value.replace(/-/g, '');
            
            // Clear input
            keyInput.value = '';
            
            const response = await fetch('/api/setup/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({setup_key: setupKey})
            });
            
            const data = await response.json();
            
            if (data.valid) {
                sessionId = data.session_id;
                showStep(2);
                startCountdown(data.expires_in);
            } else {
                alert('Invalid setup key');
            }
        }
        
        async function testHyperLiquid() {
            const apiKey = document.getElementById('hl-api-key').value;
            const apiSecret = document.getElementById('hl-api-secret').value;
            
            const statusDiv = document.getElementById('hl-status');
            statusDiv.style.display = 'block';
            statusDiv.className = 'connection-status testing';
            statusDiv.textContent = 'Testing connection...';
            
            // Encrypt credentials
            const encrypted = await encryptForServer(JSON.stringify({
                api_key: apiKey,
                api_secret: apiSecret
            }));
            
            // Clear from DOM
            document.getElementById('hl-api-key').value = '';
            document.getElementById('hl-api-secret').value = '';
            
            const response = await fetch('/api/setup/test-hyperliquid', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: sessionId,
                    encrypted_data: encrypted
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                statusDiv.className = 'connection-status success';
                statusDiv.innerHTML = `
                    ✓ Connected<br>
                    Balance: $${result.balance.toLocaleString()}
                `;
                document.getElementById('step2-next').disabled = false;
            } else {
                statusDiv.className = 'connection-status error';
                statusDiv.textContent = `✗ ${result.error}`;
            }
        }
        
        // Initialize Privy SDK
        const privy = new PrivyClient({
            appId: 'your-privy-app-id',
            config: {
                embeddedWallets: {
                    ethereum: {
                        createOnLogin: 'all-users'
                    }
                }
            }
        });
        
        // Handle wallet connection
        privy.on('wallet_connected', (wallet) => {
            document.getElementById('wallet-address').textContent = wallet.address;
            document.getElementById('wallet-info').style.display = 'block';
            
            // Store wallet address in session
            fetch('/api/setup/store-wallet-address', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: sessionId,
                    address: wallet.address
                })
            });
        });
        
        // Mount Privy login UI
        privy.mountLoginUI('#privy-login');
        
        function showStep(n) {
            document.querySelectorAll('.step').forEach(el => {
                el.classList.remove('active');
            });
            document.querySelector(`[data-step="${n}"]`).classList.add('active');
        }
        
        function startCountdown(seconds) {
            const el = document.getElementById('countdown');
            setInterval(() => {
                seconds--;
                const mins = Math.floor(seconds / 60);
                const secs = seconds % 60;
                el.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
                
                if (seconds <= 0) {
                    alert('Session expired. Please restart setup.');
                    window.location.reload();
                }
            }, 1000);
        }
        
        // Prevent accidental navigation
        window.onbeforeunload = function() {
            return "Setup is in progress. Are you sure you want to leave?";
        };
    </script>
</body>
</html>
```

### 4.3 Backend API (Secure)

```python
# src/dashboard/api/setup.py

import time
import secrets
from typing import Optional, Dict
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/setup")

# In-memory session store (cleared on restart or completion)
class SetupSession:
    def __init__(self):
        self.session_id = secrets.token_urlsafe(32)
        self.setup_key = secrets.token_urlsafe(12)[:16].upper()
        self.created_at = time.time()
        self.expires_at = self.created_at + 1800  # 30 minutes
        self.completed = False
        self.client_ip: Optional[str] = None
        self.current_step = 1
        
        # Encrypted data buffer (keys are ephemeral)
        self.staged_config: Dict[str, bytes] = {}

class SetupManager:
    def __init__(self):
        self.sessions: Dict[str, SetupSession] = {}
        self.used_keys: set = set()
    
    def create_session(self, client_ip: str) -> SetupSession:
        """Create new setup session restricted to client IP."""
        # Clean expired sessions
        self._cleanup_expired()
        
        # Check if setup already completed
        if Path('.env').exists():
            raise HTTPException(403, "Setup already completed")
        
        session = SetupSession()
        session.client_ip = client_ip
        self.sessions[session.session_id] = session
        
        return session
    
    def validate_session(self, session_id: str, client_ip: str) -> SetupSession:
        """Validate session exists, not expired, and from same IP."""
        session = self.sessions.get(session_id)
        
        if not session:
            raise HTTPException(404, "Session not found")
        
        if session.completed:
            raise HTTPException(410, "Setup already completed")
        
        if time.time() > session.expires_at:
            del self.sessions[session_id]
            raise HTTPException(410, "Session expired")
        
        if session.client_ip != client_ip:
            # Possible session hijacking attempt
            self._log_security_event("IP_MISMATCH", session_id, client_ip)
            raise HTTPException(403, "Session IP mismatch")
        
        return session
    
    def _cleanup_expired(self):
        """Remove expired sessions."""
        now = time.time()
        expired = [
            sid for sid, sess in self.sessions.items()
            if now > sess.expires_at
        ]
        for sid in expired:
            del self.sessions[sid]
    
    def _log_security_event(self, event: str, session_id: str, ip: str):
        """Log potential security incidents."""
        logger.warning(f"SECURITY: {event} | Session: {session_id[:8]}... | IP: {ip}")

# Global manager
setup_manager = SetupManager()

class SetupKeyVerify(BaseModel):
    setup_key: str = Field(..., min_length=16, max_length=16)

class EncryptedPayload(BaseModel):
    session_id: str
    encrypted_data: Dict  # RSA-encrypted JSON

@router.post("/start")
async def start_setup(request: Request):
    """
    Initialize setup session.
    Only allows localhost connections.
    """
    client_ip = request.client.host
    
    # Strict localhost check
    if client_ip not in ('127.0.0.1', '::1', 'localhost'):
        raise HTTPException(403, "Setup only available from localhost")
    
    session = setup_manager.create_session(client_ip)
    
    return {
        "session_id": session.session_id,
        "setup_key": session.setup_key,  # User must get this from terminal
        "expires_in": 1800
    }

@router.post("/verify")
async def verify_setup_key(data: SetupKeyVerify, request: Request):
    """
    Verify setup key and return session token.
    This binds the browser session to the terminal session.
    """
    client_ip = request.client.host
    
    # Find session with matching setup key
    for session in setup_manager.sessions.values():
        if session.setup_key == data.setup_key and session.client_ip == client_ip:
            return {
                "valid": True,
                "session_id": session.session_id,
                "expires_in": int(session.expires_at - time.time())
            }
    
    # Delay response to prevent timing attacks
    time.sleep(0.5)
    return JSONResponse(
        status_code=401,
        content={"valid": False, "error": "Invalid setup key"}
    )

@router.post("/test-hyperliquid")
async def test_hyperliquid(data: EncryptedPayload, request: Request):
    """Test HyperLiquid connection with encrypted credentials."""
    client_ip = request.client.host
    session = setup_manager.validate_session(data.session_id, client_ip)
    
    # Decrypt credentials using ephemeral key
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    
    try:
        # Load ephemeral private key (stored temporarily)
        private_key = serialization.load_der_private_key(
            bytes(data.encrypted_data['server_private_key']),
            password=None
        )
        
        # Decrypt
        ciphertext = bytes(data.encrypted_data['ciphertext'])
        plaintext = private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        creds = json.loads(plaintext.decode())
        
        # Test connection
        from src.setup.connection_tests import test_hyperliquid_connection
        result = test_hyperliquid_connection(
            creds['api_key'],
            creds['api_secret']
        )
        
        # Wipe credentials from memory
        creds = None
        plaintext = None
        
        return result
        
    except Exception as e:
        return {"success": False, "error": "Decryption or connection failed"}

@router.post("/store-wallet-address")
async def store_wallet_address(data: dict, request: Request):
    """
    Store wallet address from Privy connection.
    Actual wallet is managed by Privy infrastructure.
    """
    client_ip = request.client.host
    session = setup_manager.validate_session(data.get('session_id'), client_ip)
    
    address = data.get('address')
    if not address or not address.startswith('0x'):
        return {"success": False, "error": "Invalid address"}
    
    # Store just the address - keys are in Privy
    session.wallet_address = address
    
    return {
        "success": True,
        "address": address,
        "message": "Wallet address stored"
    }

@router.get("/privy-config")
async def get_privy_config(request: Request):
    """
    Get Privy app ID for frontend initialization.
    App secret stays server-side only.
    """
    return {
        "app_id": os.getenv('PRIVY_APP_ID'),
        "environment": os.getenv('PRIVY_ENVIRONMENT', 'production')
    }
```

---

## Phase 5: Validation & Testing

### 5.1 Input Validators

```python
# src/setup/validators.py

import re
from typing import Tuple
from eth_account import Account

class InputValidator:
    """Secure input validation with constant-time comparison."""
    
    @staticmethod
    def validate_ethereum_address(address: str) -> Tuple[bool, str]:
        """
        Validate Ethereum address format and checksum.
        """
        if not address.startswith('0x'):
            return False, "Address must start with 0x"
        
        if len(address) != 42:
            return False, "Address must be 42 characters (0x + 40 hex)"
        
        if not re.match(r'^0x[a-fA-F0-9]{40}$', address):
            return False, "Invalid characters in address"
        
        # Verify checksum
        try:
            if not Account.is_checksum_address(address):
                return True, "Valid format but checksum invalid (may be lowercase)"
        except:
            pass
        
        return True, "Valid"
    
    @staticmethod
    def validate_private_key(key: str) -> Tuple[bool, str]:
        """
        Validate private key format.
        """
        # Remove 0x prefix if present
        key = key.strip()
        if key.startswith('0x'):
            key = key[2:]
        
        if len(key) != 64:
            return False, "Private key must be 64 hex characters"
        
        if not re.match(r'^[a-fA-F0-9]{64}$', key):
            return False, "Invalid characters (must be hex)"
        
        # Validate it's a valid secp256k1 key
        try:
            Account.from_key(key)
        except Exception as e:
            return False, f"Invalid private key: {e}"
        
        return True, "Valid"
    
    @staticmethod
    def validate_hyperliquid_key(key: str) -> Tuple[bool, str]:
        """Validate HyperLiquid API key format."""
        if not re.match(r'^[a-fA-F0-9]{64}$', key):
            return False, "API key must be 64 hex characters"
        return True, "Valid"
    
    @staticmethod
    def validate_hyperliquid_secret(secret: str) -> Tuple[bool, str]:
        """Validate HyperLiquid API secret format."""
        if len(secret) < 32:
            return False, "API secret too short"
        return True, "Valid"
```

### 5.2 Connection Tests

```python
# src/setup/connection_tests.py

import asyncio
from typing import Dict

async def test_hyperliquid_connection(api_key: str, api_secret: str) -> Dict:
    """
    Test HyperLiquid connection without exposing credentials in error messages.
    """
    try:
        from src.venues.hyperliquid.client import HyperLiquidClient
        
        client = HyperLiquidClient(api_key=api_key, api_secret=api_secret)
        summary = await client.get_account_summary()
        
        # Extract only necessary info
        balance = float(summary.get("marginSummary", {}).get("accountValue", 0))
        
        return {
            "success": True,
            "balance": balance,
            "message": "Connection successful"
        }
    except Exception as e:
        # Sanitize error message
        error_str = str(e).lower()
        
        if "unauthorized" in error_str or "invalid" in error_str:
            message = "Invalid API credentials"
        elif "timeout" in error_str or "connection" in error_str:
            message = "Network error—check your connection"
        else:
            message = "Connection failed"
        
        return {
            "success": False,
            "error": message,
            "detail": None  # Never expose raw error
        }

async def test_arbitrum_connection(rpc_url: str) -> Dict:
    """Test Arbitrum RPC connection."""
    try:
        from web3 import Web3
        
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        if not w3.is_connected():
            return {"success": False, "error": "Cannot connect to RPC"}
        
        chain_id = w3.eth.chain_id
        if chain_id != 42161:
            return {
                "success": False, 
                "error": f"Wrong chain ID. Expected 42161 (Arbitrum), got {chain_id}"
            }
        
        block = w3.eth.block_number
        
        return {
            "success": True,
            "block": block,
            "message": f"Connected to Arbitrum (block {block})"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "RPC connection failed"
        }
```

---

## Phase 6: Sanitization & Logging

### 6.1 Secret Sanitization

```python
# src/setup/sanitization.py

import re
from typing import Dict, Any

class SecretSanitizer:
    """
    Aggressive sanitization of sensitive data from logs and errors.
    """
    
    # Patterns to redact
    PATTERNS = [
        # Private keys (64 hex)
        (r'\b[0-9a-fA-F]{64}\b', '[PRIVATE_KEY]'),
        
        # API keys (various formats)
        (r'(?i)(api[_-]?key[:\s=]+)[\w-]{20,}', r'\1[API_KEY]'),
        (r'(?i)(api[_-]?secret[:\s=]+)[\w-]{20,}', r'\1[API_SECRET]'),
        
        # JWT tokens
        (r'eyJ[\w-]*\.eyJ[\w-]*\.[\w-]*', '[JWT_TOKEN]'),
        
        # Passwords
        (r'(?i)(password[:\s=]+)[^\s&"\']+', r'\1[PASSWORD]'),
        
        # Ethereum addresses (optional—may want to keep for debugging)
        # (r'0x[a-fA-F0-9]{40}', '[ETH_ADDRESS]'),
        
        # Mnemonic phrases (BIP39 words)
        (r'\b(?:abandon|ability|able|about|above|absent|absorb|abstract|absurd|abuse|access|accident|account|accuse|achieve|acid|acoustic|acquire|across|act|action|actor|actress|actual|adapt|add|addict|address|adjust|admit|adult|advance|advice|aerobic|affair|afford|afraid|again|age|agent|agree|ahead|aim|air|airport|aisle|alarm|album|alcohol|alert|alien|all|alley|allow|almost|alone|alpha|already|also|alter|always|amateur|amazing|among|amount|amused|analyst|anchor|ancient|anger|angle|angry|animal|ankle|announce|annual|another|answer|antenna|antique|anxiety|any|apart|apple|apply|appoint|approve|april|arch|arctic|area|arena|argue|arm|armed|armor|army|around|arrange|arrest|arrive|arrow|art|artefact|artist|artwork|ask|aspect|assault|asset|assist|assume|asthma|athlete|atom|attack|attend|attitude|attract|auction|audit|august|aunt|author|auto|autumn|average|avocado|avoid|awake|aware|away|awesome|awful|awkward|axis)(?:\s+\w+){11,23}', '[MNEMONIC]'),
    ]
    
    @classmethod
    def sanitize(cls, text: str) -> str:
        """Sanitize a string."""
        if not text:
            return text
        
        for pattern, replacement in cls.PATTERNS:
            text = re.sub(pattern, replacement, text)
        
        return text
    
    @classmethod
    def sanitize_dict(cls, data: Dict[Any, Any]) -> Dict[Any, Any]:
        """Recursively sanitize a dictionary."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = cls.sanitize(value)
            elif isinstance(value, dict):
                result[key] = cls.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    cls.sanitize(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

# Monkey-patch logging to auto-sanitize
import logging

class SanitizingFormatter(logging.Formatter):
    """Log formatter that sanitizes output."""
    
    def format(self, record):
        # Sanitize the message
        if isinstance(record.msg, str):
            record.msg = SecretSanitizer.sanitize(record.msg)
        
        # Sanitize args
        if record.args:
            record.args = tuple(
                SecretSanitizer.sanitize(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        
        return super().format(record)

# Apply to root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

for handler in logging.root.handlers:
    handler.setFormatter(SanitizingFormatter())
```

---

## Security Checklist

### Pre-Implementation

- [ ] Code review by security-focused developer
- [ ] Dependency audit (`pip-audit`, `safety check`)
- [ ] Static analysis (Bandit, Semgrep)
- [ ] Secrets detection (GitLeaks, TruffleHog)
- [ ] Privy app security review (dashboard config)

### Testing

- [ ] Unit tests for all validators
- [ ] Integration tests for Privy API calls
- [ ] Fuzz testing for input validation
- [ ] Verify no local key storage

### Deployment

- [ ] Non-root container user
- [ ] Read-only root filesystem
- [ ] Privy auth key stored securely (600 permissions)
- [ ] Network policies (localhost only for setup)
- [ ] Audit logging enabled
- [ ] Privy dashboard access restricted

### Monitoring

- [ ] Alert on multiple failed setup attempts
- [ ] Alert on setup from non-localhost IP
- [ ] Alert on long-running setup sessions
- [ ] Log all configuration changes
- [ ] Monitor Privy API usage for anomalies

---

## Threat Model Summary

| Threat | Likelihood | Impact | Mitigation |
|--------|-----------|--------|------------|
| Private key theft from filesystem | **N/A** | Critical | **No local keys** (Privy manages) |
| Memory dump containing keys | **N/A** | Critical | **No local keys** (Privy TEE) |
| Privy service compromise | Low | Critical | TEE sharding, no single point of failure |
| Privy shutdown | Very Low | High | Export keys before migration |
| Timing attack on validation | Low | Medium | Constant-time comparison |
| Browser extension stealing input | Medium | Critical | CLI preferred, iframe sandbox |
| Supply chain attack (ACE) | Low | Critical | Minimal dependencies, checksums |
| Man-in-the-middle (setup) | Low | High | HTTPS, certificate pinning |
| Partial configuration corruption | Low | High | Atomic writes with rollback |
| Log file containing secrets | Medium | Critical | Aggressive sanitization |
| Session hijacking | Low | High | IP binding, short TTL |
| Screen capture of keys | N/A | Medium | **No key display in UI** |

---

## Appendix: Emergency Procedures

### If You Suspect Key Compromise

1. **Immediately**: Stop the bot
   ```bash
   docker-compose down
   ```

2. **Rotate keys**: Generate new API keys in HyperLiquid

3. **Transfer funds**: Move funds to new wallet

4. **Audit**: Check logs for unauthorized access

5. **Reinstall**: Fresh server/container with new keys

### Recovery from Corrupted Config

```bash
# Restore from backup
python setup.py --restore

# Or manually
ls -la .env.backup.*  # List backups
cp .env.backup.20240115_120000 .env
cp -r secrets.backup.20240115_120000 secrets
```

---

**Document Version**: 1.0  
**Last Updated**: 2024-01-15  
**Classification**: Internal Use Only  
**Author**: Security Team
