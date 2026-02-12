"""
Exception classes for Asgard Basis.
"""

from typing import Optional, Dict, Any


class AsgardError(Exception):
    """Base exception for all Asgard-related errors."""
    
    def __init__(
        self,
        code: str,
        message: str,
        description: Optional[str] = None,
        http_status: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.description = description or message
        self.http_status = http_status
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API response."""
        return {
            "error_code": self.code,
            "message": self.message,
            "description": self.description,
            "http_status": self.http_status,
            "details": self.details,
        }


class ValidationError(AsgardError):
    """Input validation error."""
    
    def __init__(
        self,
        code: str = "VAL-0001",
        message: str = "Invalid input provided",
        description: Optional[str] = None,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            description=description,
            http_status=400,
            details={"field": field, **(details or {})},
        )


class InsufficientFundsError(AsgardError):
    """Insufficient funds for operation."""
    
    def __init__(
        self,
        code: str = "WAL-0002",
        message: str = "Insufficient funds",
        description: Optional[str] = None,
        required: Optional[float] = None,
        available: Optional[float] = None,
        asset: Optional[str] = None,
    ):
        details = {}
        if required is not None:
            details["required"] = required
        if available is not None:
            details["available"] = available
        if asset is not None:
            details["asset"] = asset
            
        super().__init__(
            code=code,
            message=message,
            description=description,
            http_status=400,
            details=details,
        )


class HyperliquidError(AsgardError):
    """Hyperliquid-specific error."""
    
    def __init__(
        self,
        code: str = "HLQ-0001",
        message: str = "Hyperliquid API error",
        description: Optional[str] = None,
        hl_status: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        error_details = details or {}
        if hl_status:
            error_details["hyperliquid_status"] = hl_status
            
        super().__init__(
            code=code,
            message=message,
            description=description,
            http_status=502,
            details=error_details,
        )


class PositionError(AsgardError):
    """Position operation error."""
    
    def __init__(
        self,
        code: str = "POS-0001",
        message: str = "Position error",
        description: Optional[str] = None,
        position_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        error_details = details or {}
        if position_id:
            error_details["position_id"] = position_id
            
        super().__init__(
            code=code,
            message=message,
            description=description,
            http_status=400,
            details=error_details,
        )


class RiskError(AsgardError):
    """Risk check failure."""
    
    def __init__(
        self,
        code: str = "RSK-0001",
        message: str = "Risk check failed",
        description: Optional[str] = None,
        check_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        error_details = details or {}
        if check_name:
            error_details["check"] = check_name
            
        super().__init__(
            code=code,
            message=message,
            description=description,
            http_status=400,
            details=error_details,
        )


class NetworkError(AsgardError):
    """Network/RPC error."""
    
    def __init__(
        self,
        code: str = "NET-0001",
        message: str = "Network error",
        description: Optional[str] = None,
        rpc_url: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        error_details = details or {}
        if rpc_url:
            error_details["rpc_url"] = rpc_url
            
        super().__init__(
            code=code,
            message=message,
            description=description,
            http_status=503,
            details=error_details,
        )


class AuthError(AsgardError):
    """Authentication/authorization error."""
    
    def __init__(
        self,
        code: str = "AUT-0001",
        message: str = "Unauthorized",
        description: Optional[str] = None,
        http_status: int = 401,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            description=description,
            http_status=http_status,
            details=details or {},
        )
