"""
scraper.py — Automated user review extraction from app stores.

Note: Scraping app marketplaces (Google Play, App Store) is a legal grey area
with respect to their Terms of Service. This module is intended exclusively for
non-commercial use, for research and demonstration purposes (portfolio MVP).
"""

import asyncio
import json
import time
import requests
from typing import Optional

try:
    from google_play_scraper import reviews as gp_reviews, Sort, search as gp_search
    GOOGLE_PLAY_AVAILABLE = True
except ImportError:
    GOOGLE_PLAY_AVAILABLE = False


# ------------------------------------------------------------------
# App Store category map (iTunes genre IDs)
# ------------------------------------------------------------------

APP_STORE_CATEGORIES: dict[str, int] = {
    "Books": 6018,
    "Business": 6000,
    "Developer Tools": 6026,
    "Education": 6017,
    "Entertainment": 6016,
    "Finance": 6015,
    "Food & Drink": 6023,
    "Games": 6014,
    "Graphics & Design": 6027,
    "Health & Fitness": 6013,
    "Lifestyle": 6012,
    "Medical": 6020,
    "Music": 6011,
    "Navigation": 6010,
    "News": 6009,
    "Photo & Video": 6008,
    "Productivity": 6007,
    "Reference": 6006,
    "Shopping": 6024,
    "Social Networking": 6005,
    "Sports": 6004,
    "Travel": 6003,
    "Utilities": 6002,
    "Weather": 6001,
}

# Google Play category slugs (used with search fallback)
GOOGLE_PLAY_CATEGORIES: list[str] = [
    "Art & Design",
    "Auto & Vehicles",
    "Beauty",
    "Books & Reference",
    "Business",
    "Comics",
    "Communication",
    "Dating",
    "Education",
    "Entertainment",
    "Events",
    "Finance",
    "Food & Drink",
    "Games",
    "Health & Fitness",
    "House & Home",
    "Libraries & Demo",
    "Lifestyle",
    "Maps & Navigation",
    "Medical",
    "Music & Audio",
    "News & Magazines",
    "Parenting",
    "Personalization",
    "Photography",
    "Productivity",
    "Shopping",
    "Social",
    "Sports",
    "Tools",
    "Travel & Local",
    "Video Players & Editors",
    "Weather",
]


# ------------------------------------------------------------------
# Simple TTL cache for store rankings (24h)
# ------------------------------------------------------------------

_cache: dict[str, tuple[float, list]] = {}
_CACHE_TTL = 86_400  # 24 hours


def _cache_get(key: str) -> Optional[list]:
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, value: list) -> None:
    _cache[key] = (time.time(), value)


# ------------------------------------------------------------------
# App Store — top apps by category
# ------------------------------------------------------------------

async def fetch_appstore_top_apps(category: str, count: int = 10) -> list[dict]:
    """Returns top free apps for a given App Store category."""
    genre_id = APP_STORE_CATEGORIES.get(category)
    if not genre_id:
        return []

    cache_key = f"appstore:{category}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"https://itunes.apple.com/us/rss/topfreeapplications/limit={count}/genre={genre_id}/json"
    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}),
        )
        response.raise_for_status()
        data = response.json()
        entries = data.get("feed", {}).get("entry", [])
        apps = [
            {
                "id": e["id"]["attributes"]["im:id"],
                "name": e["im:name"]["label"],
                "store": "appstore",
            }
            for e in entries
        ]
        _cache_set(cache_key, apps)
        return apps
    except Exception:
        return []


# ------------------------------------------------------------------
# Google Play — top apps by category (via search)
# ------------------------------------------------------------------

async def fetch_googleplay_top_apps(category: str, count: int = 10) -> list[dict]:
    """Returns top apps for a given Google Play category via search."""
    if not GOOGLE_PLAY_AVAILABLE:
        return []

    cache_key = f"googleplay:{category}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(
            None,
            lambda: gp_search(category, n_hits=count, lang="en", country="us"),
        )
        apps = [
            {
                "id": r["appId"],
                "name": r["title"],
                "store": "googleplay",
            }
            for r in results[:count]
        ]
        _cache_set(cache_key, apps)
        return apps
    except Exception:
        return []


# ------------------------------------------------------------------
# Review fetchers
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


async def fetch_app_store_reviews(ios_id: str, count: int = 50) -> list[str]:
    """Fetches reviews from the App Store via Apple's public RSS feed."""
    url = (
        f"https://itunes.apple.com/rss/customerreviews/"
        f"id={ios_id}/sortBy=mostRecent/json"
    )
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}),
    )
    response.raise_for_status()
    data = response.json()

    entries = data.get("feed", {}).get("entry", [])
    if entries and "im:rating" not in str(entries[0]):
        entries = entries[1:]

    reviews = []
    for entry in entries[:count]:
        content = entry.get("content", {}).get("label", "")
        if content and len(content) > 10:
            reviews.append(content)

    return reviews
