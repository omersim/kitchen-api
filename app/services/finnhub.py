"""
Finnhub API service for fetching stock data.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from fastapi import HTTPException

from app.schemas.errors import ErrorCode, ErrorResponse

logger = logging.getLogger(__name__)

# Finnhub base URL
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubRateLimitError(Exception):
    """Raised when Finnhub rate limit is hit."""
    pass


class FinnhubService:
    """Service for interacting with Finnhub API."""
    
    def __init__(self, api_key: str, timeout: float = 10.0):
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(FinnhubRateLimitError)
    )
    async def _request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make a request to Finnhub API."""
        params = params or {}
        params["token"] = self.api_key
        
        url = f"{FINNHUB_BASE_URL}/{endpoint}"
        
        try:
            response = await self.client.get(url, params=params)
            
            if response.status_code == 429:
                logger.warning("Finnhub rate limit hit")
                raise FinnhubRateLimitError("Rate limit exceeded")
            
            if response.status_code == 401:
                logger.error("Finnhub unauthorized - check API key")
                raise HTTPException(
                    status_code=401,
                    detail=ErrorResponse(
                        error_code=ErrorCode.FINNHUB_UNAUTHORIZED,
                        message="מפתח Finnhub לא תקין",
                        request_id="",
                        retryable=False
                    ).model_dump()
                )
            
            if response.status_code != 200:
                logger.error(f"Finnhub error: {response.status_code} - {response.text}")
                return {}
            
            return response.json()
            
        except httpx.TimeoutException:
            logger.error(f"Finnhub timeout for {endpoint}")
            raise HTTPException(
                status_code=504,
                detail=ErrorResponse(
                    error_code=ErrorCode.UPSTREAM_TIMEOUT,
                    message="Finnhub לא הגיב בזמן",
                    request_id="",
                    retryable=True
                ).model_dump()
            )
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote for a symbol."""
        return await self._request("quote", {"symbol": symbol})
    
    async def get_profile(self, symbol: str) -> Dict[str, Any]:
        """Get company profile."""
        return await self._request("stock/profile2", {"symbol": symbol})
    
    async def get_recommendations(self, symbol: str) -> list:
        """Get analyst recommendations."""
        return await self._request("stock/recommendation", {"symbol": symbol})
    
    async def get_price_target(self, symbol: str) -> Dict[str, Any]:
        """Get analyst price targets."""
        return await self._request("stock/price-target", {"symbol": symbol})
    
    async def get_all_stock_data(self, symbol: str) -> Dict[str, Any]:
        """Fetch all stock data in parallel."""
        import asyncio
        
        quote_task = self.get_quote(symbol)
        profile_task = self.get_profile(symbol)
        recommendations_task = self.get_recommendations(symbol)
        price_target_task = self.get_price_target(symbol)
        
        quote, profile, recommendations, price_target = await asyncio.gather(
            quote_task, profile_task, recommendations_task, price_target_task,
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(quote, Exception):
            logger.error(f"Error fetching quote: {quote}")
            quote = {}
        if isinstance(profile, Exception):
            logger.error(f"Error fetching profile: {profile}")
            profile = {}
        if isinstance(recommendations, Exception):
            logger.error(f"Error fetching recommendations: {recommendations}")
            recommendations = []
        if isinstance(price_target, Exception):
            logger.error(f"Error fetching price target: {price_target}")
            price_target = {}
        
        return {
            "quote": quote,
            "profile": profile,
            "recommendations": recommendations if isinstance(recommendations, list) else [],
            "price_target": price_target
        }
    
    def calculate_analyst_data(self, recommendations: list, price_target: Dict, current_price: float) -> Dict[str, Any]:
        """Calculate analyst consensus data."""
        analyst_data = {
            "score_1_5": None,
            "label": None,
            "distribution": {
                "strongBuy": 0,
                "buy": 0,
                "hold": 0,
                "sell": 0,
                "strongSell": 0
            },
            "analysts_count": 0,
            "targets": {
                "consensus": None,
                "median": None,
                "high": None,
                "low": None
            }
        }
        
        # Process recommendations
        if recommendations and len(recommendations) > 0:
            latest = recommendations[0]
            analyst_data["distribution"] = {
                "strongBuy": latest.get("strongBuy", 0) or 0,
                "buy": latest.get("buy", 0) or 0,
                "hold": latest.get("hold", 0) or 0,
                "sell": latest.get("sell", 0) or 0,
                "strongSell": latest.get("strongSell", 0) or 0
            }
            
            total = sum(analyst_data["distribution"].values())
            analyst_data["analysts_count"] = total
            
            if total > 0:
                score = (
                    analyst_data["distribution"]["strongBuy"] * 5 +
                    analyst_data["distribution"]["buy"] * 4 +
                    analyst_data["distribution"]["hold"] * 3 +
                    analyst_data["distribution"]["sell"] * 2 +
                    analyst_data["distribution"]["strongSell"] * 1
                ) / total
                
                analyst_data["score_1_5"] = round(score, 2)
                
                if score >= 4.5:
                    analyst_data["label"] = "קנייה חזקה"
                elif score >= 3.5:
                    analyst_data["label"] = "קנייה"
                elif score >= 2.5:
                    analyst_data["label"] = "החזקה"
                elif score >= 1.5:
                    analyst_data["label"] = "מכירה"
                else:
                    analyst_data["label"] = "מכירה חזקה"
        
        # Process price targets
        if price_target and price_target.get("targetMean"):
            analyst_data["targets"] = {
                "consensus": price_target.get("targetMean"),
                "median": price_target.get("targetMedian"),
                "high": price_target.get("targetHigh"),
                "low": price_target.get("targetLow")
            }
        
        return analyst_data
