"""
agent.py - Logique de l'agent de triage de feedback produit
Utilise Google Gemini 1.5 Flash (free tier).
"""

import google.generativeai as genai
import json
import re
import pandas as pd


CATEGORIES = [
    "Bug / Erreur",
    "Feature Request",
    "UX / Ergonomie",
    "Performance",
    "Pricing / Tarification",
    "Onboarding / Documentation",
    "Support Client",
    "Securite / Confidentialite",
    "Autre",
]


class FeedbackTriageAgent:

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    async def categorize_feedbacks(self, feedbacks: list[str]) -> list[dict]:
        feedbacks_numbered = "\n".join([f"{i+1}. {f}" for i, f in enumerate(feedbacks)])
        categories_str = ", ".join(CATEGORIES)
        prompt = f"""Tu es un expert en analyse de feedback produit. Analyse ces {len(feedbacks)} feedbacks.

FEEDBACKS :
{feedbacks_numbered}

Pour chaque feedback, retourne un objet JSON avec :
- id, original, summary (6 mots max), category (parmi: {categories_str}),
  priority (Haute/Moyenne/Faible), priority_reason (10 mots max), sentiment (Positif/Neutre/Negatif)

Retourne UNIQUEMENT ce JSON valide :
{{"feedbacks": [{{"id": 1, "original": "...", "summary": "...", "category": "...", "priority": "...", "priority_reason": "...", "sentiment": "..."}}]}}"""
        response = await self.model.generate_content_async(prompt)
        return self._parse_json_response(response.text).get("feedbacks", [])

    async def validate_and_correct(self, items: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        COMPORTEMENT AGENTIQUE : l'agent relit ses propres decisions et se corrige.
        Boucle de feedback reflexive = ce qui distingue un agent d'un simple pipeline LLM.
        """
        items_json = json.dumps(items, ensure_ascii=False, indent=2)
        categories_str = ", ".join(CATEGORIES)
        prompt = f"""Tu es un expert en analyse de feedback produit. Audite tes propres categorisations.

CATEGORISATIONS A AUDITER :
{items_json}

Identifie les erreurs :
- Categorie incorrecte parmi : {categories_str} ?
- Priorite incohérente avec l'impact produit ?
- Sentiment ne reflétant pas le texte ?

Retourne UNIQUEMENT ce JSON valide :
{{"corrections": [{{"id": 1, "field": "category|priority|sentiment", "old_value": "...", "new_value": "...", "reason": "..."}}]}}
Si tout est correct : {{"corrections": []}}
Sois selectif, ne corrige que les vraies erreurs."""
        response = await self.model.generate_content_async(prompt)
        data = self._parse_json_response(response.text)
        corrections = data.get("corrections", [])
        corrected_items = [dict(item) for item in items]
        for correction in corrections:
            for item in corrected_items:
                if item.get("id") == correction.get("id"):
                    item[correction["field"]] = correction["new_value"]
                    break
        return corrected_items, corrections

    async def generate_report(self, items: list[dict]) -> str:
        df = pd.DataFrame(items)
        category_stats = df["category"].value_counts().to_dict()
        priority_stats = df["priority"].value_counts().to_dict()
        sentiment_stats = df["sentiment"].value_counts().to_dict()
        high_priority = df[df["priority"] == "Haute"][["summary", "category"]].head(5).to_dict("records")
        prompt = f"""Tu es un Product Manager senior. Rapport executif sur {len(items)} feedbacks.

Stats : categories={json.dumps(category_stats, ensure_ascii=False)}, priorites={json.dumps(priority_stats, ensure_ascii=False)}, sentiments={json.dumps(sentiment_stats, ensure_ascii=False)}
Haute priorite : {json.dumps(high_priority, ensure_ascii=False)}

## Synthese
[2-3 phrases etat general]

## Top 3 des actions recommandees
1. **[Action]** - [Justification]
2. **[Action]** - [Justification]
3. **[Action]** - [Justification]

## Signal faible a surveiller
[1 insight non evident]"""
        response = await self.model.generate_content_async(prompt)
        return response.text

    def _parse_json_response(self, text: str) -> dict:
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```", "", text)
        return json.loads(text.strip())
