"""
Security utilities for the dashboard.
"""

import re
from typing import Optional


class SecretSanitizer:
    """Sanitizes sensitive data for logging."""
    
    SENSITIVE_PATTERNS = [
        # Private keys (Ethereum, Solana)
        (r'0x[a-fA-F0-9]{64}', '[PRIVATE_KEY]'),
        (r'[a-zA-Z0-9]{88}', '[SOLANA_KEY]'),
        
        # API keys (various lengths)
        (r'[a-zA-Z0-9]{32,64}', '[API_KEY]'),
        
        # Password patterns
        (r'pass(?:word|wd)?["\']?\s*[:=]\s*["\']?[^"\'\s]+', '[PASSWORD]'),
        (r'secret["\']?\s*[:=]\s*["\']?[^"\'\s]+', '[SECRET]'),
        
        # Privy credentials
        (r'privy[_-]?app[_-]?secret["\']?\s*[:=]\s*["\']?[^"\'\s]+', '[PRIVY_SECRET]'),
        (r'privy[_-]?auth[_-]?key["\']?\s*[:=]\s*["\']?[^"\'\s]+', '[PRIVY_AUTH_KEY]'),
        
        # Wallet addresses (mask middle)
        (r'(0x[a-fA-F0-9]{4})[a-fA-F0-9]{32,}(?:[a-fA-F0-9]{4})', r'\1...[ADDRESS]'),
    ]
    
    @classmethod
    def sanitize(cls, text: str) -> str:
        """
        Sanitize sensitive data from text.
        
        Args:
            text: Input text to sanitize
            
        Returns:
            Sanitized text safe for logging
        """
        if not text:
            return text
        
        sanitized = text
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    @classmethod
    def mask_address(cls, address: str, visible_chars: int = 4) -> str:
        """
        Mask a blockchain address for display.
        
        Args:
            address: Full address
            visible_chars: Number of chars to show at start and end
            
        Returns:
            Masked address like 0x1234...5678
        """
        if not address or len(address) <= visible_chars * 2 + 4:
            return address
        
        prefix = address[:visible_chars + 2] if address.startswith("0x") else address[:visible_chars]
        suffix = address[-visible_chars:]
        
        return f"{prefix}...{suffix}"
    
    @classmethod
    def truncate_log(cls, text: str, max_length: int = 1000) -> str:
        """
        Truncate text to max length for logging.
        
        Args:
            text: Input text
            max_length: Maximum length
            
        Returns:
            Truncated text
        """
        if not text or len(text) <= max_length:
            return text
        
        return text[:max_length] + f"...[truncated {len(text) - max_length} chars]"


def sanitize_for_audit(action: str, details: Optional[dict] = None) -> str:
    """
    Sanitize details for audit log.
    
    Args:
        action: Action name
        details: Action details dict
        
    Returns:
        Sanitized details string
    """
    if not details:
        return ""
    
    # Keys that should never be logged
    sensitive_keys = {
        "password", "password_confirm", "secret", "key", "api_key",
        "private_key", "seed", "mnemonic", "auth_key", "app_secret"
    }
    
    sanitized = {}
    for key, value in details.items():
        if key.lower() in sensitive_keys:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str):
            sanitized[key] = SecretSanitizer.sanitize(value)
        else:
            sanitized[key] = value
    
    import json
    return json.dumps(sanitized)
