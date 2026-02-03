"""
Tools router - handles /v1/tools endpoints.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional

from app.schemas import ToolResult, ToolInfo, ErrorResponse, ErrorCode
from app.services.stock_review import StockReviewService

router = APIRouter(prefix="/tools", tags=["Tools"])

# Tool registry
TOOLS_REGISTRY = {
    "stock_review": ToolInfo(
        tool_key="stock_review",
        name="סקירת מניה",
        description="ניתוח מקיף של מניה כולל נתונים פיננסיים, המלצות אנליסטים ותובנות",
        entity_type="stock",
        pack="stocks",
        endpoint="/v1/tools/stock_review/render"
    )
}


@router.get("/")
async def list_tools():
    """
    List all available tools.
    Returns tool registry with metadata.
    """
    return {
        "tools": [tool.model_dump() for tool in TOOLS_REGISTRY.values()]
    }


@router.get("/{tool_key}")
async def get_tool_info(tool_key: str):
    """
    Get information about a specific tool.
    """
    if tool_key not in TOOLS_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"כלי '{tool_key}' לא נמצא",
                request_id="",
                retryable=False
            ).model_dump()
        )
    
    return TOOLS_REGISTRY[tool_key].model_dump()


@router.get("/{tool_key}/render", response_model=ToolResult)
async def render_tool(
    tool_key: str,
    request: Request,
    symbol: Optional[str] = None,
    lang: str = "he"
):
    """
    Render tool output for a given entity.
    
    For stock_review:
    - symbol: Stock ticker symbol (required)
    - lang: Language code (default: he)
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    if tool_key not in TOOLS_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"כלי '{tool_key}' לא נמצא",
                request_id=request_id,
                retryable=False
            ).model_dump()
        )
    
    # Route to appropriate service
    if tool_key == "stock_review":
        if not symbol:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message="חובה לציין סימול מניה (symbol)",
                    request_id=request_id,
                    retryable=False
                ).model_dump()
            )
        
        service = StockReviewService()
        return await service.generate_review(
            symbol=symbol.upper(),
            lang=lang,
            request_id=request_id
        )
    
    # Fallback for unimplemented tools
    raise HTTPException(
        status_code=501,
        detail=ErrorResponse(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=f"כלי '{tool_key}' עדיין לא מימוש",
            request_id=request_id,
            retryable=False
        ).model_dump()
    )
