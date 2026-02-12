"""
Error codes and messages for Asgard Basis.

Format: XXX-NNNN
- XXX: Category (3 letters)
- NNNN: Sequential number (4 digits)
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional


class ErrorCategory(Enum):
    """Error categories."""
    GENERAL = "GEN"
    VALIDATION = "VAL"
    ASGARD = "ASG"
    HYPERLIQUID = "HLQ"
    POSITION = "POS"
    RISK = "RSK"
    WALLET = "WAL"
    NETWORK = "NET"
    AUTH = "AUT"


@dataclass(frozen=True)
class ErrorInfo:
    """Error information."""
    code: str
    message: str
    description: str
    category: ErrorCategory
    http_status: int = 400


class ErrorCode(Enum):
    """
    All error codes for Asgard Basis.
    
    Format: CATEGORY-NNNN
    """
    # General Errors (GEN)
    UNKNOWN_ERROR = ("GEN-0001", "An unexpected error occurred", 500)
    INTERNAL_ERROR = ("GEN-0002", "Internal server error", 500)
    NOT_IMPLEMENTED = ("GEN-0003", "Feature not yet implemented", 501)
    TIMEOUT = ("GEN-0004", "Request timed out", 504)
    
    # Validation Errors (VAL)
    INVALID_INPUT = ("VAL-0001", "Invalid input provided", 400)
    MISSING_FIELD = ("VAL-0002", "Required field is missing", 400)
    INVALID_LEVERAGE = ("VAL-0003", "Leverage must be between 1.1x and 4x", 400)
    INVALID_SIZE = ("VAL-0004", "Position size is invalid", 400)
    SIZE_TOO_SMALL = ("VAL-0005", "Position size below minimum", 400)
    SIZE_TOO_LARGE = ("VAL-0006", "Position size above maximum", 400)
    INVALID_ASSET = ("VAL-0007", "Unsupported asset", 400)
    
    # Asgard Errors (ASG)
    ASGARD_API_ERROR = ("ASG-0001", "Asgard API error", 502)
    ASGARD_INSUFFICIENT_LIQUIDITY = ("ASG-0002", "Insufficient liquidity on Asgard", 400)
    ASGARD_POSITION_FAILED = ("ASG-0003", "Failed to open Asgard position", 502)
    ASGARD_TX_BUILD_FAILED = ("ASG-0004", "Failed to build Asgard transaction", 502)
    ASGARD_TX_SIGN_FAILED = ("ASG-0005", "Failed to sign Asgard transaction", 500)
    ASGARD_TX_SUBMIT_FAILED = ("ASG-0006", "Failed to submit Asgard transaction", 502)
    ASGARD_TX_TIMEOUT = ("ASG-0007", "Asgard transaction timed out", 504)
    ASGARD_INSUFFICIENT_COLLATERAL = ("ASG-0008", "Insufficient collateral for Asgard position", 400)
    ASGARD_HEALTH_FACTOR_LOW = ("ASG-0009", "Asgard health factor too low", 400)
    
    # Hyperliquid Errors (HLQ)
    HYPERLIQUID_API_ERROR = ("HLQ-0001", "Hyperliquid API error", 502)
    HYPERLIQUID_POSITION_FAILED = ("HLQ-0002", "Failed to open Hyperliquid position", 502)
    HYPERLIQUID_INSUFFICIENT_MARGIN = ("HLQ-0003", "Insufficient margin on Hyperliquid", 400)
    HYPERLIQUID_LEVERAGE_FAILED = ("HLQ-0004", "Failed to set leverage on Hyperliquid", 502)
    HYPERLIQUID_ORDER_FAILED = ("HLQ-0005", "Failed to place Hyperliquid order", 502)
    HYPERLIQUID_RETRY_EXHAUSTED = ("HLQ-0006", "Hyperliquid retries exhausted", 502)
    HYPERLIQUID_POSITION_NOT_FOUND = ("HLQ-0007", "Hyperliquid position not found", 404)
    
    # Position Errors (POS)
    POSITION_NOT_FOUND = ("POS-0001", "Position not found", 404)
    POSITION_ALREADY_CLOSED = ("POS-0002", "Position already closed", 400)
    POSITION_CLOSE_FAILED = ("POS-0003", "Failed to close position", 502)
    POSITION_UNWIND_FAILED = ("POS-0004", "Failed to unwind position", 502)
    ASYMMETRIC_POSITION = ("POS-0005", "Asymmetric position detected", 500)
    
    # Risk Errors (RSK)
    OPPORTUNITY_REJECTED = ("RSK-0001", "Opportunity rejected by risk engine", 400)
    FUNDING_RATE_UNFAVORABLE = ("RSK-0002", "Funding rate is unfavorable", 400)
    PRICE_DEVIATION_HIGH = ("RSK-0003", "Price deviation between venues too high", 400)
    VOLATILITY_TOO_HIGH = ("RSK-0004", "Market volatility too high", 400)
    CIRCUIT_BREAKER_TRIGGERED = ("RSK-0005", "Circuit breaker triggered", 503)
    MAX_POSITIONS_REACHED = ("RSK-0006", "Maximum positions reached", 400)
    
    # Wallet Errors (WAL)
    INSUFFICIENT_SOL = ("WAL-0001", "Insufficient SOL for gas", 400)
    INSUFFICIENT_USDC = ("WAL-0002", "Insufficient USDC collateral", 400)
    INSUFFICIENT_ETH = ("WAL-0003", "Insufficient ETH for gas", 400)
    WALLET_NOT_CONNECTED = ("WAL-0004", "Wallet not connected", 401)
    
    # Network Errors (NET)
    NETWORK_ERROR = ("NET-0001", "Network error", 503)
    SOLANA_RPC_ERROR = ("NET-0002", "Solana RPC error", 503)
    ARBITRUM_RPC_ERROR = ("NET-0003", "Arbitrum RPC error", 503)
    RATE_LIMITED = ("NET-0004", "Rate limited by external API", 429)
    
    # Auth Errors (AUT)
    UNAUTHORIZED = ("AUT-0001", "Unauthorized", 401)
    FORBIDDEN = ("AUT-0002", "Forbidden", 403)
    INVALID_TOKEN = ("AUT-0003", "Invalid authentication token", 401)

    def __init__(self, code: str, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        # Parse category from code
        self.category = ErrorCategory(code.split("-")[0])


def get_error_info(code: ErrorCode) -> Dict[str, str]:
    """Get error information as dictionary."""
    return {
        "error_code": code.code,
        "message": code.message,
        "category": code.category.value,
        "http_status": str(code.http_status),
    }


# Detailed descriptions for documentation
ERROR_DESCRIPTIONS: Dict[str, str] = {
    # General
    "GEN-0001": "An unexpected error occurred. Please try again or contact support if the problem persists.",
    "GEN-0002": "An internal server error occurred. Our team has been notified.",
    "GEN-0003": "This feature is not yet implemented. Check our roadmap for updates.",
    "GEN-0004": "The request timed out. Please try again.",
    
    # Validation
    "VAL-0001": "The input provided is invalid. Check the field format and try again.",
    "VAL-0002": "A required field is missing from your request.",
    "VAL-0003": "Leverage must be between 1.1x and 4.0x. Adjust your leverage setting.",
    "VAL-0004": "The position size is invalid. Must be a positive number.",
    "VAL-0005": "Position size is below the minimum. Increase your position size.",
    "VAL-0006": "Position size is above your configured maximum. Reduce the size or update your settings.",
    "VAL-0007": "This asset is not supported. Currently only SOL is supported.",
    
    # Asgard
    "ASG-0001": "The Asgard API returned an error. This may be temporary.",
    "ASG-0002": "Insufficient liquidity available on Asgard for this position size.",
    "ASG-0003": "Failed to open position on Asgard. The transaction may have failed on-chain.",
    "ASG-0004": "Failed to build the Asgard transaction. Try again.",
    "ASG-0005": "Failed to sign the transaction with your wallet. Ensure your wallet is connected.",
    "ASG-0006": "Failed to submit the transaction to Solana. The network may be congested.",
    "ASG-0007": "The Asgard transaction timed out. Check your wallet for the transaction status.",
    "ASG-0008": "Insufficient collateral tokens in your wallet for this position.",
    "ASG-0009": "The health factor would be too low with these parameters. Reduce leverage.",
    
    # Hyperliquid
    "HLQ-0001": "The Hyperliquid API returned an error. This may be temporary.",
    "HLQ-0002": "Failed to open position on Hyperliquid. Check your margin balance.",
    "HLQ-0003": "Insufficient margin available on Hyperliquid. Deposit more USDC.",
    "HLQ-0004": "Failed to set leverage on Hyperliquid. Try again.",
    "HLQ-0005": "Failed to place order on Hyperliquid. The order may have been rejected.",
    "HLQ-0006": "All retry attempts exhausted for Hyperliquid operation. Contact support.",
    "HLQ-0007": "The Hyperliquid position was not found. It may have been closed.",
    
    # Position
    "POS-0001": "The position you requested was not found. Check the position ID.",
    "POS-0002": "This position has already been closed.",
    "POS-0003": "Failed to close the position. One or both legs may have failed.",
    "POS-0004": "Failed to unwind the position during error recovery. Contact support.",
    "POS-0005": "Position became asymmetric (one leg only). This is an error state.",
    
    # Risk
    "RSK-0001": "The opportunity was rejected by the risk engine. Check your settings.",
    "RSK-0002": "The funding rate is currently unfavorable for opening a position.",
    "RSK-0003": "Price deviation between venues exceeds your configured threshold.",
    "RSK-0004": "Market volatility is too high according to your settings.",
    "RSK-0005": "Circuit breaker triggered due to market conditions. Trading paused.",
    "RSK-0006": "Maximum number of positions reached. Close a position first.",
    
    # Wallet
    "WAL-0001": "Insufficient SOL in wallet for transaction fees. Add more SOL.",
    "WAL-0002": "Insufficient USDC in wallet for collateral. Deposit more USDC.",
    "WAL-0003": "Insufficient ETH in wallet for Arbitrum gas fees.",
    "WAL-0004": "No wallet connected. Connect your wallet to proceed.",
    
    # Network
    "NET-0001": "A network error occurred. Check your internet connection.",
    "NET-0002": "Solana RPC error. The network may be experiencing issues.",
    "NET-0003": "Arbitrum RPC error. The network may be experiencing issues.",
    "NET-0004": "Rate limited by external API. Please wait before trying again.",
    
    # Auth
    "AUT-0001": "You are not authorized. Please log in.",
    "AUT-0002": "You don't have permission to perform this action.",
    "AUT-0003": "Your session has expired. Please log in again.",
}


def get_error_description(code: str) -> str:
    """Get detailed description for an error code."""
    return ERROR_DESCRIPTIONS.get(code, "No additional information available for this error.")
