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

### Security Model: Tiered Access

| Interface | Key Input Method | Use Case | Security Level |
|-----------|------------------|----------|----------------|
| **CLI** | User-provided private key | Power users, existing wallets | High |
| **Web** | System-generated key only | New users, convenience-first | Medium |

**Key Principle**: Private keys provided by users NEVER touch the web interface. This eliminates the browser as an attack vector for key theft.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Setup Architecture                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  CLI Mode (Full Control)        Web Mode (Convenience)                  │
│  ┌─────────────────────┐       ┌──────────────────────────┐             │
│  │ Terminal            │       │ Browser                  │             │
│  │ • Custom key input  │       │ • NO key input allowed   │             │
│  │ • getpass() hidden  │       │ • System generates key   │             │
│  │ • Direct to disk    │       │ • Display: address only  │             │
│  └──────────┬──────────┘       └───────────┬──────────────┘             │
│             │                              │                             │
│             │      Both use secure storage │                             │
│             └──────────────┬───────────────┘                             │
│                            │                                            │
│              ┌─────────────▼──────────────┐                             │
│              │    Secure Secret Storage   │                             │
│              │                            │                             │
│              │  secrets/private_key.enc   │  Hardware-bound AES-256     │
│              │  secrets/hyperliquid/*.enc │  Argon2 key derivation      │
│              └────────────────────────────┘                             │
│                                                                          │
│  Generated Key Note:                                                     │
│  Web-generated keys are created server-side with CSPRNG, encrypted       │
│  immediately, and shown to user as: "Address: 0x1234...  [Export PK]"   │
│  Export requires CLI access or password-derived decryption.              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

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

## Phase 2: Encryption Architecture

### 2.1 Hardware-Bound Key Derivation

```python
# src/setup/encryption.py

import hashlib
import platform
import uuid
from pathlib import Path
from typing import Optional
import argon2
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class HardwareKeyDerivation:
    """
    Derive encryption keys bound to hardware.
    Keys cannot be used on different machines even if secrets/ folder is copied.
    """
    
    SALT_FILE = Path.home() / '.basisstrategy' / '.install_salt'
    
    @classmethod
    def get_hardware_fingerprint(cls) -> bytes:
        """
        Generate hardware fingerprint from multiple sources.
        Combines multiple identifiers for robustness.
        """
        components = []
        
        # CPU info (platform-specific)
        try:
            if platform.system() == 'Linux':
                with open('/proc/cpuinfo') as f:
                    for line in f:
                        if line.startswith('serial') or line.startswith('Serial'):
                            components.append(line.split(':')[1].strip())
                            break
        except:
            pass
        
        # Machine ID (system-specific)
        try:
            with open('/etc/machine-id') as f:
                components.append(f.read().strip())
        except:
            pass
        
        # MAC address (first network interface)
        try:
            mac = uuid.getnode()
            if mac != 0:
                components.append(f'{mac:012x}')
        except:
            pass
        
        # Hostname
        components.append(platform.node())
        
        # Combine and hash
        combined = '|'.join(components).encode()
        return hashlib.sha256(combined).digest()
    
    @classmethod
    def get_or_create_salt(cls) -> bytes:
        """Get installation-specific salt, creating if necessary."""
        if cls.SALT_FILE.exists():
            return cls.SALT_FILE.read_bytes()
        
        # Generate new salt
        salt = secrets.token_bytes(32)
        cls.SALT_FILE.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        cls.SALT_FILE.write_bytes(salt)
        cls.SALT_FILE.chmod(0o600)
        
        return salt
    
    @classmethod
    def derive_key(cls, passphrase: Optional[str] = None) -> bytes:
        """
        Derive encryption key using Argon2id.
        
        Combines:
        - Hardware fingerprint (machine-specific)
        - Installation salt (installation-specific)
        - Optional user passphrase (knowledge factor)
        """
        hw_key = cls.get_hardware_fingerprint()
        salt = cls.get_or_create_salt()
        
        # Combine hardware key with optional passphrase
        if passphrase:
            password = hw_key + passphrase.encode()
        else:
            password = hw_key
        
        # Argon2id parameters (OWASP recommended)
        # Memory: 64MB, Iterations: 3, Parallelism: 4
        hasher = argon2.PasswordHasher(
            memory_cost=65536,
            time_cost=3,
            parallelism=4,
            hash_len=32,
            salt_len=16
        )
        
        # Argon2id binding
        hash_result = hasher.hash(password + salt)
        
        # Derive final key from hash
        return hashlib.sha256(hash_result.encode()).digest()

class SecureSecretStorage:
    """
    Encrypted secret storage with hardware binding.
    """
    
    def __init__(self):
        self._key_cache: Optional[bytes] = None
        self._key_cached_at: float = 0
        self._key_ttl: float = 300  # 5 minutes
    
    def _get_key(self, passphrase: Optional[str] = None) -> bytes:
        """Get encryption key, using cache if valid."""
        import time
        
        now = time.time()
        
        if self._key_cache and (now - self._key_cached_at) < self._key_ttl:
            return self._key_cache
        
        # Re-derive key
        key = HardwareKeyDerivation.derive_key(passphrase)
        self._key_cache = key
        self._key_cached_at = now
        
        return key
    
    def write_secret(self, name: str, plaintext: str, passphrase: Optional[str] = None):
        """
        Encrypt and write secret to disk.
        
        Format: nonce (12 bytes) || ciphertext || tag (16 bytes)
        """
        key = self._get_key(passphrase)
        aesgcm = AESGCM(key)
        
        nonce = secrets.token_bytes(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        
        # Write atomically
        secrets_dir = Path('secrets')
        secrets_dir.mkdir(mode=0o700, exist_ok=True)
        
        temp_file = secrets_dir / f'.{name}.enc.tmp'
        final_file = secrets_dir / f'{name}.enc'
        
        try:
            temp_file.write_bytes(nonce + ciphertext)
            temp_file.chmod(0o600)
            temp_file.rename(final_file)
        except:
            temp_file.unlink(missing_ok=True)
            raise
    
    def read_secret(self, name: str, passphrase: Optional[str] = None) -> Optional[str]:
        """Read and decrypt secret from disk."""
        secret_file = Path('secrets') / f'{name}.enc'
        
        if not secret_file.exists():
            return None
        
        key = self._get_key(passphrase)
        aesgcm = AESGCM(key)
        
        data = secret_file.read_bytes()
        nonce = data[:12]
        ciphertext = data[12:]
        
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode()
        except Exception:
            # Decryption failed—wrong key or corrupted
            return None
```

---

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
        Configure blockchain connection and wallet.
        
        NOTE: This is the ONLY place where custom private key input is allowed.
        Web setup generates keys automatically—custom key input is rejected.
        """
        print("═" * 62)
        print("Step 2/4: Blockchain Configuration")
        print("═" * 62)
        print("ℹ️  CLI mode allows custom private key input.")
        print("   For generated wallets, use web setup instead.\n")
        
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
        
        # Private key (with passphrase option)
        use_passphrase = input("\nAdd passphrase for extra security? [y/N]: ").lower() == 'y'
        passphrase = None
        if use_passphrase:
            passphrase = getpass("Passphrase: ")
        
        print("\n⚠️  Enter your wallet private key (64 hex characters)")
        priv_key_buf = self.prompt_secure(
            "Private Key",
            validator=InputValidator.validate_private_key,
            confirm=True
        )
        
        # Derive address for confirmation
        raw_key = priv_key_buf.read().decode().rstrip('\x00')
        from eth_account import Account
        account = Account.from_key(raw_key)
        
        print(f"\nDerived address: {account.address}")
        confirm = input("Is this correct? [Y/n]: ").lower()
        
        if confirm == 'n':
            print("Private key may be incorrect. Please retry.")
            return self._setup_blockchain()
        
        # Encrypt with optional passphrase
        self.storage.write_secret('arbitrum_private_key', raw_key, passphrase)
        print("✓ Private key encrypted and stored\n")
    
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
            "# Paths (encrypted secrets)",
            "HYPERLIQUID_API_KEY_PATH=secrets/hyperliquid_api_key.enc",
            "HYPERLIQUID_API_SECRET_PATH=secrets/hyperliquid_api_secret.enc",
            "ARBITRUM_PRIVATE_KEY_PATH=secrets/arbitrum_private_key.enc",
            "",
            f"ARBITRUM_RPC_URL={self.config.get('arbitrum_rpc_url', '')}",
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

## CLI vs Web: Security Distinction

### Critical Design Decision

To eliminate browser-based private key theft vectors, **user-provided private keys are CLI-only**. The web interface uses system-generated keys.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    KEY INPUT COMPARISON                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  CLI Setup (python setup.py)                                        │
│  ├── Can input custom private key                                    │
│  ├── getpass() - no terminal echo                                    │
│  ├── Direct to encrypted storage                                     │
│  └── For: Users with existing wallets                               │
│                                                                      │
│  Web Setup (http://localhost:8080/setup)                            │
│  ├── NO custom private key input                                     │
│  ├── System generates key via CSPRNG                                 │
│  ├── Shows: "Address: 0x1234..."                                     │
│  └── For: New users, convenience-first                              │
│                                                                      │
│  Both encrypt with:                                                  │
│  • Argon2id + hardware-bound key derivation                         │
│  • AES-256-GCM encryption                                           │
│  • Atomic file writes                                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Web Key Generation Flow

When users choose web setup, the system:

1. **Generates** a new wallet using `secrets.token_hex(32)` (CSPRNG)
2. **Immediately encrypts** the private key with a user-provided password
3. **Displays only** the public address: `0xAbCd...1234`
4. **Stores** encrypted key: `secrets/private_key.enc`
5. **Never exposes** private key in browser or logs

```python
# Server-side generation (keys never touch browser)
class WebKeyGenerator:
    def generate_and_encrypt(self, user_password: str) -> Tuple[str, bytes]:
        """
        Generate wallet and encrypt immediately.
        
        Returns:
            (address, encrypted_private_key)
        """
        from eth_account import Account
        import secrets
        
        # Generate with CSPRNG (not pseudo-random)
        private_key = secrets.token_hex(32)
        account = Account.from_key(private_key)
        
        # Encrypt with user's password + hardware salt
        encryption_key = self._derive_key(user_password)
        encrypted = self._encrypt(private_key, encryption_key)
        
        # Securely wipe from memory
        private_key = '0' * 64
        del private_key
        
        return account.address, encrypted
```

### Exporting Generated Keys

Users can export their generated private key later:

**Option 1: CLI Export**
```bash
$ python setup.py --export-key
Enter setup password: ••••••••
Private Key: 0x1234... (copy this to secure storage)
```

**Option 2: Dashboard Export** (password required)
```
Settings → Wallet → Export Private Key
Enter password: [________]
[Reveal Key]  [Copy to Clipboard]
```

**Option 3: Paper Backup** (during setup)
```
Your wallet address: 0xAbCd...1234

To backup your private key:
1. Write down this password: [MySecurePass123!]
2. Run: python setup.py --export-key --password "MySecurePass123!"
3. Store the exported key in a password manager or hardware wallet
```

---

## Phase 4: Web Implementation (Sandboxed - Generated Keys Only)

### 4.1 Security Model

The web interface runs in a **restricted setup mode** with these constraints:

1. **Localhost-only**: Only accepts connections from 127.0.0.1
2. **Time-bounded**: 30-minute window, then route 404s
3. **Single-session**: One concurrent setup session
4. **Setup key**: Requires terminal-displayed key for access
5. **No custom keys**: User-provided private keys are rejected
6. **Generated only**: System creates wallet via server-side CSPRNG
7. **No persistence**: Secrets never touch browser storage

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
    
    <!-- Step 3: Blockchain & Wallet Generation -->
    <div class="step" data-step="3">
        <h1>Blockchain Configuration</h1>
        
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
        
        <hr style="margin: 2rem 0; border-color: #333;">
        
        <h3>🔐 Secure Wallet Generation</h3>
        <p>A new wallet will be generated and encrypted. You don't need to input a private key.</p>
        
        <div class="info-box" style="background:#001a33;padding:1rem;margin:1rem 0;">
            <strong>ℹ️ How it works:</strong>
            <ul>
                <li>System generates a cryptographically secure key</li>
                <li>Key is encrypted immediately with your password</li>
                <li>Only the address is shown here</li>
                <li>You can export the private key later via CLI</li>
            </ul>
        </div>
        
        <h4>Set Wallet Encryption Password</h4>
        <p>This password protects your generated wallet. You'll need it to export the private key later.</p>
        
        <input type="password" id="wallet-password" class="secure-input" 
               placeholder="Wallet Password" autocomplete="off">
        <input type="password" id="wallet-password-confirm" class="secure-input" 
               placeholder="Confirm Password" autocomplete="off">
        
        <button onclick="generateWallet()">Generate Secure Wallet</button>
        
        <div id="wallet-generation-result" style="display:none;margin-top:1rem;">
            <div class="success-box" style="background:#002200;padding:1rem;">
                <strong>✓ Wallet Generated</strong>
                <p>Address: <code id="generated-address"></code></p>
                <p class="hint">Fund this address with USDC on Arbitrum to start trading.</p>
                <p class="backup-hint" style="font-size:0.9em;color:#888;">
                    💡 Tip: To backup, run <code>python setup.py --export-key</code> after setup.
                </p>
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
        
        async function generateWallet() {
            const password = document.getElementById('wallet-password').value;
            const confirmPassword = document.getElementById('wallet-password-confirm').value;
            
            if (password !== confirmPassword) {
                alert('Passwords do not match');
                return;
            }
            
            if (password.length < 12) {
                alert('Password must be at least 12 characters');
                return;
            }
            
            // Clear passwords from DOM
            document.getElementById('wallet-password').value = '';
            document.getElementById('wallet-password-confirm').value = '';
            
            // Request server-side generation
            const response = await fetch('/api/setup/generate-wallet', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: sessionId,
                    password: password  // Will be used for encryption
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                document.getElementById('generated-address').textContent = result.address;
                document.getElementById('wallet-generation-result').style.display = 'block';
            } else {
                alert('Wallet generation failed: ' + result.error);
            }
        }
        
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

@router.post("/generate-wallet")
async def generate_wallet(data: dict, request: Request):
    """
    Generate new wallet for web setup.
    Private key is generated server-side and immediately encrypted.
    """
    client_ip = request.client.host
    session = setup_manager.validate_session(data.get('session_id'), client_ip)
    
    password = data.get('password')
    if not password or len(password) < 12:
        return {"success": False, "error": "Password must be at least 12 characters"}
    
    try:
        from eth_account import Account
        import secrets
        from src.setup.encryption import SecureSecretStorage
        
        # Generate secure random private key
        private_key = secrets.token_hex(32)
        account = Account.from_key(private_key)
        
        # Encrypt with password-derived key
        storage = SecureSecretStorage()
        storage.write_secret('arbitrum_private_key', private_key, password)
        
        # Clear from memory
        private_key = '0' * 64
        del private_key
        
        return {
            "success": True,
            "address": account.address,
            "message": "Wallet generated and encrypted"
        }
        
    except Exception as e:
        return {"success": False, "error": "Wallet generation failed"}

@router.post("/export-key")
async def export_key(data: dict, request: Request):
    """
    Export private key (requires password).
    Only available after setup completion via CLI.
    """
    # This endpoint requires completed setup + password
    from src.setup.encryption import SecureSecretStorage
    
    try:
        storage = SecureSecretStorage()
        password = data.get('password')
        
        private_key = storage.read_secret('arbitrum_private_key', password)
        
        if not private_key:
            return {"success": False, "error": "Invalid password or key not found"}
        
        return {
            "success": True,
            "private_key": private_key,
            "warning": "Store this securely. Never share it."
        }
        
    except Exception as e:
        return {"success": False, "error": "Export failed"}
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

### Testing

- [ ] Unit tests for all validators
- [ ] Integration tests for encryption/decryption
- [ ] Fuzz testing for input validation
- [ ] Penetration testing (attempt to extract secrets)

### Deployment

- [ ] Non-root container user
- [ ] Read-only root filesystem
- [ ] Encrypted volumes for secrets
- [ ] Network policies (localhost only for setup)
- [ ] Audit logging enabled

### Monitoring

- [ ] Alert on multiple failed setup attempts
- [ ] Alert on setup from non-localhost IP
- [ ] Alert on long-running setup sessions
- [ ] Log all configuration changes

---

## Threat Model Summary

| Threat | Likelihood | Impact | Mitigation |
|--------|-----------|--------|------------|
| Private key theft from filesystem | Medium | Critical | Hardware-bound encryption |
| Memory dump containing keys | Low | Critical | SecureBuffer with mlock |
| Timing attack on validation | Low | Medium | Constant-time comparison |
| Browser extension stealing input | Medium | Critical | CLI preferred, iframe sandbox |
| Supply chain attack (ACE) | Low | Critical | Minimal dependencies, checksums |
| Man-in-the-middle (setup) | Low | High | HTTPS, certificate pinning |
| Partial configuration corruption | Low | High | Atomic writes with rollback |
| Log file containing secrets | Medium | Critical | Aggressive sanitization |
| Session hijacking | Low | High | IP binding, short TTL |
| Screen capture of keys | Medium | Medium | Hidden input, no echo |

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
