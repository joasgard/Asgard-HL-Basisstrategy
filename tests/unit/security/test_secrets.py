"""
Tests for secrets loading functionality.
"""
import os
import tempfile
from pathlib import Path

import pytest

from shared.config.settings import load_secret, get_secret, SECRETS_DIR


class TestSecretLoading:
    """Tests for secret loading from files."""
    
    def test_load_secret_from_existing_file(self, tmp_path):
        """Test loading a secret from an existing file."""
        secret_file = tmp_path / "test_secret.txt"
        secret_file.write_text("my_secret_value\n")
        
        # Temporarily override SECRETS_DIR
        from shared.config import settings
        original_dir = settings.SECRETS_DIR
        settings.SECRETS_DIR = tmp_path
        
        try:
            result = load_secret("test_secret.txt")
            assert result == "my_secret_value"
        finally:
            settings.SECRETS_DIR = original_dir
    
    def test_load_secret_from_nonexistent_file(self, tmp_path):
        """Test loading from a non-existent file returns None."""
        from shared.config import settings
        original_dir = settings.SECRETS_DIR
        settings.SECRETS_DIR = tmp_path
        
        try:
            result = load_secret("nonexistent.txt")
            assert result is None
        finally:
            settings.SECRETS_DIR = original_dir
    
    def test_load_secret_strips_whitespace(self, tmp_path):
        """Test that loaded secrets have whitespace stripped."""
        secret_file = tmp_path / "test_secret.txt"
        secret_file.write_text("  secret_with_spaces  \n\n")
        
        from shared.config import settings
        original_dir = settings.SECRETS_DIR
        settings.SECRETS_DIR = tmp_path
        
        try:
            result = load_secret("test_secret.txt")
            assert result == "secret_with_spaces"
        finally:
            settings.SECRETS_DIR = original_dir


class TestGetSecretPriority:
    """Tests for get_secret priority logic."""
    
    def test_env_var_takes_priority(self, tmp_path, monkeypatch):
        """Test that environment variables take priority over files."""
        # Create secret file
        secret_file = tmp_path / "test_api_key.txt"
        secret_file.write_text("file_value")
        
        # Set env var
        monkeypatch.setenv("TEST_API_KEY", "env_value")
        
        from shared.config import settings
        original_dir = settings.SECRETS_DIR
        settings.SECRETS_DIR = tmp_path
        
        try:
            result = get_secret("TEST_API_KEY", "test_api_key.txt")
            assert result == "env_value"
        finally:
            settings.SECRETS_DIR = original_dir
    
    def test_file_used_when_no_env_var(self, tmp_path, monkeypatch):
        """Test that file is used when env var is not set."""
        # Ensure env var is not set
        monkeypatch.delenv("TEST_API_KEY", raising=False)
        
        # Create secret file
        secret_file = tmp_path / "test_api_key.txt"
        secret_file.write_text("file_value")
        
        from shared.config import settings
        original_dir = settings.SECRETS_DIR
        settings.SECRETS_DIR = tmp_path
        
        try:
            result = get_secret("TEST_API_KEY", "test_api_key.txt")
            assert result == "file_value"
        finally:
            settings.SECRETS_DIR = original_dir
    
    def test_none_when_no_env_or_file(self, tmp_path, monkeypatch):
        """Test that None is used when neither env var nor file exists."""
        monkeypatch.delenv("TEST_API_KEY", raising=False)
        
        from shared.config import settings
        original_dir = settings.SECRETS_DIR
        settings.SECRETS_DIR = tmp_path
        
        try:
            result = get_secret("TEST_API_KEY", "nonexistent.txt")
            assert result is None
        finally:
            settings.SECRETS_DIR = original_dir


class TestSecretsDirectoryStructure:
    """Tests for the secrets directory structure."""
    
    def test_secrets_directory_exists(self):
        """Test that the secrets directory exists."""
        assert SECRETS_DIR.exists(), f"Secrets directory not found: {SECRETS_DIR}"
    
    def test_readme_exists(self):
        """Test that secrets README exists."""
        readme_path = SECRETS_DIR / "README.md"
        assert readme_path.exists(), "secrets/README.md not found"
    
    def test_gitkeep_exists(self):
        """Test that .gitkeep exists to preserve directory in git."""
        gitkeep_path = SECRETS_DIR / ".gitkeep"
        assert gitkeep_path.exists(), "secrets/.gitkeep not found"
