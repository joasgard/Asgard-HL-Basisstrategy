"""
Common enums and base types used across the system.
"""
from enum import Enum


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


class TransactionState(str, Enum):
    """Transaction state machine states."""
    IDLE = "idle"
    BUILDING = "building"
    BUILT = "built"
    SIGNING = "signing"
    SIGNED = "signed"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class Chain(str, Enum):
    """Supported blockchain networks."""
    SOLANA = "solana"
    ARBITRUM = "arbitrum"


class ChainStatus(str, Enum):
    """Health status of a chain."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OUTAGE = "outage"


class OpportunityStatus(str, Enum):
    """Status of an arbitrage opportunity."""
    DETECTED = "detected"
    VALIDATING = "validating"
    EXECUTING = "executing"
    ENTERED = "entered"
    EXITING = "exiting"
    CLOSED = "closed"
    REJECTED = "rejected"


class PositionSide(int, Enum):
    """Position side."""
    LONG = 0
    SHORT = 1


class ExitReason(str, Enum):
    """Reason for position exit."""
    FUNDING_FLIP = "funding_flip"
    HEALTH_FACTOR = "health_factor"
    MARGIN_FRACTION = "margin_fraction"
    PRICE_DEVIATION = "price_deviation"
    LST_DEPEG = "lst_depeg"
    MANUAL = "manual"
    CHAIN_OUTAGE = "chain_outage"
    STOP_LOSS = "stop_loss"
    TARGET_PROFIT = "target_profit"


# Type aliases
Address = str
TxSignature = str
IntentId = str
PositionId = str
