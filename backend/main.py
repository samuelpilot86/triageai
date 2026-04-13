"""
main.py — FastAPI backend for trIAge.
Exposes SSE streaming for analysis + REST endpoints for store data.
"""

import os
import json
import asyncio
from typing import AsyncGenerator

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import pandas as pd

from agent import FeedbackTriageAgent
from scraper import (
    APP_STORE_CATEGORIES,
    GOOGLE_PLAY_CATEGORIES,
    fetch_play_store_reviews,
    fetch_app_store_reviews,
    fetch_appstore_top_apps,
    fetch_googleplay_top_apps,
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
        report, report_fallback = await agent.generate_report(items)
    except Exception as e:
        yield sse_event("error", {"message": str(e)})
        return

    yield sse_event("report", {
        "text": report,
        "used_fallback": report_fallback,
    })

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
    if len(feedbacks) > 50:
        feedbacks = feedbacks[:50]
    return EventSourceResponse(analysis_stream(feedbacks))


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
    if len(feedbacks) > 50:
        feedbacks = feedbacks[:50]

    return EventSourceResponse(analysis_stream(feedbacks))


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
                feedbacks = await fetch_play_store_reviews(app_entry["id"], count=50)
                source = "Google Play"
            else:
                feedbacks = await fetch_app_store_reviews(app_entry["id"], count=50)
                source = "App Store"
        except Exception as e:
            yield sse_event("error", {"message": f"Scraping failed: {str(e)}"})
            return

        if not feedbacks:
            yield sse_event("error", {"message": "No reviews found for this app."})
            return

        yield sse_event("scraped", {"count": len(feedbacks), "source": source})

        async for chunk in analysis_stream(feedbacks[:50]):
            yield chunk

    return EventSourceResponse(stream())


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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
