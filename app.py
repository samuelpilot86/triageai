"""
app.py — Interface Chainlit de l'agent TriageAI
Déployé sur HuggingFace Spaces (Docker, port 7860).
"""

import os
import chainlit as cl
import pandas as pd

from agent import FeedbackTriageAgent

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

> 💡 Un fichier `sample_feedbacks.csv` est disponible dans le repo pour tester immédiatement.

---

### Ce que je fais automatiquement

- 🏷️ **Catégorise** chaque feedback (Bug, Feature Request, UX, Performance…)
- 🔥 **Priorise** avec justification (Haute / Moyenne / Faible)
- 😊 **Analyse le sentiment** (Positif / Neutre / Négatif)
- 📊 **Génère un rapport exécutif** avec Top 3 recommandations
- 💾 **Export CSV** des résultats téléchargeable

---

*Envoyez vos feedbacks pour démarrer l'analyse !*
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

    await cl.Message(content=WELCOME_MESSAGE).send()


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

    feedbacks: list[str] = []

    # --- Lecture d'un CSV uploadé ---
    if message.elements:
        for element in message.elements:
            if element.name.lower().endswith(".csv"):
                try:
                    df_input = pd.read_csv(element.path)

                    # Détection automatique de la colonne de feedback
                    feedback_col = df_input.columns[0]
                    for col in df_input.columns:
                        if any(
                            kw in col.lower()
                            for kw in ["feedback", "comment", "review", "avis", "texte", "text"]
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
    if not feedbacks and message.content.strip():
        lines = [
            line.strip()
            for line in message.content.strip().split("\n")
            if line.strip()
        ]

        if len(lines) < 2:
            await cl.Message(
                content=(
                    "💡 Entrez **au moins 2 feedbacks**, un par ligne.\n\n"
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
            content="💡 Collez vos feedbacks (un par ligne) ou uploadez un fichier CSV."
        ).send()
        return

    # Limite de sécurité pour le free tier Gemini
    if len(feedbacks) > 50:
        await cl.Message(
            content=(
                f"⚠️ **Limite appliquée** : les **50 premiers feedbacks** sur {len(feedbacks)} "
                f"seront analysés (limite du tier gratuit)."
            )
        ).send()
        feedbacks = feedbacks[:50]

    # ------------------------------------------------------------------
    # Exécution de l'agent — étapes visibles dans l'UI
    # ------------------------------------------------------------------

    async with cl.Step(name="📥 Lecture des feedbacks", type="tool") as step:
        step.output = f"**{len(feedbacks)} feedbacks** reçus et prêts à l'analyse."

    items: list[dict] = []
    async with cl.Step(name="🏷️ Catégorisation & Priorisation", type="llm") as step:
        step.input = f"Analyse de {len(feedbacks)} feedbacks avec Gemini 1.5 Flash…"
        try:
            items = await agent.categorize_feedbacks(feedbacks)
            step.output = f"✅ {len(items)} feedbacks catégorisés avec succès."
        except Exception as e:
            step.output = f"❌ Erreur : {str(e)}"
            await cl.Message(
                content=f"❌ **Erreur lors de la catégorisation**\n\n`{str(e)}`"
            ).send()
            return

    report = ""
    async with cl.Step(name="📊 Génération du rapport exécutif", type="llm") as step:
        step.input = "Rédaction du rapport PM…"
        try:
            report = await agent.generate_report(items)
            step.output = "✅ Rapport généré."
        except Exception as e:
            step.output = f"❌ Erreur rapport : {str(e)}"

    # ------------------------------------------------------------------
    # Affichage des résultats
    # ------------------------------------------------------------------

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
            stats.append(f"- {CATEGORY_EMOJI.get(cat, '📌')} {cat} — **{count}** ({pct}%)")

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
        await cl.Message(
            content="💾 **Export CSV prêt :**",
            elements=elements,
        ).send()

    await cl.Message(
        content="✅ **Analyse terminée !** Envoyez de nouveaux feedbacks pour relancer une analyse."
    ).send()
