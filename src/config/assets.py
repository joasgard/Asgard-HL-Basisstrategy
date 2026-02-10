"""
Asset definitions and metadata for delta neutral arbitrage.
"""
from typing import Dict, List
from dataclasses import dataclass

# Import enums from models (source of truth)
from src.models.common import Asset, Protocol


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
