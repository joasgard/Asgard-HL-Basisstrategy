"""
Asset definitions and metadata for delta neutral arbitrage.
"""
from enum import Enum
from typing import Dict, List
from dataclasses import dataclass


class Asset(str, Enum):
    """Supported assets for long positions."""
    SOL = "SOL"
    JITOSOL = "jitoSOL"
    JUPSOL = "jupSOL"
    INF = "INF"


class Protocol(int, Enum):
    """Supported lending protocols on Asgard."""
    MARGINFI = 0
    KAMINO = 1
    SOLEND = 2
    DRIFT = 3


@dataclass(frozen=True)
class AssetMetadata:
    """Metadata for a supported asset."""
    symbol: str
    mint: str
    decimals: int
    is_lst: bool
    staking_apy: float  # Approximate staking yield for LSTs (0 for SOL)
    
    @property
    def is_native_sol(self) -> bool:
        return self.symbol == "SOL"


# Asset mints and metadata
ASSETS: Dict[Asset, AssetMetadata] = {
    Asset.SOL: AssetMetadata(
        symbol="SOL",
        mint="So11111111111111111111111111111111111111112",
        decimals=9,
        is_lst=False,
        staking_apy=0.0,
    ),
    Asset.JITOSOL: AssetMetadata(
        symbol="jitoSOL",
        mint="jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",
        decimals=9,
        is_lst=True,
        staking_apy=0.08,  # ~8% staking yield
    ),
    Asset.JUPSOL: AssetMetadata(
        symbol="jupSOL",
        mint="jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",
        decimals=9,
        is_lst=True,
        staking_apy=0.075,  # ~7.5% staking yield
    ),
    Asset.INF: AssetMetadata(
        symbol="INF",
        mint="5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X6TxNxsi",
        decimals=9,
        is_lst=True,
        staking_apy=0.07,  # ~7% staking yield (basket average)
    ),
}

# Protocol metadata for selection tie-breaking
PROTOCOL_PRIORITY: List[Protocol] = [
    Protocol.MARGINFI,
    Protocol.KAMINO,
    Protocol.SOLEND,
    Protocol.DRIFT,
]

# Perp asset on Hyperliquid
HYPERLIQUID_PERP = "SOL"


def get_asset_metadata(asset: Asset) -> AssetMetadata:
    """Get metadata for an asset."""
    return ASSETS[asset]


def get_mint(asset: Asset) -> str:
    """Get the SPL token mint for an asset."""
    return ASSETS[asset].mint


def get_all_assets() -> List[Asset]:
    """Get list of all supported assets."""
    return list(ASSETS.keys())


def get_lst_assets() -> List[Asset]:
    """Get list of LST assets only."""
    return [a for a in ASSETS.keys() if ASSETS[a].is_lst]
