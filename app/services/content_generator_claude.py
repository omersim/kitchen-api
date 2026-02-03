"""
Anthropic Claude service for generating stock review content.
Provides higher quality Hebrew content compared to GPT.
"""

import logging
import json
from typing import Dict, Any, List, Optional

import anthropic

logger = logging.getLogger(__name__)


class ClaudeContentGenerator:
    """Service for generating stock review content using Claude."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"  # Latest Claude Sonnet

    async def generate_stock_sections(
        self,
        symbol: str,
        company_name: str,
        profile: Dict[str, Any],
        kpi_data: Dict[str, Any],
        analyst_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate content sections for a stock review."""

        # Build a comprehensive data context
        data_context = f"""
נתוני המניה:
- חברה: {company_name}
- סימול: {symbol}
- מחיר נוכחי: ${kpi_data.get('price', 'לא זמין')}
- שינוי יומי: {kpi_data.get('day_change_pct', 'לא זמין')}%
- דירוג אנליסטים: {analyst_data.get('label', 'לא זמין')} ({analyst_data.get('score_1_5', 'לא זמין')}/5)
- מספר אנליסטים: {analyst_data.get('analysts_count', 0)}
- מחיר יעד קונצנזוס: ${analyst_data.get('targets', {}).get('consensus', 'לא זמין')}
- מחיר יעד גבוה: ${analyst_data.get('targets', {}).get('high', 'לא זמין')}
- מחיר יעד נמוך: ${analyst_data.get('targets', {}).get('low', 'לא זמין')}
"""

        if profile.get('weburl'):
            data_context += f"- אתר: {profile['weburl']}\n"
        if profile.get('finnhubIndustry'):
            data_context += f"- תעשייה: {profile['finnhubIndustry']}\n"
        if profile.get('country'):
            data_context += f"- מדינה: {profile['country']}\n"
        if profile.get('marketCapitalization'):
            data_context += f"- שווי שוק: ${profile['marketCapitalization']} מיליון\n"
        if profile.get('description'):
            # Limit description length
            desc = profile['description'][:500]
            data_context += f"- תיאור החברה: {desc}\n"

        # Distribution breakdown
        dist = analyst_data.get('distribution', {})
        if dist:
            data_context += f"""
התפלגות המלצות אנליסטים:
- Strong Buy: {dist.get('strongBuy', 0)}
- Buy: {dist.get('buy', 0)}
- Hold: {dist.get('hold', 0)}
- Sell: {dist.get('sell', 0)}
- Strong Sell: {dist.get('strongSell', 0)}
"""

        prompt = f"""אתה כותב פיננסי מומחה המתמחה בסקירות מניות בעברית עבור אתר msl.org.il.
הקהל שלך הוא משקיעים מתחילים עד בינוניים בישראל.

{data_context}

כתוב סקירה מקיפה ואיכותית על {company_name} ({symbol}).

חשוב מאוד:
1. כתוב רק בעברית תקנית
2. השתמש אך ורק בנתונים שסופקו למעלה - אל תמציא מספרים או עובדות
3. אם אין לך מידע ספציפי, כתוב באופן כללי יותר (למשל "החברה פועלת בתחום הטכנולוגיה" במקום להמציא נתונים)
4. טון מקצועי ואינפורמטיבי, לא שיווקי
5. ללא המלצות קנייה/מכירה מפורשות
6. כל סקשן צריך להיות מפורט ובעל ערך

החזר JSON בפורמט הבא (ללא טקסט נוסף, רק JSON תקני):

{{
  "sections": [
    {{
      "id": "tl_dr",
      "title": "בקצרה: מה מצב החברה?",
      "html": "<p>סיכום של 4-5 משפטים על מצב החברה, הביצועים האחרונים, והכיוון העסקי. התבסס על הנתונים שניתנו.</p>"
    }},
    {{
      "id": "business_model",
      "title": "מה החברה עושה ואיך היא מרוויחה כסף?",
      "html": "<p>הסבר מפורט על מודל העסקי והשוק בו פועלת החברה. 5-7 משפטים.</p>"
    }},
    {{
      "id": "latest_report",
      "title": "נקודות עיקריות מהדוח האחרון",
      "html": "<ul><li>נקודה מפורטת 1</li><li>נקודה מפורטת 2</li><li>נקודה מפורטת 3</li><li>נקודה מפורטת 4</li></ul>"
    }},
    {{
      "id": "analysts_view",
      "title": "מה חושבים האנליסטים?",
      "html": "<p>ניתוח של המלצות האנליסטים בהתבסס על הנתונים שניתנו. 4-5 משפטים.</p>"
    }},
    {{
      "id": "risks",
      "title": "סיכונים עיקריים",
      "html": "<ul><li>סיכון 1 עם הסבר של 2 משפטים</li><li>סיכון 2 עם הסבר</li><li>סיכון 3 עם הסבר</li></ul>"
    }},
    {{
      "id": "who_fits",
      "title": "למי המניה עשויה להתאים? (לא המלצה)",
      "html": "<ul><li>פרופיל משקיע 1 עם הסבר</li><li>פרופיל משקיע 2 עם הסבר</li></ul>"
    }}
  ]
}}"""

        try:
            # Use sync client in async context (Claude SDK handles this)
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.3,  # Lower temperature for more factual content
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Extract JSON from response
            content_text = response.content[0].text

            # Try to parse JSON
            try:
                # Handle case where Claude wraps in markdown code blocks
                if "```json" in content_text:
                    content_text = content_text.split("```json")[1].split("```")[0]
                elif "```" in content_text:
                    content_text = content_text.split("```")[1].split("```")[0]

                content = json.loads(content_text.strip())
                return content.get("sections", [])

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Claude response as JSON: {e}")
                logger.debug(f"Response was: {content_text[:500]}")
                return self._fallback_sections(company_name, symbol)

        except Exception as e:
            logger.error(f"Error generating content with Claude: {e}")
            return self._fallback_sections(company_name, symbol)

    def _fallback_sections(self, company_name: str, symbol: str) -> List[Dict[str, Any]]:
        """Return minimal fallback sections on error."""
        return [
            {
                "id": "tl_dr",
                "title": "סקירה כללית",
                "html": f"<p>סקירה עבור {company_name} ({symbol}). התוכן המפורט יתעדכן בקרוב.</p>"
            }
        ]

    async def generate_insights(
        self,
        symbol: str,
        company_name: str,
        kpi_data: Dict[str, Any],
        analyst_data: Dict[str, Any],
        fundamentals: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Generate investment insights based on data analysis."""

        insights = []

        # Analyst consensus insight
        score = analyst_data.get("score_1_5")
        if score:
            if score >= 4.0:
                insights.append({
                    "severity": "low",
                    "title": "קונצנזוס אנליסטים חיובי",
                    "why": f"דירוג ממוצע של {score}/5 מצד {analyst_data.get('analysts_count', 0)} אנליסטים",
                    "what_to_do": "שווה לבחון את הסיבות לאופטימיות",
                    "evidence": analyst_data.get("label")
                })
            elif score <= 2.5:
                insights.append({
                    "severity": "high",
                    "title": "קונצנזוס אנליסטים שלילי",
                    "why": f"דירוג ממוצע של {score}/5 מצד {analyst_data.get('analysts_count', 0)} אנליסטים",
                    "what_to_do": "חשוב להבין את הסיבות לפסימיות",
                    "evidence": analyst_data.get("label")
                })

        # Price target insight
        targets = analyst_data.get("targets", {})
        current_price = kpi_data.get("price")
        if targets.get("consensus") and current_price:
            upside = ((targets["consensus"] - current_price) / current_price) * 100
            if upside > 20:
                insights.append({
                    "severity": "low",
                    "title": "פוטנציאל עלייה משמעותי",
                    "why": f"מחיר יעד קונצנזוס: ${targets['consensus']:.2f}, {round(upside)}% מעל המחיר הנוכחי",
                    "what_to_do": "בדוק את ההנחות מאחורי מחירי היעד",
                    "evidence": f"טווח יעדים: ${targets.get('low', 0):.2f} - ${targets.get('high', 0):.2f}"
                })
            elif upside < -10:
                insights.append({
                    "severity": "high",
                    "title": "מחיר מעל יעד האנליסטים",
                    "why": f"מחיר יעד קונצנזוס: ${targets['consensus']:.2f}, {round(abs(upside))}% מתחת למחיר הנוכחי",
                    "what_to_do": "המניה עשויה להיות במחיר גבוה יחסית להערכות",
                    "evidence": None
                })

        # Daily change insight
        day_change = kpi_data.get("day_change_pct")
        if day_change and abs(day_change) > 5:
            severity = "high" if abs(day_change) > 10 else "medium"
            direction = "עלייה" if day_change > 0 else "ירידה"
            insights.append({
                "severity": severity,
                "title": f"{direction} משמעותית היום",
                "why": f"המניה זזה {abs(round(day_change, 1))}% היום",
                "what_to_do": "בדוק אם יש חדשות או אירוע שהשפיע",
                "evidence": None
            })

        return insights
