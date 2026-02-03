"""
MSL Tools Kitchen API
Heavy processing server for stock data, SEC filings, and AI content generation.
"""

import uuid
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings

from app.routers import health, tools
from app.schemas.errors import ErrorResponse, ErrorCode


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] %(message)s'
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Configuration
    api_key: str = ""
    debug: bool = False
    
    # External APIs
    finnhub_api_key: str = ""
    openai_api_key: str = ""
    
    # Rate Limiting
    finnhub_rate_limit: int = 60  # requests per minute
    sec_rate_limit: int = 10  # requests per second
    
    # Cache TTLs (seconds)
    market_data_ttl: int = 1800  # 30 min
    analyst_data_ttl: int = 21600  # 6 hours
    fundamentals_ttl: int = 86400  # 24 hours
    
    class Config:
        env_file = ".env"
        env_prefix = "KITCHEN_"


settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    logger.info("Kitchen API starting up...")
    yield
    logger.info("Kitchen API shutting down...")


app = FastAPI(
    title="MSL Tools Kitchen API",
    description="Backend API for MSL Tools Platform - handles heavy data processing",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request_id to each request for observability."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    request.state.request_id = request_id
    
    # Add to logging context
    old_factory = logging.getLogRecordFactory()
    
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.request_id = request_id
        return record
    
    logging.setLogRecordFactory(record_factory)
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    logging.setLogRecordFactory(old_factory)
    return response


# API Key authentication
async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify the API key from request header."""
    if not settings.api_key:
        # No API key configured - skip validation (dev mode)
        return True
    
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error_code=ErrorCode.UNAUTHORIZED,
                message="מפתח API לא תקין",
                request_id="",
                retryable=False
            ).model_dump()
        )
    return True


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with standardized error format."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    if isinstance(exc.detail, dict) and "error_code" in exc.detail:
        # Already formatted error
        exc.detail["request_id"] = request_id
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=str(exc.detail),
            request_id=request_id,
            retryable=False
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(f"Unexpected error: {exc}")
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="שגיאה פנימית בשרת",
            request_id=request_id,
            retryable=True
        ).model_dump()
    )


# Include routers
app.include_router(health.router)
app.include_router(
    tools.router,
    prefix="/v1",
    dependencies=[Depends(verify_api_key)]
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
