"""
Comprehensive tests for encryption module.

These tests verify:
- Key derivation (Argon2id and PBKDF2 fallback)
- DEK generation and management
- Field encryption/decryption with HMAC
- Tamper detection
- EncryptionManager functionality
"""
import pytest
import hashlib
import hmac
from unittest.mock import patch, MagicMock

from src.security.encryption import (
    # Exceptions
    EncryptionError,
    DecryptionError,
    TamperDetectedError,
    # Constants
    AES_KEY_SIZE,
    AES_NONCE_SIZE,
    HMAC_SIZE,
    SALT_SIZE,
    DEK_SIZE,
    # Classes
    EncryptedField,
    EncryptionManager,
    # Functions
    derive_kek,
    generate_dek,
    generate_salt,
    generate_nonce,
    _derive_hmac_key,
    encrypt_field,
    decrypt_field,
    encrypt_dek,
    decrypt_dek,
    setup_encryption,
    unlock_encryption,
    ARGON2_AVAILABLE,
)


class TestConstants:
    """Test that constants have expected values."""
    
    def test_aes_key_size(self):
        """AES key size should be 32 bytes (256 bits)."""
        assert AES_KEY_SIZE == 32
    
    def test_aes_nonce_size(self):
        """AES nonce size should be 12 bytes (96 bits)."""
        assert AES_NONCE_SIZE == 12
    
    def test_hmac_size(self):
        """HMAC size should be 32 bytes (SHA256 output)."""
        assert HMAC_SIZE == 32
    
    def test_salt_size(self):
        """Salt size should be 32 bytes."""
        assert SALT_SIZE == 32
    
    def test_dek_size(self):
        """DEK size should be 32 bytes."""
        assert DEK_SIZE == 32


class TestExceptions:
    """Test exception hierarchy."""
    
    def test_encryption_error_is_exception(self):
        """EncryptionError should be an Exception."""
        assert issubclass(EncryptionError, Exception)
    
    def test_decryption_error_is_encryption_error(self):
        """DecryptionError should be an EncryptionError."""
        assert issubclass(DecryptionError, EncryptionError)
    
    def test_tamper_error_is_decryption_error(self):
        """TamperDetectedError should be a DecryptionError."""
        assert issubclass(TamperDetectedError, DecryptionError)
    
    def test_error_messages(self):
        """Exceptions should support custom messages."""
        msg = "Custom error message"
        
        with pytest.raises(EncryptionError, match=msg):
            raise EncryptionError(msg)
        
        with pytest.raises(DecryptionError, match=msg):
            raise DecryptionError(msg)
        
        with pytest.raises(TamperDetectedError, match=msg):
            raise TamperDetectedError(msg)


class TestGenerateFunctions:
    """Test random generation functions."""
    
    def test_generate_dek_length(self):
        """DEK should be 32 bytes."""
        dek = generate_dek()
        assert len(dek) == DEK_SIZE
    
    def test_generate_dek_randomness(self):
        """DEK should be random (different each call)."""
        dek1 = generate_dek()
        dek2 = generate_dek()
        assert dek1 != dek2
    
    def test_generate_salt_length(self):
        """Salt should be 32 bytes."""
        salt = generate_salt()
        assert len(salt) == SALT_SIZE
    
    def test_generate_salt_randomness(self):
        """Salt should be random (different each call)."""
        salt1 = generate_salt()
        salt2 = generate_salt()
        assert salt1 != salt2
    
    def test_generate_nonce_length(self):
        """Nonce should be 12 bytes."""
        nonce = generate_nonce()
        assert len(nonce) == AES_NONCE_SIZE
    
    def test_generate_nonce_randomness(self):
        """Nonce should be random (different each call)."""
        nonce1 = generate_nonce()
        nonce2 = generate_nonce()
        assert nonce1 != nonce2


class TestDeriveHmacKey:
    """Test HMAC key derivation."""
    
    def test_derive_hmac_key_length(self):
        """HMAC key should be derived from DEK."""
        dek = generate_dek()
        hmac_key = _derive_hmac_key(dek)
        assert len(hmac_key) == 32
    
    def test_derive_hmac_key_consistency(self):
        """Same DEK should produce same HMAC key."""
        dek = generate_dek()
        hmac_key1 = _derive_hmac_key(dek)
        hmac_key2 = _derive_hmac_key(dek)
        assert hmac_key1 == hmac_key2
    
    def test_derive_hmac_key_different_deks(self):
        """Different DEKs should produce different HMAC keys."""
        dek1 = generate_dek()
        dek2 = generate_dek()
        hmac_key1 = _derive_hmac_key(dek1)
        hmac_key2 = _derive_hmac_key(dek2)
        assert hmac_key1 != hmac_key2


class TestDeriveKek:
    """Test Key Encryption Key derivation."""
    
    def test_derive_kek_with_valid_inputs(self):
        """Should derive 32-byte KEK with valid inputs."""
        password = "test_password"
        salt = generate_salt()
        kek = derive_kek(password, salt)
        
        assert len(kek) == AES_KEY_SIZE
        assert isinstance(kek, bytes)
    
    def test_derive_kek_deterministic(self):
        """Same password and salt should produce same KEK."""
        password = "test_password"
        salt = generate_salt()
        
        kek1 = derive_kek(password, salt)
        kek2 = derive_kek(password, salt)
        
        assert kek1 == kek2
    
    def test_derive_kek_different_passwords(self):
        """Different passwords should produce different KEKs."""
        salt = generate_salt()
        
        kek1 = derive_kek("password1", salt)
        kek2 = derive_kek("password2", salt)
        
        assert kek1 != kek2
    
    def test_derive_kek_different_salts(self):
        """Different salts should produce different KEKs."""
        password = "test_password"
        
        kek1 = derive_kek(password, generate_salt())
        kek2 = derive_kek(password, generate_salt())
        
        assert kek1 != kek2
    
    def test_derive_kek_invalid_salt_size(self):
        """Should raise EncryptionError for invalid salt size."""
        password = "test_password"
        
        with pytest.raises(EncryptionError, match="Salt must be"):
            derive_kek(password, b"short_salt")
        
        with pytest.raises(EncryptionError, match="Salt must be"):
            derive_kek(password, b"a" * 100)  # Too long
    
    def test_derive_kek_empty_password(self):
        """Should handle empty password."""
        salt = generate_salt()
        kek = derive_kek("", salt)
        
        assert len(kek) == AES_KEY_SIZE


class TestFieldEncryption:
    """Test field-level encryption/decryption."""
    
    def test_encrypt_field_basic(self):
        """Should encrypt plaintext successfully."""
        plaintext = "secret data"
        dek = generate_dek()
        
        encrypted = encrypt_field(plaintext, dek)
        
        # Should be: nonce (12) + ciphertext + hmac (32)
        assert len(encrypted) >= AES_NONCE_SIZE + HMAC_SIZE + 1
    
    def test_encrypt_field_invalid_dek_size(self):
        """Should raise EncryptionError for invalid DEK size."""
        with pytest.raises(EncryptionError, match="DEK must be"):
            encrypt_field("data", b"short")
        
        with pytest.raises(EncryptionError, match="DEK must be"):
            encrypt_field("data", b"a" * 100)
    
    def test_decrypt_field_success(self):
        """Should decrypt encrypted field successfully."""
        plaintext = "secret data"
        dek = generate_dek()
        
        encrypted = encrypt_field(plaintext, dek)
        decrypted = decrypt_field(encrypted, dek)
        
        assert decrypted == plaintext
    
    def test_decrypt_field_empty_string(self):
        """Should handle empty string encryption/decryption."""
        plaintext = ""
        dek = generate_dek()
        
        encrypted = encrypt_field(plaintext, dek)
        decrypted = decrypt_field(encrypted, dek)
        
        assert decrypted == plaintext
    
    def test_decrypt_field_unicode(self):
        """Should handle unicode characters."""
        plaintext = "Hello 世界 🌍 émojis"
        dek = generate_dek()
        
        encrypted = encrypt_field(plaintext, dek)
        decrypted = decrypt_field(encrypted, dek)
        
        assert decrypted == plaintext
    
    def test_decrypt_field_large_data(self):
        """Should handle large data."""
        plaintext = "x" * 10000
        dek = generate_dek()
        
        encrypted = encrypt_field(plaintext, dek)
        decrypted = decrypt_field(encrypted, dek)
        
        assert decrypted == plaintext
    
    def test_decrypt_field_wrong_dek(self):
        """Should raise DecryptionError with wrong DEK."""
        plaintext = "secret"
        dek1 = generate_dek()
        dek2 = generate_dek()
        
        encrypted = encrypt_field(plaintext, dek1)
        
        # HMAC verification should fail with wrong DEK
        with pytest.raises(TamperDetectedError):
            decrypt_field(encrypted, dek2)
    
    def test_decrypt_field_invalid_dek_size(self):
        """Should raise DecryptionError for invalid DEK size."""
        with pytest.raises(DecryptionError, match="DEK must be"):
            decrypt_field(b"encrypted", b"short")
    
    def test_decrypt_field_too_short(self):
        """Should raise DecryptionError for too short data."""
        dek = generate_dek()
        
        with pytest.raises(DecryptionError, match="too short"):
            decrypt_field(b"short", dek)
    
    def test_decrypt_field_tampered_hmac(self):
        """Should detect tampered HMAC."""
        plaintext = "secret"
        dek = generate_dek()
        
        encrypted = bytearray(encrypt_field(plaintext, dek))
        # Tamper with last byte (HMAC)
        encrypted[-1] ^= 0xFF
        
        with pytest.raises(TamperDetectedError, match="tampered"):
            decrypt_field(bytes(encrypted), dek)
    
    def test_decrypt_field_tampered_ciphertext(self):
        """Should detect tampered ciphertext."""
        plaintext = "secret"
        dek = generate_dek()
        
        encrypted = bytearray(encrypt_field(plaintext, dek))
        # Tamper with ciphertext (after nonce, before HMAC)
        encrypted[AES_NONCE_SIZE] ^= 0xFF
        
        with pytest.raises(TamperDetectedError, match="tampered"):
            decrypt_field(bytes(encrypted), dek)
    
    def test_decrypt_field_tampered_nonce(self):
        """Should fail with tampered nonce (AES-GCM will fail)."""
        plaintext = "secret"
        dek = generate_dek()
        
        encrypted = bytearray(encrypt_field(plaintext, dek))
        # Tamper with nonce (first byte)
        encrypted[0] ^= 0xFF
        
        # Either tamper detection or decryption error
        with pytest.raises((TamperDetectedError, DecryptionError)):
            decrypt_field(bytes(encrypted), dek)


class TestDekEncryption:
    """Test DEK encryption with KEK."""
    
    def test_encrypt_dek_success(self):
        """Should encrypt DEK successfully."""
        dek = generate_dek()
        kek = generate_dek()  # Use random bytes as KEK
        salt = generate_salt()
        
        encrypted = encrypt_dek(dek, kek, salt)
        
        # Should be: salt (32) + nonce (12) + ciphertext + hmac (32)
        assert len(encrypted) >= SALT_SIZE + AES_NONCE_SIZE + HMAC_SIZE + 1
    
    def test_encrypt_dek_invalid_sizes(self):
        """Should raise EncryptionError for invalid sizes."""
        dek = generate_dek()
        kek = generate_dek()
        salt = generate_salt()
        
        with pytest.raises(EncryptionError, match="DEK must be"):
            encrypt_dek(b"short", kek, salt)
        
        with pytest.raises(EncryptionError, match="KEK must be"):
            encrypt_dek(dek, b"short", salt)
        
        with pytest.raises(EncryptionError, match="Salt must be"):
            encrypt_dek(dek, kek, b"short")
    
    def test_decrypt_dek_success(self):
        """Should decrypt encrypted DEK successfully."""
        dek = generate_dek()
        kek = generate_dek()
        salt = generate_salt()
        
        encrypted = encrypt_dek(dek, kek, salt)
        decrypted = decrypt_dek(encrypted, kek)
        
        assert decrypted == dek
    
    def test_decrypt_dek_wrong_kek(self):
        """Should raise TamperDetectedError with wrong KEK."""
        dek = generate_dek()
        kek1 = generate_dek()
        kek2 = generate_dek()
        salt = generate_salt()
        
        encrypted = encrypt_dek(dek, kek1, salt)
        
        with pytest.raises(TamperDetectedError):
            decrypt_dek(encrypted, kek2)
    
    def test_decrypt_dek_invalid_kek_size(self):
        """Should raise DecryptionError for invalid KEK size."""
        with pytest.raises(DecryptionError, match="KEK must be"):
            decrypt_dek(b"encrypted", b"short")
    
    def test_decrypt_dek_too_short(self):
        """Should raise DecryptionError for too short data."""
        kek = generate_dek()
        
        with pytest.raises(DecryptionError, match="too short"):
            decrypt_dek(b"short", kek)
    
    def test_decrypt_dek_tampered(self):
        """Should detect tampered encrypted DEK."""
        dek = generate_dek()
        kek = generate_dek()
        salt = generate_salt()
        
        encrypted = bytearray(encrypt_dek(dek, kek, salt))
        # Tamper with ciphertext
        encrypted[SALT_SIZE + AES_NONCE_SIZE] ^= 0xFF
        
        with pytest.raises(TamperDetectedError):
            decrypt_dek(bytes(encrypted), kek)


class TestSetupAndUnlock:
    """Test high-level setup and unlock functions."""
    
    def test_setup_encryption(self):
        """Should setup encryption and return encrypted DEK and salt."""
        password = "my_secure_password"
        
        encrypted_dek, salt = setup_encryption(password)
        
        assert len(salt) == SALT_SIZE
        assert len(encrypted_dek) >= SALT_SIZE + AES_NONCE_SIZE + HMAC_SIZE + 1
    
    def test_unlock_encryption_success(self):
        """Should unlock encryption with correct password."""
        password = "my_secure_password"
        
        encrypted_dek, salt = setup_encryption(password)
        dek = unlock_encryption(password, encrypted_dek, salt)
        
        assert len(dek) == DEK_SIZE
    
    def test_unlock_encryption_wrong_password(self):
        """Should raise DecryptionError with wrong password."""
        password = "correct_password"
        wrong_password = "wrong_password"
        
        encrypted_dek, salt = setup_encryption(password)
        
        with pytest.raises(TamperDetectedError):
            unlock_encryption(wrong_password, encrypted_dek, salt)
    
    def test_setup_unlock_roundtrip(self):
        """Should be able to encrypt/decrypt after setup/unlock."""
        password = "my_secure_password"
        plaintext = "sensitive data"
        
        # Setup
        encrypted_dek, salt = setup_encryption(password)
        
        # Unlock
        dek = unlock_encryption(password, encrypted_dek, salt)
        
        # Encrypt some data
        encrypted_data = encrypt_field(plaintext, dek)
        
        # Decrypt
        decrypted = decrypt_field(encrypted_data, dek)
        
        assert decrypted == plaintext


class TestEncryptedField:
    """Test EncryptedField dataclass."""
    
    def test_encrypted_field_creation(self):
        """Should create EncryptedField with components."""
        salt = b"s" * SALT_SIZE
        nonce = b"n" * AES_NONCE_SIZE
        ciphertext = b"cipher"
        hmac_val = b"h" * HMAC_SIZE
        
        field = EncryptedField(
            salt=salt,
            nonce=nonce,
            ciphertext=ciphertext,
            hmac=hmac_val
        )
        
        assert field.salt == salt
        assert field.nonce == nonce
        assert field.ciphertext == ciphertext
        assert field.hmac == hmac_val
    
    def test_encrypted_field_to_bytes(self):
        """Should serialize to bytes correctly."""
        salt = b"s" * SALT_SIZE
        nonce = b"n" * AES_NONCE_SIZE
        ciphertext = b"cipher"
        hmac_val = b"h" * HMAC_SIZE
        
        field = EncryptedField(salt, nonce, ciphertext, hmac_val)
        data = field.to_bytes()
        
        expected = salt + nonce + ciphertext + hmac_val
        assert data == expected
    
    def test_encrypted_field_from_bytes(self):
        """Should deserialize from bytes correctly."""
        salt = b"s" * SALT_SIZE
        nonce = b"n" * AES_NONCE_SIZE
        ciphertext = b"cipher"
        hmac_val = b"h" * HMAC_SIZE
        
        data = salt + nonce + ciphertext + hmac_val
        field = EncryptedField.from_bytes(data)
        
        assert field.salt == salt
        assert field.nonce == nonce
        assert field.ciphertext == ciphertext
        assert field.hmac == hmac_val
    
    def test_encrypted_field_from_bytes_too_short(self):
        """Should raise DecryptionError for too short data."""
        with pytest.raises(DecryptionError, match="too short"):
            EncryptedField.from_bytes(b"short")
    
    def test_encrypted_field_roundtrip(self):
        """Should roundtrip through to_bytes/from_bytes."""
        salt = generate_salt()
        nonce = generate_nonce()
        ciphertext = b"encrypted data here"
        hmac_val = hashlib.sha256(ciphertext).digest()
        
        field1 = EncryptedField(salt, nonce, ciphertext, hmac_val)
        data = field1.to_bytes()
        field2 = EncryptedField.from_bytes(data)
        
        assert field2.salt == field1.salt
        assert field2.nonce == field1.nonce
        assert field2.ciphertext == field1.ciphertext
        assert field2.hmac == field1.hmac


class TestEncryptionManager:
    """Test EncryptionManager class."""
    
    def test_init_without_dek(self):
        """Should initialize without DEK (locked state)."""
        manager = EncryptionManager()
        
        assert not manager.is_unlocked
        assert manager._dek is None
    
    def test_init_with_dek(self):
        """Should initialize with DEK (unlocked state)."""
        dek = generate_dek()
        manager = EncryptionManager(dek)
        
        assert manager.is_unlocked
        assert manager.dek == dek
    
    def test_dek_property_raises_when_locked(self):
        """Should raise EncryptionError when accessing DEK while locked."""
        manager = EncryptionManager()
        
        with pytest.raises(EncryptionError, match="not unlocked"):
            _ = manager.dek
    
    def test_unlock_with_password(self):
        """Should unlock with password, encrypted_dek, and salt."""
        password = "my_password"
        encrypted_dek, salt = setup_encryption(password)
        
        manager = EncryptionManager()
        manager.unlock(password, encrypted_dek, salt)
        
        assert manager.is_unlocked
        assert len(manager.dek) == DEK_SIZE
    
    def test_unlock_with_kek(self):
        """Should unlock with encrypted DEK and KEK."""
        dek = generate_dek()
        kek = generate_dek()
        salt = generate_salt()
        
        encrypted_dek = encrypt_dek(dek, kek, salt)
        
        manager = EncryptionManager()
        manager.unlock_with_dek(encrypted_dek, kek)
        
        assert manager.is_unlocked
        assert manager.dek == dek
    
    def test_lock(self):
        """Should lock and clear DEK."""
        dek = generate_dek()
        manager = EncryptionManager(dek)
        
        assert manager.is_unlocked
        
        manager.lock()
        
        assert not manager.is_unlocked
        assert manager._dek is None
    
    def test_encrypt_decrypt(self):
        """Should encrypt and decrypt data."""
        dek = generate_dek()
        manager = EncryptionManager(dek)
        plaintext = "secret message"
        
        encrypted = manager.encrypt(plaintext)
        decrypted = manager.decrypt(encrypted)
        
        assert decrypted == plaintext
    
    def test_encrypt_raises_when_locked(self):
        """Should raise when encrypting while locked."""
        manager = EncryptionManager()
        
        with pytest.raises(EncryptionError, match="not unlocked"):
            manager.encrypt("data")
    
    def test_decrypt_raises_when_locked(self):
        """Should raise when decrypting while locked."""
        manager = EncryptionManager()
        
        with pytest.raises(EncryptionError, match="not unlocked"):
            manager.decrypt(b"encrypted")
    
    def test_context_manager(self):
        """Should work as context manager and lock on exit."""
        dek = generate_dek()
        
        with EncryptionManager(dek) as manager:
            assert manager.is_unlocked
            encrypted = manager.encrypt("test")
            decrypted = manager.decrypt(encrypted)
            assert decrypted == "test"
        
        # After exiting context, should be locked
        assert not manager.is_unlocked
    
    def test_context_manager_with_exception(self):
        """Should lock even when exception occurs."""
        dek = generate_dek()
        manager = EncryptionManager(dek)
        
        try:
            with manager:
                assert manager.is_unlocked
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Should still be locked after exception
        assert not manager.is_unlocked


class TestArgon2Fallback:
    """Test PBKDF2 fallback when Argon2 unavailable."""
    
    @pytest.mark.skipif(ARGON2_AVAILABLE, reason="Only test when Argon2 available (mock unavailable)")
    def test_pbkdf2_fallback_produces_valid_key(self):
        """PBKDF2 should produce valid 32-byte key."""
        password = "test_password"
        salt = generate_salt()
        
        kek = derive_kek(password, salt)
        
        assert len(kek) == AES_KEY_SIZE
    
    @pytest.mark.skipif(not ARGON2_AVAILABLE, reason="Only test when Argon2 available")
    def test_argon2_produces_different_key_than_pbkdf2(self):
        """Argon2 and PBKDF2 should produce different keys (different algorithms)."""
        # This test verifies that when we mock Argon2 unavailable,
        # we get different results than with Argon2
        password = "test_password"
        salt = generate_salt()
        
        # Get Argon2 result
        kek_argon2 = derive_kek(password, salt)
        
        # Mock Argon2 as unavailable and get PBKDF2 result
        with patch('src.security.encryption.ARGON2_AVAILABLE', False):
            with patch('src.security.encryption.hash_secret_raw', side_effect=ImportError):
                kek_pbkdf2 = derive_kek(password, salt)
        
        # Different algorithms should produce different keys
        assert kek_argon2 != kek_pbkdf2
