"""
Test that project structure is correctly set up.
"""
import os
from pathlib import Path

import pytest


BASE_DIR = Path(__file__).parent.parent.parent


def test_directory_structure():
    """Verify all required directories exist."""
    required_dirs = [
        "src",
        "src/config",
        "src/core",
        "src/venues",
        "src/venues/asgard",
        "src/venues/hyperliquid",
        "src/chain",
        "src/state",
        "src/security",
        "src/models",
        "src/utils",
        "tests/unit",
        "tests/integration",
        "tests/fixtures",
        "docker",
        "scripts",
    ]
    
    for dir_path in required_dirs:
        full_path = BASE_DIR / dir_path
        assert full_path.exists(), f"Missing directory: {dir_path}"
        assert full_path.is_dir(), f"Not a directory: {dir_path}"


def test_init_files():
    """Verify __init__.py files exist in Python packages."""
    packages = [
        "src",
        "src/config",
        "src/core",
        "src/venues",
        "src/venues/asgard",
        "src/venues/hyperliquid",
        "src/chain",
        "src/state",
        "src/security",
        "src/models",
        "src/utils",
    ]
    
    for pkg in packages:
        init_file = BASE_DIR / pkg / "__init__.py"
        assert init_file.exists(), f"Missing __init__.py in {pkg}"


def test_config_files_exist():
    """Verify configuration files exist."""
    config_files = [
        "requirements.txt",
        ".env.example",
        "src/config/risk.yaml",
    ]
    
    for file_path in config_files:
        full_path = BASE_DIR / file_path
        assert full_path.exists(), f"Missing config file: {file_path}"


def test_imports_work():
    """Verify core modules can be imported."""
    # These should not raise ImportError
    from src.config import assets, settings
    from src.utils import logger, retry
    
    assert assets is not None
    assert settings is not None
    assert logger is not None
    assert retry is not None


def test_asset_definitions():
    """Verify asset definitions are loaded correctly."""
    from src.config.assets import Asset, ASSETS
    
    # Check all assets are defined
    assets = list(ASSETS.keys())
    assert len(assets) == 4
    
    # Check specific assets
    assert Asset.SOL in assets
    assert Asset.JITOSOL in assets
    assert Asset.JUPSOL in assets
    assert Asset.INF in assets
    
    # Check mint addresses are correct
    assert ASSETS[Asset.SOL].mint == "So11111111111111111111111111111111111111112"
    assert ASSETS[Asset.JITOSOL].is_lst is True
    assert ASSETS[Asset.SOL].is_lst is False
