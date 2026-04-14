"""
main.py — FastAPI backend for trIAge.
Exposes SSE streaming for analysis + REST endpoints for store data.
"""

import os
import json
import asyncio
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import pandas as pd

from agent import FeedbackTriageAgent
from scraper import (
    APP_STORE_CATEGORIES,
    GOOGLE_PLAY_CATEGORIES,
    fetch_play_store_reviews,
    fetch_app_store_reviews,
    fetch_appstore_top_apps,
    fetch_googleplay_top_apps,
    search_appstore_apps,
    search_googleplay_apps,
)

# ------------------------------------------------------------------
# App + CORS
# ------------------------------------------------------------------

app = FastAPI(title="trIAge API")

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Timing history (shared across all users, persisted to file)
# ------------------------------------------------------------------

_TIMINGS_FILE = Path("timings.json")
_MAX_TIMINGS = 3

# Separate history per step: {"categorization": [...], "report": [...]}
def _load_timings() -> dict:
    try:
        data = json.loads(_TIMINGS_FILE.read_text())
        # Migrate old flat list format
        if isinstance(data, list):
            return {"categorization": data[-_MAX_TIMINGS:], "report": []}
        return {k: v[-_MAX_TIMINGS:] for k, v in data.items()}
    except Exception:
        return {"categorization": [], "report": []}

_timing_history: dict = _load_timings()

def _save_timing(step: str, ms: int, n: int | None = None) -> None:
    global _timing_history
    entry: dict = {"ms": ms}
    if n is not None:
        entry["n"] = n
    if step not in _timing_history:
        _timing_history[step] = []
    _timing_history[step].append(entry)
    _timing_history[step] = _timing_history[step][-_MAX_TIMINGS:]
    try:
        _TIMINGS_FILE.write_text(json.dumps(_timing_history))
    except Exception:
        pass


# ------------------------------------------------------------------
# Agent factory
# ------------------------------------------------------------------

def get_agent() -> FeedbackTriageAgent:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured.")
    groq_api_key = os.environ.get("GROQ_API_KEY")
    return FeedbackTriageAgent(api_key=api_key, groq_api_key=groq_api_key)


# ------------------------------------------------------------------
# SSE helpers
# ------------------------------------------------------------------

def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def analysis_stream(feedbacks: list[str]) -> AsyncGenerator[str, None]:
    agent = get_agent()

    yield sse_event("status", {"step": "categorization", "message": f"Analyzing {len(feedbacks)} feedbacks…"})

    try:
        items, corrections, used_fallback = await agent.categorize_and_validate(feedbacks)
    except Exception as e:
        yield sse_event("error", {"message": str(e)})
        return

    yield sse_event("categorization", {
        "items": items,
        "corrections": corrections,
        "used_fallback": used_fallback,
    })

    yield sse_event("status", {"step": "report", "message": "Generating executive report…"})

    try:
        report, actions, report_fallback = await agent.generate_report(items)
    except Exception as e:
        yield sse_event("error", {"message": str(e)})
        return

    yield sse_event("report", {
        "text": report,
        "used_fallback": report_fallback,
    })

    if actions:
        yield sse_event("status", {"step": "report", "message": "Generating user story cards…"})
        try:
            cards, cards_fallback = await agent.generate_user_stories(items, actions)
            yield sse_event("user_stories", {
                "cards": cards,
                "used_fallback": cards_fallback,
            })
        except Exception:
            pass  # user stories are non-blocking — report is already shown

    yield sse_event("done", {})


# ------------------------------------------------------------------
# Analysis endpoint (SSE)
# ------------------------------------------------------------------

@app.post("/api/analyze/text")
async def analyze_text(body: dict):
    """Accepts { feedbacks: string[] } and streams results."""
    feedbacks = body.get("feedbacks", [])
    if not feedbacks or len(feedbacks) < 2:
        raise HTTPException(status_code=422, detail="At least 2 feedbacks required.")
    if len(feedbacks) > 100:
        feedbacks = feedbacks[:100]
    return StreamingResponse(analysis_stream(feedbacks), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.post("/api/analyze/csv")
async def analyze_csv(file: UploadFile = File(...)):
    """Accepts a CSV upload and streams results."""
    content = await file.read()
    import io
    df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")

    feedback_col = df.columns[0]
    for col in df.columns:
        if any(kw in col.lower() for kw in ["feedback", "comment", "review", "text", "texte", "avis"]):
            feedback_col = col
            break

    feedbacks = (
        df[feedback_col].dropna().astype(str).str.strip().tolist()
    )
    feedbacks = [f for f in feedbacks if f and f != "nan" and f.lower() != feedback_col.lower()]

    if len(feedbacks) < 2:
        raise HTTPException(status_code=422, detail="CSV must contain at least 2 feedbacks.")
    if len(feedbacks) > 100:
        feedbacks = feedbacks[:100]

    return StreamingResponse(analysis_stream(feedbacks), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.post("/api/analyze/store")
async def analyze_store(body: dict):
    """Accepts { app: AppCatalogEntry, store: 'googleplay'|'appstore' } and streams results."""
    app_entry = body.get("app")
    store = body.get("store", "googleplay")

    if not app_entry:
        raise HTTPException(status_code=422, detail="app is required.")

    feedbacks: list[str] = []

    async def stream():
        nonlocal feedbacks
        yield sse_event("status", {"step": "scraping", "message": f"Fetching reviews for {app_entry['name']}…"})
        try:
            if store == "googleplay":
                feedbacks = await fetch_play_store_reviews(app_entry["id"], count=100)
                source = "Google Play"
            else:
                feedbacks = await fetch_app_store_reviews(app_entry["id"], count=100)
                source = "App Store"
        except Exception as e:
            yield sse_event("error", {"message": f"Scraping failed: {str(e)}"})
            return

        if not feedbacks:
            yield sse_event("error", {"message": "No reviews found for this app."})
            return

        yield sse_event("scraped", {"count": len(feedbacks), "source": source})

        async for chunk in analysis_stream(feedbacks[:100]):
            yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


# ------------------------------------------------------------------
# Store catalog endpoints
# ------------------------------------------------------------------

@app.get("/api/store/categories")
async def get_categories(store: str = Query("googleplay")):
    """Returns available categories for the selected store."""
    if store == "googleplay":
        return {"categories": sorted(GOOGLE_PLAY_CATEGORIES)}
    else:
        return {"categories": sorted(APP_STORE_CATEGORIES.keys())}


@app.get("/api/store/apps")
async def get_apps(store: str = Query("googleplay"), category: str = Query(...)):
    """Returns top 10 apps for a given store + category (live, cached 24h)."""
    if store == "googleplay":
        apps = await fetch_googleplay_top_apps(category, count=10)
    else:
        apps = await fetch_appstore_top_apps(category, count=10)
    return {"apps": apps}


@app.get("/api/store/search")
async def search_apps(store: str = Query("googleplay"), q: str = Query(...)):
    """Search apps by name/keyword across Google Play or App Store."""
    if not q.strip():
        return {"apps": []}
    if store == "googleplay":
        apps = await search_googleplay_apps(q.strip(), count=8)
    else:
        apps = await search_appstore_apps(q.strip(), count=8)
    return {"apps": apps}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ------------------------------------------------------------------
# Timing history endpoints
# ------------------------------------------------------------------

@app.get("/api/timings")
async def get_timings(step: str = Query("categorization")):
    """Returns the last 3 timings for a given step (categorization or report)."""
    return {"timings": _timing_history.get(step, [])}


@app.post("/api/timings")
async def post_timing(body: dict):
    """Records a timing. Body: { step: str, ms: int, n?: int }"""
    step = body.get("step", "categorization")
    ms = body.get("ms")
    n = body.get("n")
    if not isinstance(ms, int) or ms <= 0:
        raise HTTPException(status_code=422, detail="ms must be a positive integer.")
    _save_timing(step, ms, n if isinstance(n, int) and n > 0 else None)
    return {"ok": True}
