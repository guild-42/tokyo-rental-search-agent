"""FastAPI server for the rental search web service."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import get_active_properties, get_stats, init_db, prune_rent_cap, prune_wards

logger = logging.getLogger(__name__)

# --- Configuration via environment variables ---
# FETCH_SCHEDULE_HOURS: comma-separated hours to run fetch (default: "9,12,15,18,21")
# FETCH_MAX_PAGES: max pages per source per fetch (default: 10)
# FETCH_WARD_CODES: comma-separated ward codes to fetch (default: all)
# DB_PATH: path to SQLite database (default: data/rental.db)
# MAX_AGE_DAYS: max age of properties to display (default: 7)

_PROJECT_DIR = Path(__file__).parent.parent
_db_conn = None
_fetch_task = None
_fetch_lock = asyncio.Lock()


def _get_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", str(_PROJECT_DIR / "data" / "rental.db")))


def _get_schedule_hours() -> list[int]:
    raw = os.environ.get("FETCH_SCHEDULE_HOURS", "9,12,15,18,21")
    return sorted(int(h.strip()) for h in raw.split(",") if h.strip())


def _get_max_age_days() -> int:
    return int(os.environ.get("MAX_AGE_DAYS", "7"))


def _get_interval_minutes() -> int | None:
    """Return the fetch interval in minutes.

    Preference order:
      1. FETCH_INTERVAL_MINUTES (new, supports sub-hour cycles)
      2. FETCH_INTERVAL_HOURS (legacy, integer hours)
    Returns None if neither is set to a valid positive value.
    """
    minutes_raw = os.environ.get("FETCH_INTERVAL_MINUTES", "").strip()
    if minutes_raw.isdigit() and int(minutes_raw) > 0:
        return int(minutes_raw)
    hours_raw = os.environ.get("FETCH_INTERVAL_HOURS", "").strip()
    if hours_raw.isdigit() and int(hours_raw) > 0:
        return int(hours_raw) * 60
    return None


async def _run_fetch_once(ward_codes, max_pages):
    from .orchestrator import fetch_all

    if _fetch_lock.locked():
        logger.warning("Previous fetch still running — skipping this cycle")
        return
    async with _fetch_lock:
        started = datetime.now()
        try:
            logger.info("Scheduled fetch starting...")
            db_path = _get_db_path()
            result = await fetch_all(db_path, ward_codes=ward_codes, max_pages=max_pages)
            elapsed = (datetime.now() - started).total_seconds()
            logger.info(
                f"Scheduled fetch complete in {elapsed:.0f}s: "
                f"{result.total_results} properties, {result.new_inserted} new"
            )
        except Exception:
            logger.exception("Scheduled fetch failed")


async def _scheduled_fetch():
    """Background fetch loop.

    Two modes:
      - FETCH_INTERVAL_MINUTES=N (or legacy FETCH_INTERVAL_HOURS=N) : run every N minutes
      - FETCH_SCHEDULE_HOURS="9,12,15,..." : run at specific hours
    Interval mode takes precedence when both are set.
    """
    max_pages = int(os.environ.get("FETCH_MAX_PAGES", "10"))
    ward_codes_str = os.environ.get("FETCH_WARD_CODES", "")
    ward_codes = [c.strip() for c in ward_codes_str.split(",") if c.strip()] or None

    interval_minutes = _get_interval_minutes()

    if interval_minutes is None and not _get_schedule_hours():
        logger.info("Scheduled fetch disabled (no interval or schedule hours)")
        return

    if interval_minutes:
        logger.info(
            f"Fetch scheduler started: interval={interval_minutes}min, "
            f"max_pages={max_pages}, wards={ward_codes or 'all'}"
        )
        first_run = True
        while True:
            if first_run:
                wait_seconds = 30  # Small delay on startup to let server bind port
                first_run = False
            else:
                wait_seconds = interval_minutes * 60
            next_run = datetime.now() + timedelta(seconds=wait_seconds)
            logger.info(f"Next fetch at {next_run.strftime('%Y-%m-%d %H:%M')} (in {wait_seconds/60:.0f}min)")
            await asyncio.sleep(wait_seconds)

            await _run_fetch_once(ward_codes, max_pages)
        return

    # Specific-hours mode
    schedule_hours = _get_schedule_hours()
    logger.info(
        f"Fetch scheduler started: hours={schedule_hours}, "
        f"max_pages={max_pages}, wards={ward_codes or 'all'}"
    )

    while True:
        now = datetime.now()
        next_run = None
        for h in schedule_hours:
            candidate = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if candidate > now:
                next_run = candidate
                break
        if next_run is None:
            next_run = (now + timedelta(days=1)).replace(
                hour=schedule_hours[0], minute=0, second=0, microsecond=0
            )

        wait_seconds = (next_run - now).total_seconds()
        logger.info(f"Next fetch at {next_run.strftime('%H:%M')} (in {wait_seconds/60:.0f}min)")
        await asyncio.sleep(wait_seconds)

        await _run_fetch_once(ward_codes, max_pages)

        await asyncio.sleep(61)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and start background fetch scheduler on startup."""
    global _db_conn, _fetch_task

    db_path = _get_db_path()
    _db_conn = init_db(db_path)
    logger.info(f"Server starting with DB: {db_path}")

    # Enforce ward allow-list at startup so stale data from wider past fetches is cleared.
    from .orchestrator import ALLOWED_WARD_NAMES
    from .scrapers.constants import RENT_MAX_YEN
    prune_wards(_db_conn, list(ALLOWED_WARD_NAMES))
    prune_rent_cap(_db_conn, RENT_MAX_YEN)

    # Start background fetch scheduler
    _fetch_task = asyncio.create_task(_scheduled_fetch())

    yield

    # Cleanup
    if _fetch_task:
        _fetch_task.cancel()
    if _db_conn:
        _db_conn.close()


app = FastAPI(title="いい物件は7日まで", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint for Docker/Coolify."""
    try:
        _db_conn.execute("SELECT 1").fetchone()
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=503)


@app.get("/api/properties")
async def api_properties():
    """Return active properties within max_age_days."""
    max_age = _get_max_age_days()
    props = get_active_properties(_db_conn, max_age_days=max_age)
    return JSONResponse(content=props)


@app.get("/api/stats")
async def api_stats():
    """Return database statistics."""
    stats = get_stats(_db_conn)
    return JSONResponse(content=stats)


# Static files (web/) - mounted last so API routes take priority
_web_dir = _PROJECT_DIR / "web"
if _web_dir.exists():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="static")
