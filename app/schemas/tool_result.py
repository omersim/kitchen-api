"""
ToolResult schema and widget definitions per V1.1 spec.
"""

from datetime import datetime
from typing import List, Optional, Any, Dict, Literal, Union
from pydantic import BaseModel, Field


# =============================================================================
# Widget Schemas
# =============================================================================

class KPICard(BaseModel):
    """Single KPI card data."""
    key: str
    label: str
    value: Any
    format: Optional[str] = None  # "currency", "percent", "number"
    change: Optional[float] = None
    change_direction: Optional[str] = None  # "up", "down", "neutral"


class KPICardsWidget(BaseModel):
    """KPI Cards widget - displays key metrics."""
    type: Literal["kpi_cards"] = "kpi_cards"
    data: Dict[str, Any]
    # Expected keys: price, day_change_pct, analyst_score_1_5, analyst_label,
    # analysts_count, price_target_consensus, price_target_upside_pct


class TradingViewEmbedWidget(BaseModel):
    """TradingView chart embed widget."""
    type: Literal["tradingview_embed"] = "tradingview_embed"
    data: Dict[str, Any]
    # Expected keys: tv_symbol, interval, theme, locale, autosize, allow_symbol_change


class AnalystTarget(BaseModel):
    """Analyst price target data."""
    consensus: Optional[float] = None
    median: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None


class AnalystDistribution(BaseModel):
    """Analyst recommendation distribution."""
    strongBuy: int = 0
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strongSell: int = 0


class AnalystCardWidget(BaseModel):
    """Analyst consensus card widget."""
    type: Literal["analyst_card"] = "analyst_card"
    data: Dict[str, Any]
    # Expected keys: score_1_5, label, analysts_count, targets (AnalystTarget), 
    # distribution (AnalystDistribution)


class TableColumn(BaseModel):
    """Table column definition."""
    key: str
    label: str
    format: Optional[str] = None


class TableRow(BaseModel):
    """Table row data."""
    label: str
    values: Dict[str, Any]


class TableWidget(BaseModel):
    """Data table widget."""
    type: Literal["table"] = "table"
    data: Dict[str, Any]
    # Expected keys: unit, scale (K/M/B), columns (List[TableColumn]), rows (List[TableRow])


class InsightItem(BaseModel):
    """Single insight item."""
    severity: Literal["low", "medium", "high"]
    title: str
    why: str
    what_to_do: str
    evidence: Optional[str] = None


class InsightListWidget(BaseModel):
    """Insights list widget."""
    type: Literal["insight_list"] = "insight_list"
    data: Dict[str, Any]
    # Expected keys: items (List[InsightItem])


class NoticeWidget(BaseModel):
    """Notice/alert widget."""
    type: Literal["notice"] = "notice"
    data: Dict[str, Any]
    # Expected keys: kind (info/warning/error), html_message


class CTAButton(BaseModel):
    """CTA button definition."""
    url: str
    label: str
    style: Literal["primary", "secondary"] = "primary"


class CTABoxWidget(BaseModel):
    """Call to action box widget."""
    type: Literal["cta_box"] = "cta_box"
    data: Dict[str, Any]
    # Expected keys: html_message, buttons (List[CTAButton]), html_disclosure


# =============================================================================
# Widget Union Type
# =============================================================================

class Widget(BaseModel):
    """Generic widget container."""
    id: str
    type: str
    data: Dict[str, Any]


# =============================================================================
# Section Schema
# =============================================================================

class Section(BaseModel):
    """Content section with HTML."""
    id: str
    title: str
    html: str


# =============================================================================
# Entity Schema
# =============================================================================

class Entity(BaseModel):
    """Entity being analyzed (stock, fund, etc.)."""
    type: str  # "stock", "fund", "crypto"
    id: str    # Symbol/identifier
    name: Optional[str] = None  # Full name (e.g., "Apple Inc")
    ticker: Optional[str] = None  # Ticker symbol
    exchange: Optional[str] = None  # Normalized exchange (e.g., "NASDAQ")
    logo: Optional[str] = None  # Logo URL


# =============================================================================
# SEO Schema
# =============================================================================

class SEOData(BaseModel):
    """SEO metadata for the page."""
    title: str
    description: str
    canonical: str
    robots: str = "index, follow"


# =============================================================================
# Main ToolResult Schema
# =============================================================================

class ToolResult(BaseModel):
    """
    Unified response format from Kitchen API.
    All tools return data in this format.
    """
    schema_version: str = "1.0"
    tool_key: str
    lang: str = "he"
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    entity: Entity
    seo: SEOData
    widgets: List[Widget]
    sections: List[Section]
    disclaimer: str = ""
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# =============================================================================
# Tool Registry Entry
# =============================================================================

class ToolInfo(BaseModel):
    """Tool information for registry."""
    tool_key: str
    name: str
    description: str
    entity_type: str
    pack: str
    endpoint: str
