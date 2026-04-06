"""
app.py - Interface Chainlit de l'agent trIAge
Deploye sur HuggingFace Spaces (Docker, port 7860).
"""

import os
import chainlit as cl
import pandas as pd

from agent import FeedbackTriageAgent

PRIORITY_EMOJI = {"Haute": "🔴", "Moyenne": "🟡", "Faible": "🟢"}
CATEGORY_EMOJI = {
    "Bug / Erreur": "🐛", "Feature Request": "✨", "UX / Ergonomie": "🎨",
    "Performance": "⚡", "Pricing / Tarification": "💰",
    "Onboarding / Documentation": "📚", "Support Client": "🎧",
    "Securite / Confidentialite": "🔒", "Autre": "📌",
}

WELCOME_MESSAGE = """# 🎯 trIAge — Agent de Triage de Feedback Produit

Bienvenue ! Je suis un **agent IA** specialise dans l'analyse de feedbacks utilisateurs.

---

### Comment utiliser cet outil

**Option 1 — Coller vos feedbacks**
Collez vos retours directement dans le chat, **un feedback par ligne**.

**Option 2 — Uploader un CSV**
Importez un fichier `.csv` avec une colonne `feedback`.

---

### Ce que je fais automatiquement

- 🏷️ **Categorise** chaque feedback (Bug, Feature Request, UX, Performance...)
- 🔥 **Priorise** avec justification (Haute / Moyenne / Faible)
- 😊 **Analyse le sentiment** (Positif / Neutre / Negatif)
- 🔍 **S'auto-corrige** — relit ses propres decisions et les revise si necessaire
- 📊 **Genere un rapport executif** avec Top 3 recommandations
- 💾 **Export CSV** des resultats

---

*Envoyez vos feedbacks pour demarrer !*
"""


@cl.on_chat_start
async def on_chat_start():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        await cl.Message(content="⚠️ GEMINI_API_KEY manquante. Ajoutez-la dans Settings > Repository secrets.").send()
        return
    agent = FeedbackTriageAgent(api_key=api_key)
    cl.user_session.set("agent", agent)
    await cl.Message(content=WELCOME_MESSAGE).send()


@cl.on_message
async def on_message(message: cl.Message):
    agent = cl.user_session.get("agent")
    if not agent:
        await cl.Message(content="⚠️ Session expiree. Rechargez la page.").send()
        return

    feedbacks = []

    if message.elements:
        for element in message.elements:
            if element.name.lower().endswith(".csv"):
                try:
                    df_input = pd.read_csv(element.path)
                    feedback_col = df_input.columns[0]
                    for col in df_input.columns:
                        if any(kw in col.lower() for kw in ["feedback", "comment", "review", "avis", "texte", "text"]):
                            feedback_col = col
                            break
                    feedbacks = df_input[feedback_col].dropna().astype(str).str.strip().tolist()
                    feedbacks = [f for f in feedbacks if f and f != "nan"]
                    await cl.Message(content=f"✅ **CSV importe** — {len(feedbacks)} feedbacks (colonne : `{feedback_col}`)").send()
                except Exception as e:
                    await cl.Message(content=f"❌ Erreur CSV : `{str(e)}`").send()
                    return

    if not feedbacks and message.content.strip():
        lines = [l.strip() for l in message.content.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            await cl.Message(content="💡 Entrez au moins 2 feedbacks, un par ligne.").send()
            return
        feedbacks = lines

    if not feedbacks:
        await cl.Message(content="💡 Collez vos feedbacks ou uploadez un CSV.").send()
        return

    if len(feedbacks) > 50:
        await cl.Message(content=f"⚠️ Limite : 50 premiers feedbacks sur {len(feedbacks)}.").send()
        feedbacks = feedbacks[:50]

    # -------------------------------------------------------
    # Execution de l'agent en 4 etapes visibles
    # -------------------------------------------------------

    # Etape 1 : Lecture
    async with cl.Step(name="📥 Lecture des feedbacks", type="tool") as step:
        step.output = f"**{len(feedbacks)} feedbacks** recus et prets a l'analyse."

    # Etape 2 : Categorisation
    items = []
    async with cl.Step(name="🏷️ Categorisation & Priorisation", type="llm") as step:
        step.input = f"Analyse de {len(feedbacks)} feedbacks avec Gemini 1.5 Flash..."
        try:
            items = await agent.categorize_feedbacks(feedbacks)
            step.output = f"✅ {len(items)} feedbacks categorises."
        except Exception as e:
            step.output = f"❌ Erreur : {str(e)}"
            await cl.Message(content=f"❌ Erreur categorisation : `{str(e)}`").send()
            return

    # Etape 3 : Auto-validation agentique
    corrections = []
    async with cl.Step(name="🔍 Auto-validation & Corrections", type="tool") as step:
        step.input = "L'agent relit ses propres categorisations..."
        try:
            items, corrections = await agent.validate_and_correct(items)
            if corrections:
                lines = [f"**{len(corrections)} correction(s) effectuee(s) :**"]
                for c in corrections:
                    field_label = {"category": "categorie", "priority": "priorite", "sentiment": "sentiment"}.get(c.get("field", ""), c.get("field", ""))
                    lines.append(f"- Feedback #{c.get('id')} — {field_label} : `{c.get('old_value')}` → **{c.get('new_value')}** *({c.get('reason', '')})*")
                step.output = "\n".join(lines)
            else:
                step.output = "✅ Aucune correction — categorisations validees."
        except Exception as e:
            step.output = f"⚠️ Auto-validation ignoree : {str(e)}"

    # Etape 4 : Rapport
    report = ""
    async with cl.Step(name="📊 Generation du rapport executif", type="llm") as step:
        step.input = "Redaction du rapport PM..."
        try:
            report = await agent.generate_report(items)
            step.output = "✅ Rapport genere."
        except Exception as e:
            step.output = f"❌ Erreur rapport : {str(e)}"

    # -------------------------------------------------------
    # Affichage des resultats
    # -------------------------------------------------------

    if items:
        rows = ["| # | Resume | Categorie | Priorite | Raison | Sentiment |", "|---|--------|-----------|----------|--------|-----------|"]
        for item in items:
            cat = item.get("category", "Autre")
            prio = item.get("priority", "Moyenne")
            rows.append(f"| {item.get('id','')} | {item.get('summary','')[:55]} | {CATEGORY_EMOJI.get(cat,'📌')} {cat} | {PRIORITY_EMOJI.get(prio,'🟡')} {prio} | {item.get('priority_reason','')} | {item.get('sentiment','')} |")
        await cl.Message(content="## 📋 Resultats detailles\n\n" + "\n".join(rows)).send()

    if items:
        df_r = pd.DataFrame(items)
        stats = ["### 📈 Statistiques\n", "**Par categorie :**"]
        for cat, count in df_r["category"].value_counts().items():
            stats.append(f"- {CATEGORY_EMOJI.get(cat,'📌')} {cat} — **{count}** ({round(count/len(items)*100)}%)")
        stats.append("\n**Par priorite :**")
        for prio, count in df_r["priority"].value_counts().items():
            stats.append(f"- {PRIORITY_EMOJI.get(prio,'🟡')} {prio} — **{count}**")
        stats.append("\n**Par sentiment :**")
        for sent, count in df_r["sentiment"].value_counts().items():
            emoji = "😊" if sent == "Positif" else ("😐" if sent == "Neutre" else "😞")
            stats.append(f"- {emoji} {sent} — **{count}**")
        await cl.Message(content="\n".join(stats)).send()

    if report:
        await cl.Message(content=f"## 🎯 Rapport Executif\n\n{report}").send()

    if items:
        df_export = pd.DataFrame(items)
        tmp_path = "/tmp/triageai_results.csv"
        df_export.to_csv(tmp_path, index=False, encoding="utf-8-sig")
        elements = [cl.File(name="triageai_results.csv", path=tmp_path, display="inline")]
        await cl.Message(content="💾 **Export CSV pret :**", elements=elements).send()

    await cl.Message(content="✅ **Analyse terminee !** Envoyez de nouveaux feedbacks pour relancer.").send()
