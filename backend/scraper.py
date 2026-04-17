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
            for r in results
            if r.get("appId") and r.get("title")
        ][:count]
        _cache_set(cache_key, apps)
        return apps
    except Exception:
        return []


# ------------------------------------------------------------------
# Search by name
# ------------------------------------------------------------------

async def search_googleplay_apps(query: str, count: int = 8) -> list[dict]:
    """Search Google Play apps by name/keyword."""
    if not GOOGLE_PLAY_AVAILABLE:
        return []
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(
            None,
            lambda: gp_search(query, n_hits=count, lang="en", country="us"),
        )

        # Resolve missing appIds (bug in library for featured apps like Google Maps)
        resolved = []
        unresolved = []
        for r in results:
            if r.get("appId") and r.get("title"):
                resolved.append({"id": r["appId"], "name": r["title"], "store": "googleplay"})
            elif r.get("title") and r.get("developer"):
                unresolved.append(r)

        for r in unresolved:
            try:
                fallback = await loop.run_in_executor(
                    None,
                    lambda title=r["title"], dev=r["developer"]: gp_search(
                        f"{title} {dev}", n_hits=3, lang="en", country="us"
                    ),
                )
                match = next(
                    (f for f in fallback if f.get("appId") and f.get("title") == r["title"]),
                    None,
                )
                if match:
                    resolved.append({"id": match["appId"], "name": match["title"], "store": "googleplay"})
            except Exception:
                pass

        return resolved[:count]
    except Exception:
        return []


async def search_appstore_apps(query: str, count: int = 8) -> list[dict]:
    """Search App Store apps by name/keyword via iTunes Search API."""
    loop = asyncio.get_event_loop()
    try:
        url = (
            f"https://itunes.apple.com/search"
            f"?term={requests.utils.quote(query)}&entity=software&limit={count}&country=us"
        )
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}),
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [
            {"id": str(r["trackId"]), "name": r["trackName"], "store": "appstore"}
            for r in results[:count]
        ]
    except Exception:
        return []


# ------------------------------------------------------------------
# Review fetchers
# ------------------------------------------------------------------

# Locales tried in order when the primary locale returns too few reviews.
# Google Play: (lang, country). App Store: just country codes.
PLAY_LOCALES = [("en", "us"), ("fr", "fr"), ("en", "gb"), ("es", "es"), ("de", "de")]
APPSTORE_COUNTRIES = ["us", "fr", "gb", "es", "de"]


async def fetch_play_store_reviews(play_id: str, count: int = 50) -> list[str]:
    """Fetches the most recent reviews from Google Play, with multilingual fallback.

    Tries locales in PLAY_LOCALES order; accumulates reviews until `count` is reached
    or locales are exhausted. De-duplicates identical review bodies across locales.
    """
    if not GOOGLE_PLAY_AVAILABLE:
        raise ImportError("google-play-scraper is not installed.")

    loop = asyncio.get_event_loop()
    collected: list[str] = []
    seen: set[str] = set()

    for lang, country in PLAY_LOCALES:
        if len(collected) >= count:
            break
        remaining = count - len(collected)
        try:
            result, _ = await loop.run_in_executor(
                None,
                lambda l=lang, c=country, n=remaining: gp_reviews(
                    play_id, lang=l, country=c, count=n, sort=Sort.NEWEST,
                ),
            )
        except Exception:
            continue
        for r in result:
            body = (r.get("content") or "").strip()
            if body and body not in seen:
                seen.add(body)
                collected.append(body)
                if len(collected) >= count:
                    break

    return collected


async def fetch_app_store_reviews(ios_id: str, count: int = 50) -> list[str]:
    """Fetches reviews from the App Store RSS feed, with country fallback."""
    loop = asyncio.get_event_loop()
    collected: list[str] = []
    seen: set[str] = set()

    for country in APPSTORE_COUNTRIES:
        if len(collected) >= count:
            break
        url = (
            f"https://itunes.apple.com/{country}/rss/customerreviews/"
            f"id={ios_id}/sortBy=mostRecent/json"
        )
        try:
            response = await loop.run_in_executor(
                None,
                lambda u=url: requests.get(u, timeout=15, headers={"User-Agent": "Mozilla/5.0"}),
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            continue

        entries = data.get("feed", {}).get("entry", [])
        if entries and "im:rating" not in str(entries[0]):
            entries = entries[1:]

        for entry in entries:
            if len(collected) >= count:
                break
            content = (entry.get("content", {}).get("label") or "").strip()
            if len(content) > 10 and content not in seen:
                seen.add(content)
                collected.append(content)

    return collected
