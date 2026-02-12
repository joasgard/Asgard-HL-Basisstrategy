"""
Encryption module for Asgard Basis.

Implements a two-tier key hierarchy:
- KEK (Key Encryption Key): Derived from password via Argon2id, never persisted
- DEK (Data Encryption Key): Random 256-bit key, stored encrypted by KEK

Field-level encryption using AES-256-GCM with HMAC-SHA256 for tamper detection.
"""

import os
import secrets
import hashlib
import hmac
from typing import Optional, Tuple
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# Try to import Argon2, fallback to pure Python implementation if needed
try:
    from argon2.low_level import hash_secret_raw, Type
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False
    import warnings
    warnings.warn(
        "argon2-cffi not available. Using PBKDF2 fallback for development only. "
        "Install argon2-cffi for production: pip install argon2-cffi",
        RuntimeWarning
    )


# Constants
ARGON2_MEMORY_COST = 65536  # 64 MB
ARGON2_TIME_COST = 3  # iterations
ARGON2_PARALLELISM = 4  # lanes
ARGON2_HASH_LENGTH = 32  # 256 bits

AES_KEY_SIZE = 32  # 256 bits
AES_NONCE_SIZE = 12  # 96 bits for GCM
HMAC_SIZE = 32  # SHA256 output

SALT_SIZE = 32  # 256 bits
DEK_SIZE = 32  # 256 bits


class EncryptionError(Exception):
    """Base exception for encryption errors."""
    pass


class DecryptionError(EncryptionError):
    """Exception raised when decryption fails."""
    pass


class TamperDetectedError(DecryptionError):
    """Exception raised when HMAC verification fails (tampering detected)."""
    pass


@dataclass
class EncryptedField:
    """Represents an encrypted field with its components."""
    salt: bytes  # For KEK derivation when storing DEK
    nonce: bytes  # For AES-GCM
    ciphertext: bytes
    hmac: bytes  # HMAC-SHA256 of ciphertext
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes for storage: salt || nonce || ciphertext || hmac."""
        return self.salt + self.nonce + self.ciphertext + self.hmac
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedField":
        """Deserialize from bytes."""
        if len(data) < SALT_SIZE + AES_NONCE_SIZE + HMAC_SIZE:
            raise DecryptionError("Invalid encrypted field: too short")
        
        salt = data[:SALT_SIZE]
        nonce = data[SALT_SIZE:SALT_SIZE + AES_NONCE_SIZE]
        hmac_value = data[-HMAC_SIZE:]
        ciphertext = data[SALT_SIZE + AES_NONCE_SIZE:-HMAC_SIZE]
        
        return cls(
            salt=salt,
            nonce=nonce,
            ciphertext=ciphertext,
            hmac=hmac_value
        )


def derive_kek(password: str, salt: bytes) -> bytes:
    """
    Derive Key Encryption Key (KEK) from password using Argon2id.
    
    Args:
        password: User's plaintext password
        salt: Random salt (32 bytes)
        
    Returns:
        32-byte KEK for encrypting the DEK
        
    Raises:
        EncryptionError: If derivation fails
    """
    if len(salt) != SALT_SIZE:
        raise EncryptionError(f"Salt must be {SALT_SIZE} bytes, got {len(salt)}")
    
    password_bytes = password.encode('utf-8')
    
    if ARGON2_AVAILABLE:
        try:
            kek = hash_secret_raw(
                secret=password_bytes,
                salt=salt,
                time_cost=ARGON2_TIME_COST,
                memory_cost=ARGON2_MEMORY_COST,
                parallelism=ARGON2_PARALLELISM,
                hash_len=ARGON2_HASH_LENGTH,
                type=Type.ID
            )
            return kek
        except Exception as e:
            raise EncryptionError(f"Argon2id derivation failed: {e}")
    else:
        # Fallback to PBKDF2 for development only
        # WARNING: This is NOT suitable for production
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600000,  # OWASP recommended minimum
            backend=default_backend()
        )
        return kdf.derive(password_bytes)


def generate_dek() -> bytes:
    """
    Generate a new random Data Encryption Key (DEK).
    
    Returns:
        32-byte random DEK for field-level encryption
    """
    return secrets.token_bytes(DEK_SIZE)


def generate_salt() -> bytes:
    """
    Generate a new random salt for KEK derivation.
    
    Returns:
        32-byte random salt
    """
    return secrets.token_bytes(SALT_SIZE)


def generate_nonce() -> bytes:
    """
    Generate a new random nonce for AES-GCM.
    
    Returns:
        12-byte random nonce
    """
    return secrets.token_bytes(AES_NONCE_SIZE)


def _derive_hmac_key(dek: bytes) -> bytes:
    """
    Derive a separate HMAC key from DEK using HKDF-like derivation.
    Ensures key separation between encryption and authentication.
    """
    return hashlib.sha256(b"hmac-key:" + dek).digest()


def encrypt_field(plaintext: str, dek: bytes) -> bytes:
    """
    Encrypt a field using AES-256-GCM with HMAC-SHA256 tamper detection.
    
    Format: nonce (12B) || ciphertext || HMAC (32B)
    
    Args:
        plaintext: String to encrypt
        dek: 32-byte Data Encryption Key
        
    Returns:
        Encrypted bytes ready for storage
        
    Raises:
        EncryptionError: If encryption fails
    """
    if len(dek) != DEK_SIZE:
        raise EncryptionError(f"DEK must be {DEK_SIZE} bytes, got {len(dek)}")
    
    try:
        # Generate random nonce
        nonce = generate_nonce()
        
        # Encrypt with AES-GCM
        aesgcm = AESGCM(dek)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        
        # Compute HMAC of ciphertext for tamper detection
        hmac_key = _derive_hmac_key(dek)
        h = hmac.new(hmac_key, ciphertext, hashlib.sha256)
        field_hmac = h.digest()
        
        # Combine: nonce || ciphertext || hmac
        return nonce + ciphertext + field_hmac
        
    except Exception as e:
        raise EncryptionError(f"Field encryption failed: {e}")


def decrypt_field(encrypted: bytes, dek: bytes) -> str:
    """
    Decrypt a field and verify HMAC for tamper detection.
    
    Args:
        encrypted: Encrypted bytes (nonce || ciphertext || hmac)
        dek: 32-byte Data Encryption Key
        
    Returns:
        Decrypted plaintext string
        
    Raises:
        DecryptionError: If decryption fails
        TamperDetectedError: If HMAC verification fails (data tampered)
    """
    if len(dek) != DEK_SIZE:
        raise DecryptionError(f"DEK must be {DEK_SIZE} bytes, got {len(dek)}")
    
    if len(encrypted) < AES_NONCE_SIZE + HMAC_SIZE + 1:
        raise DecryptionError("Invalid encrypted field: too short")
    
    try:
        # Extract components
        nonce = encrypted[:AES_NONCE_SIZE]
        field_hmac = encrypted[-HMAC_SIZE:]
        ciphertext = encrypted[AES_NONCE_SIZE:-HMAC_SIZE]
        
        # Verify HMAC
        hmac_key = _derive_hmac_key(dek)
        h = hmac.new(hmac_key, ciphertext, hashlib.sha256)
        expected_hmac = h.digest()
        
        if not hmac.compare_digest(field_hmac, expected_hmac):
            raise TamperDetectedError("HMAC verification failed - data may have been tampered with")
        
        # Decrypt
        aesgcm = AESGCM(dek)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        
        return plaintext.decode('utf-8')
        
    except TamperDetectedError:
        raise
    except Exception as e:
        raise DecryptionError(f"Field decryption failed: {e}")


def encrypt_dek(dek: bytes, kek: bytes, salt: bytes) -> bytes:
    """
    Encrypt the DEK with the KEK for storage.
    
    Format: salt (32B) || nonce (12B) || ciphertext || HMAC (32B)
    
    Args:
        dek: 32-byte Data Encryption Key to encrypt
        kek: 32-byte Key Encryption Key derived from password
        salt: 32-byte salt used for KEK derivation
        
    Returns:
        Encrypted DEK ready for storage
    """
    if len(dek) != DEK_SIZE:
        raise EncryptionError(f"DEK must be {DEK_SIZE} bytes, got {len(dek)}")
    if len(kek) != AES_KEY_SIZE:
        raise EncryptionError(f"KEK must be {AES_KEY_SIZE} bytes, got {len(kek)}")
    if len(salt) != SALT_SIZE:
        raise EncryptionError(f"Salt must be {SALT_SIZE} bytes, got {len(salt)}")
    
    try:
        # Generate random nonce for DEK encryption
        nonce = generate_nonce()
        
        # Encrypt DEK with KEK using AES-GCM
        aesgcm = AESGCM(kek)
        ciphertext = aesgcm.encrypt(nonce, dek, None)
        
        # Compute HMAC
        hmac_key = _derive_hmac_key(kek)
        h = hmac.new(hmac_key, ciphertext, hashlib.sha256)
        dek_hmac = h.digest()
        
        # Combine: salt || nonce || ciphertext || hmac
        return salt + nonce + ciphertext + dek_hmac
        
    except Exception as e:
        raise EncryptionError(f"DEK encryption failed: {e}")


def decrypt_dek(encrypted_dek: bytes, kek: bytes) -> bytes:
    """
    Decrypt the DEK using the KEK.
    
    Args:
        encrypted_dek: Encrypted DEK (salt || nonce || ciphertext || hmac)
        kek: 32-byte Key Encryption Key derived from password
        
    Returns:
        32-byte decrypted DEK
        
    Raises:
        DecryptionError: If decryption fails
        TamperDetectedError: If HMAC verification fails
    """
    if len(kek) != AES_KEY_SIZE:
        raise DecryptionError(f"KEK must be {AES_KEY_SIZE} bytes, got {len(kek)}")
    
    if len(encrypted_dek) < SALT_SIZE + AES_NONCE_SIZE + HMAC_SIZE + 1:
        raise DecryptionError("Invalid encrypted DEK: too short")
    
    try:
        # Extract components (salt is included but already used to derive KEK)
        salt = encrypted_dek[:SALT_SIZE]
        nonce = encrypted_dek[SALT_SIZE:SALT_SIZE + AES_NONCE_SIZE]
        dek_hmac = encrypted_dek[-HMAC_SIZE:]
        ciphertext = encrypted_dek[SALT_SIZE + AES_NONCE_SIZE:-HMAC_SIZE]
        
        # Verify HMAC
        hmac_key = _derive_hmac_key(kek)
        h = hmac.new(hmac_key, ciphertext, hashlib.sha256)
        expected_hmac = h.digest()
        
        if not hmac.compare_digest(dek_hmac, expected_hmac):
            raise TamperDetectedError("DEK HMAC verification failed - data may have been tampered with")
        
        # Decrypt
        aesgcm = AESGCM(kek)
        dek = aesgcm.decrypt(nonce, ciphertext, None)
        
        if len(dek) != DEK_SIZE:
            raise DecryptionError(f"Decrypted DEK has wrong size: {len(dek)}")
        
        return dek
        
    except TamperDetectedError:
        raise
    except Exception as e:
        raise DecryptionError(f"DEK decryption failed: {e}")


def setup_encryption(password: str) -> Tuple[bytes, bytes]:
    """
    Initial setup: generate salt, derive KEK, generate and encrypt DEK.
    
    Args:
        password: User's password for KEK derivation
        
    Returns:
        Tuple of (encrypted_dek, salt)
        - encrypted_dek: Store this in database
        - salt: Store this in database (needed for KEK derivation on login)
    """
    salt = generate_salt()
    kek = derive_kek(password, salt)
    dek = generate_dek()
    encrypted_dek = encrypt_dek(dek, kek, salt)
    
    # Clear sensitive data from memory (best effort)
    import ctypes
    ctypes.memset(id(kek) + 20, 0, len(kek))
    ctypes.memset(id(dek) + 20, 0, len(dek))
    
    return encrypted_dek, salt


def unlock_encryption(password: str, encrypted_dek: bytes, salt: bytes) -> bytes:
    """
    Unlock encryption: derive KEK and decrypt DEK.
    
    Args:
        password: User's password
        encrypted_dek: Encrypted DEK from database
        salt: Salt from database
        
    Returns:
        Decrypted DEK for field-level encryption/decryption
        
    Raises:
        DecryptionError: If password is wrong or data is corrupted
    """
    kek = derive_kek(password, salt)
    try:
        dek = decrypt_dek(encrypted_dek, kek)
        return dek
    finally:
        # Clear KEK from memory (best effort)
        import ctypes
        ctypes.memset(id(kek) + 20, 0, len(kek))


class EncryptionManager:
    """
    Manages encryption state for a session.
    
    Holds the DEK in memory during an authenticated session.
    Never persists the KEK or password.
    """
    
    def __init__(self, dek: Optional[bytes] = None):
        self._dek: Optional[bytes] = dek
    
    @property
    def is_unlocked(self) -> bool:
        """Check if encryption is unlocked (DEK available)."""
        return self._dek is not None
    
    @property
    def dek(self) -> bytes:
        """Get the DEK (raises if not unlocked)."""
        if self._dek is None:
            raise EncryptionError("Encryption not unlocked - no DEK available")
        return self._dek
    
    def unlock(self, password: str, encrypted_dek: bytes, salt: bytes) -> None:
        """Unlock encryption with password."""
        self._dek = unlock_encryption(password, encrypted_dek, salt)
    
    def unlock_with_dek(self, encrypted_dek: bytes, kek: bytes) -> None:
        """Unlock encryption with encrypted DEK and KEK."""
        self._dek = decrypt_dek(encrypted_dek, kek)
    
    def lock(self) -> None:
        """Lock encryption by clearing DEK from memory."""
        if self._dek is not None:
            # Best effort to clear from memory
            import ctypes
            ctypes.memset(id(self._dek) + 20, 0, len(self._dek))
            self._dek = None
    
    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a field."""
        return encrypt_field(plaintext, self.dek)
    
    def decrypt(self, encrypted: bytes) -> str:
        """Decrypt a field."""
        return decrypt_field(encrypted, self.dek)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock()
        return False
