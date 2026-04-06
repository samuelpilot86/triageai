"""
agent.py — Logique de l'agent de triage de feedback produit
Utilise Google Gemini 1.5 Flash (free tier) pour catégoriser et prioriser les feedbacks.
"""

import google.generativeai as genai
import json
import re
import pandas as pd


# Catégories disponibles pour le triage
CATEGORIES = [
    "Bug / Erreur",
    "Feature Request",
    "UX / Ergonomie",
    "Performance",
    "Pricing / Tarification",
    "Onboarding / Documentation",
    "Support Client",
    "Sécurité / Confidentialité",
    "Autre",
]


class FeedbackTriageAgent:
    """Agent de triage de feedback produit alimenté par Gemini 1.5 Flash."""

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    # ------------------------------------------------------------------
    # Étape 1 : Catégorisation & Priorisation
    # ------------------------------------------------------------------

    async def categorize_feedbacks(self, feedbacks: list[str]) -> list[dict]:
        """
        Envoie tous les feedbacks en un seul appel LLM et retourne
        une liste de dicts structurés (catégorie, priorité, sentiment…).
        """
        feedbacks_numbered = "\n".join(
            [f"{i + 1}. {f}" for i, f in enumerate(feedbacks)]
        )
        categories_str = ", ".join(CATEGORIES)

        prompt = f"""Tu es un expert en analyse de feedback produit. Analyse ces {len(feedbacks)} feedbacks utilisateurs.

FEEDBACKS :
{feedbacks_numbered}

Pour chaque feedback, retourne un objet avec ces champs :
- id          : numéro du feedback (entier, commence à 1)
- original    : texte original exact du feedback
- summary     : résumé synthétique en 6 mots maximum
- category    : UNE des catégories suivantes : {categories_str}
- priority    : "Haute", "Moyenne" ou "Faible"
  * Haute    = impact fort sur la rétention ou l'acquisition, ou problème bloquant
  * Moyenne  = gêne significative mais contournable
  * Faible   = amélioration cosmétique ou rare
- priority_reason : justification de la priorité en 10 mots maximum
- sentiment   : "Positif", "Neutre" ou "Négatif"

IMPORTANT : Retourne UNIQUEMENT ce JSON valide, sans markdown, sans texte autour :
{{
  "feedbacks": [
    {{
      "id": 1,
      "original": "...",
      "summary": "...",
      "category": "...",
      "priority": "...",
      "priority_reason": "...",
      "sentiment": "..."
    }}
  ]
}}"""

        response = await self.model.generate_content_async(prompt)
        return self._parse_json_response(response.text).get("feedbacks", [])

    # ------------------------------------------------------------------
    # Étape 2 : Rapport exécutif
    # ------------------------------------------------------------------

    async def generate_report(self, items: list[dict]) -> str:
        """
        Génère un rapport exécutif PM à partir des feedbacks catégorisés.
        """
        df = pd.DataFrame(items)

        category_stats = df["category"].value_counts().to_dict()
        priority_stats = df["priority"].value_counts().to_dict()
        sentiment_stats = df["sentiment"].value_counts().to_dict()

        high_priority = (
            df[df["priority"] == "Haute"][["summary", "category"]]
            .head(5)
            .to_dict("records")
        )

        prompt = f"""Tu es un Product Manager senior. Génère un rapport exécutif basé sur cette analyse de {len(items)} feedbacks utilisateurs.

STATISTIQUES :
- Par catégorie : {json.dumps(category_stats, ensure_ascii=False)}
- Par priorité  : {json.dumps(priority_stats, ensure_ascii=False)}
- Par sentiment : {json.dumps(sentiment_stats, ensure_ascii=False)}
- Feedbacks haute priorité : {json.dumps(high_priority, ensure_ascii=False)}

Génère le rapport avec EXACTEMENT cette structure markdown :

## Synthèse
[2-3 phrases sur l'état général du produit perçu par les utilisateurs. Mentionne le ratio sentiment et la catégorie dominante.]

## Top 3 des actions recommandées
1. **[Action]** — [Justification courte orientée impact produit]
2. **[Action]** — [Justification courte orientée impact produit]
3. **[Action]** — [Justification courte orientée impact produit]

## Signal faible à surveiller
[1 insight non évident, tendance émergente ou risque sous-estimé à investiguer davantage]

Sois concis, factuel et orienté décision. Ton de consultant produit senior."""

        response = await self.model.generate_content_async(prompt)
        return response.text

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _parse_json_response(self, text: str) -> dict:
        """Nettoie et parse la réponse JSON du LLM."""
        text = text.strip()
        # Supprime les blocs de code markdown si présents
        text = re.sub(r"```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```", "", text)
        text = text.strip()
        return json.loads(text)
