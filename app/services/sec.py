"""
SEC EDGAR API service for fetching company fundamentals.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

import httpx
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# SEC endpoints
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Cache for ticker -> CIK mapping (24 hour TTL)
cik_cache = TTLCache(maxsize=10000, ttl=86400)


class SECService:
    """Service for fetching company fundamentals from SEC EDGAR."""
    
    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "MSL Stock Tool contact@msl.org.il",
            "Accept": "application/json"
        }
        self.client = httpx.AsyncClient(timeout=timeout, headers=self.headers)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def get_cik(self, symbol: str) -> Optional[str]:
        """Get CIK number for a stock symbol."""
        # Check cache first
        if symbol in cik_cache:
            return cik_cache[symbol]
        
        try:
            response = await self.client.get(SEC_TICKERS_URL)
            
            if response.status_code == 429:
                logger.warning("SEC rate limit hit")
                return None
            
            if response.status_code != 200:
                logger.error(f"SEC tickers error: {response.status_code}")
                return None
            
            tickers = response.json()
            
            # Build cache and find symbol
            for key, data in tickers.items():
                ticker = data.get("ticker", "").upper()
                cik = str(data.get("cik_str", "")).zfill(10)
                cik_cache[ticker] = cik
                
                if ticker == symbol.upper():
                    return cik
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching CIK: {e}")
            return None
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def get_company_facts(self, cik: str) -> Optional[Dict[str, Any]]:
        """Get company facts from SEC EDGAR."""
        try:
            url = SEC_COMPANY_FACTS_URL.format(cik=cik)
            response = await self.client.get(url)
            
            if response.status_code == 429:
                logger.warning("SEC rate limit hit for company facts")
                return None
            
            if response.status_code == 404:
                logger.info(f"No SEC data for CIK {cik}")
                return None
            
            if response.status_code != 200:
                logger.error(f"SEC company facts error: {response.status_code}")
                return None
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching company facts: {e}")
            return None
    
    def extract_metric(
        self,
        metric_data: Optional[Dict],
        period: str,  # 'annual' or 'quarterly'
        count: int
    ) -> Dict[str, Any]:
        """Extract metric values from SEC data."""
        empty_result = {
            "periods": ["N/A"] * count,
            "values": [None] * count
        }
        
        if not metric_data or not metric_data.get("units"):
            return empty_result
        
        # Try USD first, then shares
        units = metric_data["units"].get("USD") or metric_data["units"].get("shares") or []
        
        # Filter by form type
        form_filter = "10-K" if period == "annual" else "10-Q"
        filtered = [item for item in units if item.get("form") == form_filter]
        
        # Sort by end date descending
        filtered.sort(key=lambda x: x.get("end", ""), reverse=True)
        selected = filtered[:count]
        
        if not selected:
            return empty_result
        
        periods = []
        values = []
        
        for item in selected:
            end_date = item.get("end", "")
            val = item.get("val")
            
            # Format period
            if end_date:
                year = datetime.fromisoformat(end_date).year
                if period == "annual":
                    periods.append(f"FY{year}")
                else:
                    fp = item.get("fp", "")
                    periods.append(f"{fp} FY{year}")
            else:
                periods.append("N/A")
            
            # Format value
            if val is not None:
                if abs(val) > 1_000_000_000:
                    values.append(round(val / 1_000_000_000, 1))
                elif abs(val) > 1_000_000:
                    values.append(round(val / 1_000_000, 1))
                else:
                    values.append(round(val, 2))
            else:
                values.append(None)
        
        # Reverse to get chronological order
        periods.reverse()
        values.reverse()
        
        return {"periods": periods, "values": values}
    
    async def get_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get full fundamentals data for a symbol."""
        cik = await self.get_cik(symbol)
        if not cik:
            logger.info(f"No CIK found for {symbol}")
            return None
        
        facts_data = await self.get_company_facts(cik)
        if not facts_data:
            return None
        
        facts = facts_data.get("facts", {}).get("us-gaap", {})
        
        # Extract annual data (3 years)
        revenues = self.extract_metric(
            facts.get("Revenues") or facts.get("RevenueFromContractWithCustomerExcludingAssessedTax"),
            "annual", 3
        )
        net_income = self.extract_metric(facts.get("NetIncomeLoss"), "annual", 3)
        eps = self.extract_metric(facts.get("EarningsPerShareDiluted"), "annual", 3)
        shares = self.extract_metric(
            facts.get("WeightedAverageNumberOfDilutedSharesOutstanding"),
            "annual", 3
        )
        
        # Cash flow data
        op_cash_flow = self.extract_metric(
            facts.get("NetCashProvidedByUsedInOperatingActivities"),
            "annual", 3
        )
        capex = self.extract_metric(
            facts.get("PaymentsToAcquirePropertyPlantAndEquipment"),
            "annual", 3
        )
        
        # Calculate free cash flow
        fcf_values = []
        for i in range(len(op_cash_flow["values"])):
            ocf = op_cash_flow["values"][i]
            cx = capex["values"][i]
            if ocf is not None and cx is not None:
                fcf_values.append(round(ocf - abs(cx), 1))
            else:
                fcf_values.append(None)
        
        # Quarterly data (latest vs year ago)
        q_revenues = self.extract_metric(
            facts.get("Revenues") or facts.get("RevenueFromContractWithCustomerExcludingAssessedTax"),
            "quarterly", 5
        )
        q_net_income = self.extract_metric(facts.get("NetIncomeLoss"), "quarterly", 5)
        q_eps = self.extract_metric(facts.get("EarningsPerShareDiluted"), "quarterly", 5)
        
        return {
            "annual_3y": {
                "type": "table",
                "data": {
                    "title": "נתונים שנתיים (3 שנים)",
                    "unit": "USD",
                    "scale": "B",
                    "columns": [
                        {"key": "metric", "label": "מדד"},
                        *[{"key": f"y{i}", "label": p} for i, p in enumerate(revenues["periods"])]
                    ],
                    "rows": [
                        {"label": "הכנסות", "values": revenues["values"]},
                        {"label": "רווח נקי", "values": net_income["values"]},
                        {"label": "רווח למניה (EPS)", "values": eps["values"]},
                        {"label": "מניות (מדולל)", "values": shares["values"]}
                    ]
                }
            },
            "cashflow_3y": {
                "type": "table",
                "data": {
                    "title": "תזרים מזומנים (3 שנים)",
                    "unit": "USD",
                    "scale": "B",
                    "columns": [
                        {"key": "metric", "label": "מדד"},
                        *[{"key": f"y{i}", "label": p} for i, p in enumerate(op_cash_flow["periods"])]
                    ],
                    "rows": [
                        {"label": "תזרים תפעולי", "values": op_cash_flow["values"]},
                        {"label": "Capex", "values": [
                            -abs(v) if v is not None else None for v in capex["values"]
                        ]},
                        {"label": "תזרים חופשי (FCF)", "values": fcf_values}
                    ]
                }
            },
            "quarterly": {
                "type": "table",
                "data": {
                    "title": "נתונים רבעוניים",
                    "unit": "USD",
                    "scale": "B",
                    "columns": [
                        {"key": "metric", "label": "מדד"},
                        *[{"key": f"q{i}", "label": p} for i, p in enumerate(q_revenues["periods"][-4:])]
                    ],
                    "rows": [
                        {"label": "הכנסות", "values": q_revenues["values"][-4:]},
                        {"label": "רווח נקי", "values": q_net_income["values"][-4:]},
                        {"label": "EPS", "values": q_eps["values"][-4:]}
                    ]
                }
            }
        }
