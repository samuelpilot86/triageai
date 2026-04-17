#!/usr/bin/env python3
"""
test_live.py — Integration test for the trIAge HF Space backend.

Usage:
    python test_live.py [--timeout 300]

Steps:
  1. Poll /api/health until the Space is up (post-rebuild)
  2. Stream /api/analyze/text with a small set of test feedbacks
  3. Assert all expected SSE events arrive without error
  4. Print a summary
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "https://samuelpilot-triageai.hf.space"

TEST_FEEDBACKS = [
    "The app crashes every time I try to upload a file larger than 10MB.",
    "Please add dark mode, my eyes hurt at night.",
    "Login with Google doesn't work on Android 14, I get a blank screen.",
    "The monthly price went up again with no notice, this is unacceptable.",
    "Onboarding is confusing, I had no idea how to create my first project.",
]

EXPECTED_EVENTS = {"categorization", "clustered", "report", "done"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _get(path: str, timeout: int = 5) -> dict:
    url = BASE_URL + path
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def poll_health(max_wait: int) -> float:
    """Poll /api/health every 3 s until OK or timeout. Returns elapsed seconds."""
    print(f"⏳ Waiting for Space to be healthy (max {max_wait}s, every 3s)…")
    start = time.time()
    attempt = 0
    while True:
        elapsed = time.time() - start
        if elapsed > max_wait:
            print(f"✗ Timed out after {elapsed:.0f}s waiting for /api/health")
            sys.exit(1)
        attempt += 1
        try:
            data = _get("/api/health")
            if data.get("status") == "ok":
                print(f"  ✓ Health OK after {elapsed:.0f}s ({attempt} attempts)")
                return elapsed
        except Exception as e:
            pass  # not up yet
        time.sleep(3)


def stream_analysis() -> list[tuple[str, dict]]:
    """POST to /api/analyze/text and collect all SSE events."""
    url = BASE_URL + "/api/analyze/text"
    payload = json.dumps({"feedbacks": TEST_FEEDBACKS}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    events: list[tuple[str, dict]] = []
    print(f"\n📡 Streaming analysis ({len(TEST_FEEDBACKS)} feedbacks)…")

    with urllib.request.urlopen(req, timeout=120) as resp:
        event_name = None
        for raw_line in resp:
            line = raw_line.decode("utf-8").rstrip("\n")
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: ") and event_name:
                try:
                    data = json.loads(line[len("data: "):])
                except json.JSONDecodeError:
                    data = {}
                events.append((event_name, data))
                _print_event(event_name, data)
                if event_name in ("done", "error"):
                    break
                event_name = None

    return events


def _print_event(name: str, data: dict) -> None:
    if name == "status":
        print(f"  → [{name}] {data.get('step')}: {data.get('message', '')}")
    elif name == "categorization":
        n = len(data.get("items", []))
        fallback = data.get("used_fallback", False)
        print(f"  → [{name}] {n} items, fallback={fallback}")
    elif name == "clustered":
        print(f"  → [{name}] {data.get('count')} clusters")
    elif name == "report":
        snippet = (data.get("text") or "")[:80].replace("\n", " ")
        print(f"  → [{name}] {snippet}…")
    elif name == "user_stories":
        print(f"  → [{name}] {len(data.get('cards', []))} cards")
    elif name == "done":
        print(f"  → [{name}] ✓")
    elif name == "error":
        print(f"  ✗ [{name}] {data.get('message', '')}")
    else:
        print(f"  → [{name}]")


def assert_events(events: list[tuple[str, dict]]) -> bool:
    received = {e for e, _ in events}
    ok = True

    # No error event
    errors = [(e, d) for e, d in events if e == "error"]
    if errors:
        for _, d in errors:
            print(f"\n✗ Error event received: {d.get('message', '')[:200]}")
        ok = False

    # All expected events present
    missing = EXPECTED_EVENTS - received
    if missing:
        print(f"\n✗ Missing events: {missing}")
        ok = False

    # categorization has items
    cats = [d for e, d in events if e == "categorization"]
    if cats and len(cats[0].get("items", [])) == 0:
        print("\n✗ categorization returned 0 items")
        ok = False

    # report text non-empty
    reports = [d for e, d in events if e == "report"]
    if reports and not (reports[0].get("text") or "").strip():
        print("\n✗ report text is empty")
        ok = False

    return ok


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=300, help="Max seconds to wait for health")
    parser.add_argument("--skip-health", action="store_true", help="Skip health polling (Space already up)")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  trIAge live integration test")
    print(f"  {BASE_URL}")
    print(f"{'='*60}\n")

    if not args.skip_health:
        poll_health(args.timeout)

    start = time.time()
    try:
        events = stream_analysis()
    except Exception as e:
        print(f"\n✗ Stream failed: {e}")
        sys.exit(1)

    elapsed = time.time() - start
    ok = assert_events(events)

    print(f"\n{'='*60}")
    if ok:
        print(f"  ✅ ALL CHECKS PASSED  ({elapsed:.1f}s)")
    else:
        print(f"  ❌ SOME CHECKS FAILED ({elapsed:.1f}s)")
    print(f"{'='*60}\n")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
