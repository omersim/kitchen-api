"""
Stock Review service - orchestrates data fetching and content generation.
"""

import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from app.schemas import ToolResult, Widget, Section, Entity, SEOData
from app.schemas.errors import ErrorCode, ErrorResponse
from app.services.finnhub import FinnhubService
from app.services.sec import SECService
from app.services.content_generator import ContentGeneratorService
from app.services.content_generator_claude import ClaudeContentGenerator

logger = logging.getLogger(__name__)


class StockReviewService:
    """
    Main service for generating stock reviews.
    Orchestrates Finnhub, SEC, and OpenAI services.
    """
    
    def __init__(self):
        self.finnhub_key = os.getenv("KITCHEN_FINNHUB_API_KEY", "")
        self.openai_key = os.getenv("KITCHEN_OPENAI_API_KEY", "")
        self.anthropic_key = os.getenv("KITCHEN_ANTHROPIC_API_KEY", "")

    @staticmethod
    def _normalize_exchange(exchange: str) -> str:
        """Normalize exchange name for TradingView."""
        exchange = exchange.upper().strip()

        exchange_map = {
            "NASDAQ NMS - GLOBAL MARKET": "NASDAQ",
            "NASDAQ NMS": "NASDAQ",
            "NASDAQ GLOBAL MARKET": "NASDAQ",
            "NASDAQ GLOBAL SELECT": "NASDAQ",
            "NEW YORK STOCK EXCHANGE": "NYSE",
            "NYSE ARCA": "AMEX",
            "NYSE AMERICAN": "AMEX",
            "TEL AVIV": "TASE",
        }

        # Try exact match
        if exchange in exchange_map:
            return exchange_map[exchange]

        # Try partial match
        for key, value in exchange_map.items():
            if key in exchange:
                return value

        # Return cleaned version if no mapping
        import re
        cleaned = re.sub(r'[^A-Z]', '', exchange)
        return cleaned if cleaned else "NASDAQ"
    
    async def generate_review(
        self,
        symbol: str,
        lang: str = "he",
        request_id: str = ""
    ) -> ToolResult:
        """
        Generate a complete stock review.
        
        Args:
            symbol: Stock ticker symbol (uppercase)
            lang: Language code (default: he)
            request_id: Request ID for tracking
            
        Returns:
            ToolResult with all widgets and sections
        """
        symbol = symbol.upper()
        
        # Validate configuration
        if not self.finnhub_key:
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error_code=ErrorCode.MISCONFIGURED,
                    message="Finnhub API key לא מוגדר",
                    request_id=request_id,
                    retryable=False
                ).model_dump()
            )
        
        # Initialize services
        finnhub = FinnhubService(self.finnhub_key)
        sec = SECService()

        # Prefer Claude over OpenAI for better Hebrew content
        content_gen = None
        if self.anthropic_key:
            logger.info("Using Claude for content generation")
            content_gen = ClaudeContentGenerator(self.anthropic_key)
        elif self.openai_key:
            logger.info("Using OpenAI for content generation (Claude key not set)")
            content_gen = ContentGeneratorService(self.openai_key)
        
        try:
            # Fetch Finnhub data
            logger.info(f"Fetching Finnhub data for {symbol}")
            finnhub_data = await finnhub.get_all_stock_data(symbol)
            
            quote = finnhub_data["quote"]
            profile = finnhub_data["profile"]
            recommendations = finnhub_data["recommendations"]
            price_target = finnhub_data["price_target"]
            
            # Validate symbol exists
            if not profile or not profile.get("name"):
                raise HTTPException(
                    status_code=404,
                    detail=ErrorResponse(
                        error_code=ErrorCode.UNKNOWN_SYMBOL,
                        message=f"סימול '{symbol}' לא נמצא",
                        request_id=request_id,
                        retryable=False
                    ).model_dump()
                )
            
            company_name = profile.get("name", symbol)
            current_price = quote.get("c", 0)
            
            # Calculate analyst data
            analyst_data = finnhub.calculate_analyst_data(
                recommendations,
                price_target,
                current_price
            )
            
            # Build KPI data
            kpi_data = {
                "price": current_price,
                "day_change_pct": quote.get("dp"),
                "analyst_score_1_5": analyst_data["score_1_5"],
                "analyst_label": analyst_data["label"],
                "analysts_count": analyst_data["analysts_count"],
                "price_target_consensus": analyst_data["targets"]["consensus"],
                "price_target_upside_pct": None
            }
            
            # Calculate upside
            if analyst_data["targets"]["consensus"] and current_price:
                upside = ((analyst_data["targets"]["consensus"] - current_price) / current_price) * 100
                kpi_data["price_target_upside_pct"] = round(upside, 2)
            
            # Fetch SEC fundamentals
            logger.info(f"Fetching SEC data for {symbol}")
            fundamentals = await sec.get_fundamentals(symbol)
            
            # Build widgets list
            widgets = []
            
            # KPI Cards widget
            widgets.append(Widget(
                id="kpis",
                type="kpi_cards",
                data=kpi_data
            ))
            
            # TradingView embed widget - normalize exchange name
            raw_exchange = profile.get("exchange", "NASDAQ")
            tv_exchange = self._normalize_exchange(raw_exchange)
            tv_symbol = f"{tv_exchange}:{symbol}"
            widgets.append(Widget(
                id="tv_chart",
                type="tradingview_embed",
                data={
                    "tv_symbol": tv_symbol,
                    "interval": "D",
                    "theme": "light",
                    "locale": "he_IL",
                    "autosize": True,
                    "allow_symbol_change": False
                }
            ))
            
            # Analyst card widget
            widgets.append(Widget(
                id="analysts",
                type="analyst_card",
                data={
                    "score_1_5": analyst_data["score_1_5"],
                    "label": analyst_data["label"],
                    "analysts_count": analyst_data["analysts_count"],
                    "targets": analyst_data["targets"],
                    "distribution": analyst_data["distribution"]
                }
            ))
            
            # Fundamentals tables (if available)
            no_sec_data = False
            if fundamentals:
                widgets.append(Widget(
                    id="fundamentals_annual_3y",
                    type="table",
                    data=fundamentals["annual_3y"]["data"]
                ))
                widgets.append(Widget(
                    id="fundamentals_cashflow_3y",
                    type="table",
                    data=fundamentals["cashflow_3y"]["data"]
                ))
                widgets.append(Widget(
                    id="fundamentals_quarterly",
                    type="table",
                    data=fundamentals["quarterly"]["data"]
                ))
            else:
                no_sec_data = True
                widgets.append(Widget(
                    id="fundamentals_notice",
                    type="notice",
                    data={
                        "kind": "info",
                        "html_message": f"<p>נתוני דוחות כספיים אינם זמינים עבור {symbol} מ-SEC/EDGAR.</p>"
                    }
                ))
            
            # Generate AI sections
            sections = []
            if content_gen:
                logger.info(f"Generating AI content for {symbol}")
                ai_sections = await content_gen.generate_stock_sections(
                    symbol=symbol,
                    company_name=company_name,
                    profile=profile,
                    kpi_data=kpi_data,
                    analyst_data=analyst_data
                )
                sections = [Section(**s) for s in ai_sections]
                
                # Generate insights
                insights = await content_gen.generate_insights(
                    symbol=symbol,
                    company_name=company_name,
                    kpi_data=kpi_data,
                    analyst_data=analyst_data,
                    fundamentals=fundamentals
                )
                if insights:
                    widgets.append(Widget(
                        id="insights",
                        type="insight_list",
                        data={"items": insights}
                    ))
            else:
                # Fallback section if no OpenAI key
                sections = [
                    Section(
                        id="overview",
                        title="סקירה כללית",
                        html=f"<p>סקירה עבור {company_name} ({symbol}). תוכן מפורט יופיע כאן לאחר הגדרת OpenAI API.</p>"
                    )
                ]
            
            # Add CTA widget
            widgets.append(Widget(
                id="cta",
                type="cta_box",
                data={
                    "html_message": "<p>רוצים להעמיק? בדקו את הכלים הנוספים שלנו</p>",
                    "buttons": [
                        {
                            "url": f"/stocks/",
                            "label": "כל המניות",
                            "style": "primary"
                        }
                    ],
                    "html_disclosure": "<small>המידע אינו מהווה ייעוץ השקעות</small>"
                }
            ))
            
            # Build SEO data
            seo = SEOData(
                title=f"סקירת מניית {company_name} ({symbol}) | MSL",
                description=f"ניתוח מקיף של מניית {company_name} ({symbol}) - נתונים פיננסיים, המלצות אנליסטים, דוחות ותובנות",
                canonical=f"https://msl.org.il/stocks/{symbol.lower()}",
                robots="index, follow" if not no_sec_data else "index, follow"
            )
            
            # Build final result
            return ToolResult(
                schema_version="1.0",
                tool_key="stock_review",
                lang=lang,
                generated_at=datetime.utcnow(),
                entity=Entity(
                    type="stock",
                    id=symbol,
                    name=company_name,
                    ticker=symbol,
                    exchange=tv_exchange,  # Normalized exchange for TradingView
                    logo=profile.get("logo")
                ),
                seo=seo,
                widgets=widgets,
                sections=sections,
                disclaimer="המידע באתר הינו אינפורמטיבי בלבד ואינו מהווה ייעוץ השקעות, המלצה או הצעה לרכישה או מכירה של ניירות ערך. כל החלטת השקעה היא באחריות המשתמש בלבד."
            )
            
        finally:
            # Cleanup
            await finnhub.close()
            await sec.close()
