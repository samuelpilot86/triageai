"""
agent.py — Logique de l'agent de triage de feedback produit
Utilise Google Gemini 2.5 Flash via le SDK officiel google-genai.
"""

import json
import re
import pandas as pd
from google import genai


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
    """Agent de triage de feedback produit alimenté par Gemini 2.5 Flash."""

    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash-lite"

    # ------------------------------------------------------------------
    # Étape 1 : Catégorisation & Auto-validation (appel unique)
    # ------------------------------------------------------------------

    async def categorize_and_validate(
        self, feedbacks: list[str]
    ) -> tuple[list[dict], list[dict]]:
        """
        Catégorise les feedbacks ET s'auto-corrige en un seul appel LLM.
        Retourne (items_finaux, liste_des_corrections).
        """
        feedbacks_numbered = "\n".join(
            [f"{i + 1}. {f}" for i, f in enumerate(feedbacks)]
        )
        categories_str = ", ".join(CATEGORIES)

        prompt = f"""Tu es un expert en analyse de feedback produit. Travaille en deux temps.

FEEDBACKS À ANALYSER :
{feedbacks_numbered}

═══ PHASE 1 — CATÉGORISATION ═══
Pour chaque feedback, détermine :
- id          : numéro (entier, commence à 1)
- original    : texte original exact
- summary     : résumé synthétique en 6 mots maximum
- category    : UNE des catégories : {categories_str}
- priority    : "Haute", "Moyenne" ou "Faible"
  * Haute   = problème bloquant ou impact fort sur la rétention/acquisition
  * Moyenne = gêne significative mais contournable
  * Faible  = amélioration cosmétique ou cas rare
- priority_reason : justification en 10 mots maximum
- sentiment   : "Positif", "Neutre" ou "Négatif"

═══ PHASE 2 — AUTO-CORRECTION ═══
Relis tes propres décisions avec un regard critique :
- La catégorie est-elle vraiment la plus précise ?
- La priorité est-elle cohérente avec l'impact réel ?
- Le sentiment reflète-t-il bien le texte original ?
- Y a-t-il des incohérences entre feedbacks similaires ?
Applique les corrections directement dans les feedbacks finaux.

Retourne UNIQUEMENT ce JSON valide, sans markdown, sans texte autour :
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
  ],
  "corrections": [
    {{
      "id": <id du feedback corrigé>,
      "field": "category" | "priority" | "sentiment",
      "old_value": "valeur initiale",
      "new_value": "valeur corrigée",
      "reason": "justification en 10 mots max"
    }}
  ]
}}

Si aucune correction n'est nécessaire, retourne "corrections": [].
Sois sélectif : ne signale que les corrections vraiment justifiées."""

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        data = self._parse_json_response(self._extract_text(response))
        return data.get("feedbacks", []), data.get("corrections", [])

    # ------------------------------------------------------------------
    # Étape 3 : Rapport exécutif
    # ------------------------------------------------------------------

    async def generate_report(self, items: list[dict]) -> str:
        """Génère un rapport exécutif PM à partir des feedbacks catégorisés."""
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
[2-3 phrases sur l'état général du produit perçu par les utilisateurs.]

## Top 3 des actions recommandées
1. **[Action]** — [Justification courte orientée impact produit]
2. **[Action]** — [Justification courte orientée impact produit]
3. **[Action]** — [Justification courte orientée impact produit]

## Signal faible à surveiller
[1 insight non évident ou tendance émergente à investiguer]

Sois concis, factuel et orienté décision. Ton de consultant produit senior."""

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return self._extract_text(response)

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _extract_text(self, response) -> str:
        """Extrait le texte de la réponse, compatible avec les modèles thinking."""
        try:
            text = response.text
            if text:
                return text
        except (ValueError, AttributeError):
            pass
        try:
            parts = response.candidates[0].content.parts
            return "".join(
                p.text for p in parts
                if hasattr(p, "text") and p.text and not getattr(p, "thought", False)
            )
        except Exception:
            return ""

    def _parse_json_response(self, text: str) -> dict:
        """Nettoie et parse la réponse JSON du LLM."""
        if not text:
            return {}
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```", "", text)
        text = text.strip()
        return json.loads(text)
