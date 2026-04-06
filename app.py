"""
app.py — Interface Chainlit de l'agent TriageAI
Déployé sur HuggingFace Spaces (Docker, port 7860).
"""

import os
import chainlit as cl
import pandas as pd

from agent import FeedbackTriageAgent
from scraper import (
    APP_CATALOG,
    APP_TRIGGER_KEYWORDS,
    format_catalog_message,
    find_app,
    fetch_reviews,
)

# ------------------------------------------------------------------
# Mapping visuels
# ------------------------------------------------------------------

PRIORITY_EMOJI = {"Haute": "🔴", "Moyenne": "🟡", "Faible": "🟢"}

CATEGORY_EMOJI = {
    "Bug / Erreur": "🐛",
    "Feature Request": "✨",
    "UX / Ergonomie": "🎨",
    "Performance": "⚡",
    "Pricing / Tarification": "💰",
    "Onboarding / Documentation": "📚",
    "Support Client": "🎧",
    "Sécurité / Confidentialité": "🔒",
    "Autre": "📌",
}

# ------------------------------------------------------------------
# Message de bienvenue
# ------------------------------------------------------------------

WELCOME_MESSAGE = """# 🎯 TriageAI — Agent de Triage de Feedback Produit

Bienvenue ! Je suis votre agent IA spécialisé dans l'analyse et la priorisation de feedbacks utilisateurs.

---

### Comment utiliser cet outil

**Option 1 — Coller vos feedbacks**
Collez vos retours directement dans le chat, **un feedback par ligne**.

**Option 2 — Uploader un CSV**
Importez un fichier `.csv` avec une colonne `feedback` (ou la première colonne sera utilisée automatiquement).

**Option 3 — Avis App Store / Google Play** *(nouveau !)*
Tapez `apps` pour afficher le catalogue de 15 applications et lancer une récupération automatique des avis.

> 💡 Un fichier `sample_feedbacks.csv` est disponible dans le repo pour tester immédiatement.

---

### Ce que je fais automatiquement

- 🏷️ **Catégorise** chaque feedback (Bug, Feature Request, UX, Performance…)
- 🔥 **Priorise** avec justification (Haute / Moyenne / Faible)
- 😊 **Analyse le sentiment** (Positif / Neutre / Négatif)
- 🔍 **S'auto-corrige** — relit ses propres décisions et les révise si nécessaire
- 📊 **Génère un rapport exécutif** avec Top 3 recommandations
- 💾 **Export CSV** des résultats téléchargeable

---

*Envoyez vos feedbacks, uploadez un CSV, ou tapez `apps` pour démarrer !*
"""

# ------------------------------------------------------------------
# Initialisation de la session
# ------------------------------------------------------------------


@cl.on_chat_start
async def on_chat_start():
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        await cl.Message(
            content=(
                "⚠️ **Configuration manquante**\n\n"
                "La variable d'environnement `GEMINI_API_KEY` n'est pas définie.\n\n"
                "**Sur HuggingFace Spaces :** allez dans *Settings → Repository secrets* "
                "et ajoutez `GEMINI_API_KEY` avec votre clé Google AI Studio.\n\n"
                "Obtenez une clé gratuite sur [aistudio.google.com](https://aistudio.google.com/app/apikey)."
            )
        ).send()
        return

    agent = FeedbackTriageAgent(api_key=api_key)
    cl.user_session.set("agent", agent)
    cl.user_session.set("mode", None)

    await cl.Message(content=WELCOME_MESSAGE).send()


# ------------------------------------------------------------------
# Pipeline principal (réutilisé par les 3 modes d'entrée)
# ------------------------------------------------------------------


async def _run_pipeline(feedbacks: list[str], agent: FeedbackTriageAgent) -> None:
    """Exécute les 4 étapes de l'agent sur une liste de feedbacks."""

    async with cl.Step(name="📥 Lecture des feedbacks", type="tool") as step:
        step.input = f"{len(feedbacks)} feedbacks reçus."
        step.output = f"**{len(feedbacks)} feedbacks** reçus et prêts à l'analyse."

    items: list[dict] = []
    categorization_error = None
    async with cl.Step(name="🏷️ Catégorisation & Priorisation", type="llm") as step:
        step.input = f"Analyse de {len(feedbacks)} feedbacks avec Gemini…"
        try:
            items = await agent.categorize_feedbacks(feedbacks)
            step.output = f"✅ {len(items)} feedbacks catégorisés avec succès."
        except Exception as e:
            categorization_error = str(e)
            step.output = f"❌ Erreur : {categorization_error}"

    if categorization_error:
        await cl.Message(
            content=f"❌ **Erreur lors de la catégorisation**\n\n`{categorization_error}`"
        ).send()
        return

    corrections = []
    async with cl.Step(name="🔍 Auto-validation & Corrections", type="tool") as step:
        step.input = "L'agent relit ses propres catégorisations…"
        try:
            items, corrections = await agent.validate_and_correct(items)
            if corrections:
                lines = [f"**{len(corrections)} correction(s) effectuée(s) :**"]
                for c in corrections:
                    field_label = {
                        "category": "catégorie",
                        "priority": "priorité",
                        "sentiment": "sentiment",
                    }.get(c.get("field", ""), c.get("field", ""))
                    lines.append(
                        f"- Feedback #{c.get('id')} — {field_label} : "
                        f"`{c.get('old_value')}` → **{c.get('new_value')}** "
                        f"*({c.get('reason', '')})*"
                    )
                step.output = "\n".join(lines)
            else:
                step.output = "✅ Aucune correction nécessaire — catégorisations validées."
        except Exception as e:
            step.output = f"⚠️ Auto-validation ignorée : {str(e)}"

    report = ""
    report_error = None
    async with cl.Step(name="📊 Génération du rapport exécutif", type="llm") as step:
        step.input = "Rédaction du rapport PM…"
        try:
            report = await agent.generate_report(items)
            step.output = "✅ Rapport généré."
        except Exception as e:
            report_error = str(e)
            step.output = f"❌ Erreur rapport : {report_error}"

    # Tableau détaillé
    if items:
        rows = [
            "| # | Résumé | Catégorie | Priorité | Raison | Sentiment |",
            "|---|--------|-----------|----------|--------|-----------|",
        ]
        for item in items:
            cat = item.get("category", "Autre")
            prio = item.get("priority", "Moyenne")
            rows.append(
                f"| {item.get('id', '')} "
                f"| {item.get('summary', '')[:55]} "
                f"| {CATEGORY_EMOJI.get(cat, '📌')} {cat} "
                f"| {PRIORITY_EMOJI.get(prio, '🟡')} {prio} "
                f"| {item.get('priority_reason', '')} "
                f"| {item.get('sentiment', '')} |"
            )
        await cl.Message(
            content="## 📋 Résultats détaillés\n\n" + "\n".join(rows)
        ).send()

    # Statistiques
    if items:
        df_r = pd.DataFrame(items)
        cat_counts = df_r["category"].value_counts()
        prio_counts = df_r["priority"].value_counts()
        sent_counts = df_r["sentiment"].value_counts()

        stats = ["### 📈 Statistiques\n"]
        stats.append("**Par catégorie :**")
        for cat, count in cat_counts.items():
            pct = round(count / len(items) * 100)
            stats.append(
                f"- {CATEGORY_EMOJI.get(cat, '📌')} {cat} — **{count}** ({pct}%)"
            )
        stats.append("\n**Par priorité :**")
        for prio, count in prio_counts.items():
            stats.append(f"- {PRIORITY_EMOJI.get(prio, '🟡')} {prio} — **{count}**")
        stats.append("\n**Par sentiment :**")
        for sent, count in sent_counts.items():
            emoji = "😊" if sent == "Positif" else ("😐" if sent == "Neutre" else "😞")
            stats.append(f"- {emoji} {sent} — **{count}**")

        await cl.Message(content="\n".join(stats)).send()

    # Rapport exécutif
    if report:
        await cl.Message(content=f"## 🎯 Rapport Exécutif\n\n{report}").send()

    # Export CSV
    if items:
        df_export = pd.DataFrame(items)
        tmp_path = "/tmp/triageai_results.csv"
        df_export.to_csv(tmp_path, index=False, encoding="utf-8-sig")
        elements = [
            cl.File(
                name="triageai_results.csv",
                path=tmp_path,
                display="inline",
            )
        ]
        await cl.Message(content="💾 **Export CSV prêt :**", elements=elements).send()

    await cl.Message(
        content="✅ **Analyse terminée !** Envoyez de nouveaux feedbacks pour relancer une analyse."
    ).send()


# ------------------------------------------------------------------
# Traitement des messages
# ------------------------------------------------------------------


@cl.on_message
async def on_message(message: cl.Message):
    agent: FeedbackTriageAgent | None = cl.user_session.get("agent")

    if not agent:
        await cl.Message(
            content="⚠️ Session expirée ou clé API manquante. Rechargez la page."
        ).send()
        return

    content = message.content.strip()
    content_lower = content.lower()

    # ------------------------------------------------------------------
    # Mode 3 — App Store / Google Play
    # ------------------------------------------------------------------

    # Déclencheur : l'utilisateur veut voir le catalogue
    if not message.elements and content_lower in APP_TRIGGER_KEYWORDS:
        await cl.Message(content=format_catalog_message()).send()
        cl.user_session.set("mode", "app_selection")
        return

    # Sélection d'une app dans le catalogue
    if cl.user_session.get("mode") == "app_selection" and not message.elements:
        app = find_app(content)

        if not app:
            await cl.Message(
                content=(
                    f"❌ Application introuvable : `{content}`\n\n"
                    f"Tapez un numéro entre **1** et **{len(APP_CATALOG)}** "
                    f"ou un nom d'app (ex: `calm`, `fitbit`).\n\n"
                    f"Tapez `apps` pour revoir la liste."
                )
            ).send()
            return

        cl.user_session.set("mode", None)

        feedbacks: list[str] = []
        source = ""
        async with cl.Step(
            name=f"🌐 Récupération des avis — {app['name']}", type="tool"
        ) as step:
            step.input = f"Scraping {app['name']} ({app['category']})…"
            try:
                feedbacks, source = await fetch_reviews(app, count=50)
                if feedbacks:
                    step.output = (
                        f"✅ **{len(feedbacks)} avis récupérés** depuis **{source}**."
                    )
                else:
                    step.output = "❌ Aucun avis récupéré (sources indisponibles)."
            except Exception as e:
                step.output = f"❌ Erreur : {str(e)}"

        if not feedbacks:
            await cl.Message(
                content=(
                    f"❌ **Impossible de récupérer les avis de {app['name']}**\n\n"
                    "Google Play et App Store sont tous les deux indisponibles "
                    "pour cette app.\n\n"
                    "Essayez une autre application ou collez vos feedbacks manuellement."
                )
            ).send()
            return

        await cl.Message(
            content=(
                f"✅ **{len(feedbacks)} avis récupérés** depuis **{source}** "
                f"pour **{app['name']}** ({app['category']})\n\n"
                f"Lancement de l'analyse…"
            )
        ).send()

        if len(feedbacks) > 50:
            feedbacks = feedbacks[:50]

        await _run_pipeline(feedbacks, agent)
        return

    # ------------------------------------------------------------------
    # Mode 1 & 2 — CSV uploadé ou texte collé (comportement original)
    # ------------------------------------------------------------------

    cl.user_session.set("mode", None)

    feedbacks: list[str] = []

    # --- Lecture d'un CSV uploadé ---
    if message.elements:
        for element in message.elements:
            if element.name.lower().endswith(".csv"):
                try:
                    df_input = pd.read_csv(element.path)

                    feedback_col = df_input.columns[0]
                    for col in df_input.columns:
                        if any(
                            kw in col.lower()
                            for kw in [
                                "feedback", "comment", "review",
                                "avis", "texte", "text",
                            ]
                        ):
                            feedback_col = col
                            break

                    feedbacks = (
                        df_input[feedback_col]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .tolist()
                    )
                    feedbacks = [f for f in feedbacks if f and f != "nan"]

                    await cl.Message(
                        content=(
                            f"✅ **CSV importé avec succès**\n\n"
                            f"- Fichier : `{element.name}`\n"
                            f"- Colonne utilisée : `{feedback_col}`\n"
                            f"- Feedbacks détectés : **{len(feedbacks)}**"
                        )
                    ).send()

                except Exception as e:
                    await cl.Message(
                        content=f"❌ **Erreur lors de la lecture du CSV**\n\n`{str(e)}`"
                    ).send()
                    return

    # --- Lecture du texte collé ---
    if not feedbacks and content:
        lines = [line.strip() for line in content.split("\n") if line.strip()]

        if len(lines) < 2:
            await cl.Message(
                content=(
                    "💡 Entrez **au moins 2 feedbacks**, un par ligne — "
                    "ou tapez `apps` pour récupérer des avis depuis l'App Store / Google Play.\n\n"
                    "Exemple :\n"
                    "```\n"
                    "L'application plante au démarrage sur iOS\n"
                    "Il manque un mode sombre, c'est fatiguant la nuit\n"
                    "Le temps de chargement est beaucoup trop lent\n"
                    "```"
                )
            ).send()
            return

        feedbacks = lines

    if not feedbacks:
        await cl.Message(
            content=(
                "💡 Collez vos feedbacks (un par ligne), uploadez un CSV, "
                "ou tapez `apps` pour récupérer des avis automatiquement."
            )
        ).send()
        return

    if len(feedbacks) > 50:
        await cl.Message(
            content=(
                f"⚠️ **Limite appliquée** : les **50 premiers feedbacks** sur {len(feedbacks)} "
                f"seront analysés (limite du tier gratuit)."
            )
        ).send()
        feedbacks = feedbacks[:50]

    await _run_pipeline(feedbacks, agent)
