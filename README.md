---
title: TriageAI
emoji: 🎯
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# 🎯 TriageAI — Agent de Triage de Feedback Produit

Un agent IA qui catégorise, priorise et analyse vos feedbacks utilisateurs en quelques secondes.

Construit avec **Chainlit** + **Google Gemini 1.5 Flash** + **HuggingFace Spaces**.

---

## Fonctionnalités

- 🏷️ Catégorisation automatique (Bug, Feature Request, UX, Performance…)
- 🔥 Priorisation avec justification (Haute / Moyenne / Faible)
- 😊 Analyse de sentiment (Positif / Neutre / Négatif)
- 📊 Rapport exécutif avec Top 3 recommandations
- 💾 Export CSV des résultats

---

## Déploiement sur HuggingFace Spaces

### Étape 1 — Obtenir une clé Gemini (gratuit)

1. Allez sur [aistudio.google.com](https://aistudio.google.com/app/apikey)
2. Cliquez sur **Create API Key**
3. Copiez la clé générée

### Étape 2 — Créer le Space HuggingFace

1. Allez sur [huggingface.co/new-space](https://huggingface.co/new-space)
2. Choisissez un nom : `triageai`
3. Sélectionnez **Docker** comme SDK
4. Cliquez sur **Create Space**

### Étape 3 — Ajouter la clé API comme secret

1. Dans votre Space, allez dans **Settings → Repository secrets**
2. Cliquez sur **New secret**
3. Nom : `GEMINI_API_KEY`
4. Valeur : votre clé Gemini
5. Cliquez sur **Add secret**

### Étape 4 — Pousser le code

```bash
# Cloner votre Space HuggingFace
git clone https://huggingface.co/spaces/VOTRE_USERNAME/triageai

# Copier les fichiers du projet
cp -r triageai/* triageai/

# Push vers HuggingFace (déclenche le build Docker automatiquement)
cd triageai
git add .
git commit -m "Initial deploy"
git push
```

Le build prend environ 2-3 minutes. Votre app est ensuite accessible à :
`https://huggingface.co/spaces/VOTRE_USERNAME/triageai`

---

## Utilisation

**Option 1 — Texte**
Collez vos feedbacks dans le chat, un par ligne (minimum 2).

**Option 2 — CSV**
Uploadez un fichier `.csv` avec une colonne `feedback`. Le fichier `sample_feedbacks.csv` est fourni pour tester immédiatement.

**Option 3 — App Store / Google Play** *(nouveau)*
Tapez `apps` dans le chat pour afficher le catalogue de 15 applications HealthTech.
L'agent récupère automatiquement les avis les plus récents depuis Google Play (en priorité) ou l'App Store (en fallback), puis lance l'analyse.

> ⚠️ **Note légale** : la récupération d'avis depuis les marketplaces est en zone grise vis-à-vis des CGU de Google et Apple. Ce projet est exclusivement à visée non-commerciale (démonstration portfolio). Les auteurs déclinent toute responsabilité quant à un usage contraire aux conditions d'utilisation des plateformes concernées.

---

## Structure du projet

```
triageai/
├── app.py                  # Interface Chainlit + orchestration
├── agent.py                # Logique LLM (Gemini 1.5 Flash)
├── scraper.py              # Extraction d'avis App Store / Google Play
├── requirements.txt        # Dépendances Python
├── Dockerfile              # Configuration HuggingFace Spaces
├── sample_feedbacks.csv    # Données de test
└── .chainlit/
    └── config.toml         # Configuration UI Chainlit
```

---

## Stack technique

| Composant | Technologie | Coût |
|-----------|-------------|------|
| UI + Backend | Chainlit | Gratuit (open source) |
| Hébergement | HuggingFace Spaces | Gratuit |
| LLM | Gemini 1.5 Flash | Gratuit (1500 req/jour) |
| Data | Pandas | Gratuit (open source) |
| Scraping Play Store | google-play-scraper | Gratuit (open source) |
| Scraping App Store | Apple RSS API (public) | Gratuit |

**Coût total : 0€/mois**
