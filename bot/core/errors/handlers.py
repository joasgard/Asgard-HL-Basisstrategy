"""
FastAPI exception handlers for the error system.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi import status
import logging

from .exceptions import AsgardError, ValidationError, InsufficientFundsError
from .codes import ErrorCode, get_error_info

logger = logging.getLogger(__name__)


async def asgard_error_handler(request: Request, exc: AsgardError) -> JSONResponse:
    """Handle AsgardError exceptions."""
    error_response = {
        "error_code": exc.code,
        "message": exc.message,
        "description": exc.description,
        "details": exc.details,
    }
    
    # Log the error
    if exc.http_status >= 500:
        logger.error(
            f"Server error {exc.code}: {exc.message}",
            extra={
                "error_code": exc.code,
                "path": request.url.path,
                "details": exc.details,
            }
        )
    else:
        logger.warning(
            f"Client error {exc.code}: {exc.message}",
            extra={
                "error_code": exc.code,
                "path": request.url.path,
                "details": exc.details,
            }
        )
    
    return JSONResponse(
        status_code=exc.http_status,
        content=error_response,
    )


async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle ValidationError exceptions."""
    return await asgard_error_handler(request, exc)


async def insufficient_funds_error_handler(request: Request, exc: InsufficientFundsError) -> JSONResponse:
    """Handle InsufficientFundsError exceptions."""
    return await asgard_error_handler(request, exc)


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions."""
    error_code = ErrorCode.UNKNOWN_ERROR
    
    logger.exception(
        f"Unhandled exception: {exc}",
        extra={"path": request.url.path}
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": error_code.code,
            "message": error_code.message,
            "description": error_code.description,
            "details": {"error": str(exc)},
        },
    )


def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app."""
    app.add_exception_handler(AsgardError, asgard_error_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(InsufficientFundsError, insufficient_funds_error_handler)
    app.add_exception_handler(Exception, general_exception_handler)
