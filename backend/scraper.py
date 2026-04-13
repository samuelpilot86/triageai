"""
scraper.py — Automated user review extraction from app stores.

Note: Scraping app marketplaces (Google Play, App Store) is a legal grey area
with respect to their Terms of Service. This module is intended exclusively for
non-commercial use, for research and demonstration purposes (portfolio MVP).
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
# App catalog (HealthTech focus)
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
        "category": "Meditation & Mindfulness",
        "play_id": "com.getsomeheadspace.android",
        "ios_id": 493145008,
    },
    {
        "id": 3,
        "name": "Calm",
        "category": "Sleep & Meditation",
        "play_id": "com.calm.android",
        "ios_id": 571800810,
    },
    {
        "id": 4,
        "name": "Fitbit",
        "category": "Health & Activity",
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
        "category": "Weight & Health Coaching",
        "play_id": "com.noom.android",
        "ios_id": 634598719,
    },
    {
        "id": 7,
        "name": "Flo",
        "category": "Women's Health",
        "play_id": "org.iggymedia.periodtracker",
        "ios_id": 1038369691,
    },
    {
        "id": 8,
        "name": "Clue",
        "category": "Women's Health",
        "play_id": "com.clue.android",
        "ios_id": 657189197,
    },
    {
        "id": 9,
        "name": "Sleep Cycle",
        "category": "Sleep Tracking",
        "play_id": "com.northcube.sleepcycle",
        "ios_id": 320606217,
    },
    {
        "id": 10,
        "name": "Lifesum",
        "category": "Nutrition & Diet",
        "play_id": "com.lifesum.lifesum",
        "ios_id": 286760398,
    },
    {
        "id": 11,
        "name": "BetterHelp",
        "category": "Mental Health",
        "play_id": "com.betterhelp",
        "ios_id": 1069395979,
    },
    {
        "id": 12,
        "name": "Doctolib",
        "category": "Telemedicine",
        "play_id": "fr.doctolib.www",
        "ios_id": 1234993343,
    },
    {
        "id": 13,
        "name": "Ada Health",
        "category": "AI Diagnostics",
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

# Keywords that trigger the catalog display
APP_TRIGGER_KEYWORDS = {
    "apps", "app", "store", "marketplace", "app store", "google play",
    "play store", "applications", "/apps", "catalog", "catalogue",
    "reviews", "scraper",
}


# ------------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------------

def format_catalog_message() -> str:
    """Generates the catalog presentation message."""
    lines = [
        "## 📱 Select an Application\n",
        "Automatically fetch the latest user reviews from "
        "Google Play or the App Store.\n",
        "| # | Application | Category |",
        "|---|-------------|----------|",
    ]
    for app in APP_CATALOG:
        lines.append(f"| **{app['id']}** | {app['name']} | {app['category']} |")
    lines.append(
        "\n*Type the **number** (e.g. `3`) or the **app name** (e.g. `calm`)*"
    )
    return "\n".join(lines)


def find_app(query: str) -> Optional[dict]:
    """Finds an app in the catalog by number or name (partial, case-insensitive)."""
    query = query.strip()

    # Search by number
    if query.isdigit():
        target_id = int(query)
        for app in APP_CATALOG:
            if app["id"] == target_id:
                return app
        return None

    # Search by name
    query_lower = query.lower()
    for app in APP_CATALOG:
        if query_lower in app["name"].lower():
            return app

    return None


# ------------------------------------------------------------------
# Fetchers
# ------------------------------------------------------------------

async def fetch_play_store_reviews(play_id: str, count: int = 50) -> list[str]:
    """Fetches the most recent reviews from the Google Play Store."""
    if not GOOGLE_PLAY_AVAILABLE:
        raise ImportError("google-play-scraper is not installed.")

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
    """Fetches reviews from the App Store via Apple's public RSS feed."""
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
    # First entry is often app metadata, not a review
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
    Fetches reviews for an app: tries Google Play first, then App Store.
    Returns (reviews_list, source_used).
    """
    # Try Google Play
    if app.get("play_id") and GOOGLE_PLAY_AVAILABLE:
        try:
            reviews = await fetch_play_store_reviews(app["play_id"], count)
            if reviews:
                return reviews, "Google Play"
        except Exception:
            pass

    # Try App Store
    if app.get("ios_id"):
        try:
            reviews = await fetch_app_store_reviews(app["ios_id"], count)
            if reviews:
                return reviews, "App Store"
        except Exception:
            pass

    return [], "no source available"
