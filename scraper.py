"""
scraper.py — Extraction automatique d'avis utilisateurs depuis les app stores.

Note : Le scraping des marketplaces (Google Play, App Store) est en zone grise
vis-à-vis des CGU de ces plateformes. Ce module est destiné exclusivement à un
usage non-commercial, à des fins de recherche et démonstration (MVP portfolio).
"""

import asyncio
import requests
from typing import Optional

try:
    from google_play_scraper import reviews as gp_reviews, Sort
    GOOGLE_PLAY_AVAILABLE = True
except ImportError:
    GOOGLE_PLAY_AVAILABLE = False


# ------------------------------------------------------------------
# Catalogue d'applications (focus HealthTech)
# ------------------------------------------------------------------

APP_CATALOG = [
    {
        "id": 1,
        "name": "MyFitnessPal",
        "category": "Nutrition & Fitness",
        "play_id": "com.myfitnesspal.android",
        "ios_id": 321643882,
    },
    {
        "id": 2,
        "name": "Headspace",
        "category": "Méditation & Mindfulness",
        "play_id": "com.getsomeheadspace.android",
        "ios_id": 493145008,
    },
    {
        "id": 3,
        "name": "Calm",
        "category": "Sommeil & Méditation",
        "play_id": "com.calm.android",
        "ios_id": 571800810,
    },
    {
        "id": 4,
        "name": "Fitbit",
        "category": "Santé & Activité",
        "play_id": "com.fitbit.FitbitMobile",
        "ios_id": 462638897,
    },
    {
        "id": 5,
        "name": "Strava",
        "category": "Sport & Running",
        "play_id": "com.strava",
        "ios_id": 426826309,
    },
    {
        "id": 6,
        "name": "Noom",
        "category": "Poids & Coaching Santé",
        "play_id": "com.noom.android",
        "ios_id": 634598719,
    },
    {
        "id": 7,
        "name": "Flo",
        "category": "Santé Féminine",
        "play_id": "org.iggymedia.periodtracker",
        "ios_id": 1038369691,
    },
    {
        "id": 8,
        "name": "Clue",
        "category": "Santé Féminine",
        "play_id": "com.clue.android",
        "ios_id": 657189197,
    },
    {
        "id": 9,
        "name": "Sleep Cycle",
        "category": "Analyse du Sommeil",
        "play_id": "com.northcube.sleepcycle",
        "ios_id": 320606217,
    },
    {
        "id": 10,
        "name": "Lifesum",
        "category": "Nutrition & Régime",
        "play_id": "com.lifesum.lifesum",
        "ios_id": 286760398,
    },
    {
        "id": 11,
        "name": "BetterHelp",
        "category": "Santé Mentale",
        "play_id": "com.betterhelp",
        "ios_id": 1069395979,
    },
    {
        "id": 12,
        "name": "Doctolib",
        "category": "Télémédecine",
        "play_id": "fr.doctolib.www",
        "ios_id": 1234993343,
    },
    {
        "id": 13,
        "name": "Ada Health",
        "category": "Diagnostic IA",
        "play_id": "com.ada.app",
        "ios_id": 1099191424,
    },
    {
        "id": 14,
        "name": "Peloton",
        "category": "Fitness",
        "play_id": "com.onepeloton.carrot",
        "ios_id": 792750948,
    },
    {
        "id": 15,
        "name": "Nike Run Club",
        "category": "Running",
        "play_id": "com.nike.plusgps",
        "ios_id": 387771637,
    },
]

# Mots-clés qui déclenchent l'affichage du catalogue
APP_TRIGGER_KEYWORDS = {
    "apps", "app", "store", "marketplace", "app store", "google play",
    "play store", "applications", "/apps", "catalog", "catalogue",
    "avis", "reviews", "scraper",
}


# ------------------------------------------------------------------
# Helpers UI
# ------------------------------------------------------------------

def format_catalog_message() -> str:
    """Génère le message de présentation du catalogue."""
    lines = [
        "## 📱 Sélectionnez une application\n",
        "Récupération automatique des derniers avis utilisateurs depuis "
        "Google Play ou l'App Store.\n",
        "| # | Application | Catégorie |",
        "|---|-------------|-----------|",
    ]
    for app in APP_CATALOG:
        lines.append(f"| **{app['id']}** | {app['name']} | {app['category']} |")
    lines.append(
        "\n*Tapez le **numéro** (ex: `3`) ou le **nom** de l'app (ex: `calm`)*"
    )
    return "\n".join(lines)


def find_app(query: str) -> Optional[dict]:
    """Trouve une app dans le catalogue par numéro ou nom (partiel, insensible à la casse)."""
    query = query.strip()

    # Recherche par numéro
    if query.isdigit():
        target_id = int(query)
        for app in APP_CATALOG:
            if app["id"] == target_id:
                return app
        return None

    # Recherche par nom
    query_lower = query.lower()
    for app in APP_CATALOG:
        if query_lower in app["name"].lower():
            return app

    return None


# ------------------------------------------------------------------
# Fetchers
# ------------------------------------------------------------------

async def fetch_play_store_reviews(play_id: str, count: int = 50) -> list[str]:
    """Récupère les avis les plus récents depuis le Google Play Store."""
    if not GOOGLE_PLAY_AVAILABLE:
        raise ImportError("google-play-scraper non installé.")

    loop = asyncio.get_event_loop()
    result, _ = await loop.run_in_executor(
        None,
        lambda: gp_reviews(
            play_id,
            lang="en",
            count=count,
            sort=Sort.NEWEST,
        ),
    )
    return [r["content"] for r in result if r.get("content")]


async def fetch_app_store_reviews(ios_id: int, count: int = 50) -> list[str]:
    """Récupère les avis depuis l'App Store via le flux RSS public d'Apple."""
    url = (
        f"https://itunes.apple.com/rss/customerreviews/"
        f"id={ios_id}/sortBy=mostRecent/json"
    )
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        ),
    )
    response.raise_for_status()
    data = response.json()

    entries = data.get("feed", {}).get("entry", [])
    # La première entrée est souvent les métadonnées de l'app, pas un avis
    if entries and "im:rating" not in str(entries[0]):
        entries = entries[1:]

    reviews = []
    for entry in entries[:count]:
        content = entry.get("content", {}).get("label", "")
        if content and len(content) > 10:
            reviews.append(content)

    return reviews


async def fetch_reviews(app: dict, count: int = 50) -> tuple[list[str], str]:
    """
    Récupère les avis d'une app : essaie Google Play en premier, puis App Store.
    Retourne (liste_avis, source_utilisée).
    """
    # Tentative Google Play
    if app.get("play_id") and GOOGLE_PLAY_AVAILABLE:
        try:
            reviews = await fetch_play_store_reviews(app["play_id"], count)
            if reviews:
                return reviews, "Google Play"
        except Exception:
            pass

    # Tentative App Store
    if app.get("ios_id"):
        try:
            reviews = await fetch_app_store_reviews(app["ios_id"], count)
            if reviews:
                return reviews, "App Store"
        except Exception:
            pass

    return [], "aucune source disponible"
