"""
Error schemas and codes for Kitchen API.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class ErrorCode(str, Enum):
    """Standardized error codes per V1.1 spec."""
    
    # Authentication
    UNAUTHORIZED = "UNAUTHORIZED"
    
    # Configuration
    MISCONFIGURED = "MISCONFIGURED"
    
    # Finnhub errors
    FINNHUB_RATE_LIMIT = "FINNHUB_RATE_LIMIT"
    FINNHUB_UNAUTHORIZED = "FINNHUB_UNAUTHORIZED"
    
    # SEC errors
    SEC_RATE_LIMIT = "SEC_RATE_LIMIT"
    
    # Data errors
    UNKNOWN_SYMBOL = "UNKNOWN_SYMBOL"
    NO_SEC_DATA = "NO_SEC_DATA"
    DATA_PARSE_ERROR = "DATA_PARSE_ERROR"
    
    # System errors
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorResponse(BaseModel):
    """Standardized error response format."""
    
    error_code: ErrorCode
    message: str
    request_id: str
    retryable: bool
    details: Optional[dict] = None
    
    class Config:
        use_enum_values = True
