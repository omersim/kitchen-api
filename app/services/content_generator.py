"""
OpenAI service for generating stock review content.
"""

import logging
import json
from typing import Dict, Any, List, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class ContentGeneratorService:
    """Service for generating stock review content using OpenAI."""
    
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)
    
    async def generate_stock_sections(
        self,
        symbol: str,
        company_name: str,
        profile: Dict[str, Any],
        kpi_data: Dict[str, Any],
        analyst_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate content sections for a stock review."""
        
        prompt = f"""
אתה כותב סקירת מניה מפורטת בעברית עבור משקיעים מתחילים-בינוניים באתר msl.org.il.

פרטי המניה:
- חברה: {company_name} ({symbol})
- מחיר נוכחי: ${kpi_data.get('price', 'N/A')}
- שינוי יומי: {kpi_data.get('day_change_pct', 'N/A')}%
- דירוג אנליסטים: {analyst_data.get('label', 'N/A')} ({analyst_data.get('score_1_5', 'N/A')}/5)
- מספר אנליסטים: {analyst_data.get('analysts_count', 0)}
- מחיר יעד קונצנזוס: ${analyst_data.get('targets', {}).get('consensus', 'N/A')}
{f"- אתר: {profile.get('weburl')}" if profile.get('weburl') else ''}
{f"- תעשייה: {profile.get('finnhubIndustry')}" if profile.get('finnhubIndustry') else ''}
{f"- תיאור: {profile.get('description', '')[:200]}" if profile.get('description') else ''}

צור JSON עם הסקשנים הבאים בעברית בלבד:

{{
  "sections": [
    {{
      "id": "tl_dr",
      "title": "בשורה אחת: מה מצב החברה היום?",
      "html": "<p>פסקה מפורטת (4-5 משפטים) המסכמת את מצב החברה, הביצועים האחרונים והכיוון העסקי</p>"
    }},
    {{
      "id": "business_model",
      "title": "מה החברה עושה ואיך היא מרוויחה כסף?",
      "html": "<p>הסבר מפורט על מודל העסקי, מקורות ההכנסה העיקריים, והשוק שבו פועלת החברה (6-8 משפטים)</p>"
    }},
    {{
      "id": "what_moved",
      "title": "מה הזיז את העסק השנה?",
      "html": "<ul><li>נקודה מפורטת 1 (2-3 משפטים)</li><li>נקודה מפורטת 2</li><li>נקודה מפורטת 3</li></ul>"
    }},
    {{
      "id": "latest_report",
      "title": "נקודות עיקריות מהדוח האחרון",
      "html": "<ul><li>שינוי/התפתחות מרכזית 1</li><li>שינוי/התפתחות מרכזית 2</li><li>נתון או הודעה חשובה 3</li><li>תובנה נוספת 4</li></ul>"
    }},
    {{
      "id": "under_radar",
      "title": "דברים שפחות מדברים עליהם",
      "html": "<ul><li>נקודה מפורטת 1 (2 משפטים)</li><li>נקודה מפורטת 2</li><li>נקודה מפורטת 3</li></ul>"
    }},
    {{
      "id": "risks",
      "title": "סיכונים עיקריים",
      "html": "<ul><li>סיכון 1 עם הסבר (2-3 משפטים)</li><li>סיכון 2 עם הסבר</li><li>סיכון 3 עם הסבר</li></ul>"
    }},
    {{
      "id": "who_fits",
      "title": "למי זה יכול להתאים? (לא המלצה)",
      "html": "<ul><li>פרופיל משקיע 1 עם הסבר מפורט</li><li>פרופיל משקיע 2 עם הסבר מפורט</li></ul>"
    }}
  ]
}}

כללים חשובים:
1. כתוב בעברית בלבד
2. טון אינפורמטיבי ומעמיק, לא שיווקי
3. ללא המלצות קנייה/מכירה מפורשות
4. ללא הבטחות או תחזיות ודאיות
5. שפה פשוטה למתחילים אך מפורטת
6. כל סקשן חייב להיות בפורמט HTML תקני
7. התמקד בעובדות, מספרים, והתפתחויות אמיתיות

החזר רק JSON תקני, ללא טקסט נוסף.
"""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "אתה כותב פיננסי מומחה בכתיבת סקירות מניות בעברית למשקיעים מתחילים. אתה תמיד מחזיר JSON תקני בלבד."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            content = json.loads(response.choices[0].message.content)
            return content.get("sections", [])
            
        except Exception as e:
            logger.error(f"Error generating content: {e}")
            # Return minimal fallback sections
            return [
                {
                    "id": "tl_dr",
                    "title": "סקירה כללית",
                    "html": f"<p>לא הצלחנו ליצור תוכן אוטומטי עבור {company_name} ({symbol}). אנא נסה שוב מאוחר יותר.</p>"
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
                    "why": f"מחיר יעד קונצנזוס: ${targets['consensus']}, {round(upside)}% מעל המחיר הנוכחי",
                    "what_to_do": "בדוק את ההנחות מאחורי מחירי היעד",
                    "evidence": f"טווח יעדים: ${targets.get('low', 'N/A')} - ${targets.get('high', 'N/A')}"
                })
            elif upside < -10:
                insights.append({
                    "severity": "high",
                    "title": "מחיר מעל יעד האנליסטים",
                    "why": f"מחיר יעד קונצנזוס: ${targets['consensus']}, {round(abs(upside))}% מתחת למחיר הנוכחי",
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
