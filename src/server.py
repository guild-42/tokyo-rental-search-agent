"""FastAPI server for the rental search web service."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import get_active_properties, get_stats, init_db

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


def _get_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", str(_PROJECT_DIR / "data" / "rental.db")))


def _get_schedule_hours() -> list[int]:
    raw = os.environ.get("FETCH_SCHEDULE_HOURS", "9,12,15,18,21")
    return sorted(int(h.strip()) for h in raw.split(",") if h.strip())


def _get_max_age_days() -> int:
    return int(os.environ.get("MAX_AGE_DAYS", "7"))


async def _scheduled_fetch():
    """Background fetch loop.

    Two modes:
      - FETCH_INTERVAL_HOURS=N : run every N hours (preferred, simpler)
      - FETCH_SCHEDULE_HOURS="9,12,15,..." : run at specific hours
    FETCH_INTERVAL_HOURS takes precedence when both are set.
    """
    from datetime import datetime, timedelta

    from .orchestrator import fetch_all

    max_pages = int(os.environ.get("FETCH_MAX_PAGES", "10"))
    ward_codes_str = os.environ.get("FETCH_WARD_CODES", "")
    ward_codes = [c.strip() for c in ward_codes_str.split(",") if c.strip()] or None

    interval_raw = os.environ.get("FETCH_INTERVAL_HOURS", "").strip()
    interval_hours = int(interval_raw) if interval_raw.isdigit() and int(interval_raw) > 0 else None

    if interval_hours is None and not _get_schedule_hours():
        logger.info("Scheduled fetch disabled (no interval or schedule hours)")
        return

    if interval_hours:
        logger.info(
            f"Fetch scheduler started: interval={interval_hours}h, "
            f"max_pages={max_pages}, wards={ward_codes or 'all'}"
        )
        # Run immediately on startup, then every N hours
        first_run = True
        while True:
            if first_run:
                wait_seconds = 30  # Small delay on startup to let server bind port
                first_run = False
            else:
                wait_seconds = interval_hours * 3600
            next_run = datetime.now() + timedelta(seconds=wait_seconds)
            logger.info(f"Next fetch at {next_run.strftime('%Y-%m-%d %H:%M')} (in {wait_seconds/60:.0f}min)")
            await asyncio.sleep(wait_seconds)

            try:
                logger.info("Scheduled fetch starting...")
                db_path = _get_db_path()
                result = await fetch_all(db_path, ward_codes=ward_codes, max_pages=max_pages)
                logger.info(
                    f"Scheduled fetch complete: {result.total_results} properties, "
                    f"{result.new_inserted} new"
                )
            except Exception:
                logger.exception("Scheduled fetch failed")
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

        try:
            logger.info("Scheduled fetch starting...")
            db_path = _get_db_path()
            result = await fetch_all(db_path, ward_codes=ward_codes, max_pages=max_pages)
            logger.info(
                f"Scheduled fetch complete: {result.total_results} properties, "
                f"{result.new_inserted} new"
            )
        except Exception:
            logger.exception("Scheduled fetch failed")

        await asyncio.sleep(61)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and start background fetch scheduler on startup."""
    global _db_conn, _fetch_task

    db_path = _get_db_path()
    _db_conn = init_db(db_path)
    logger.info(f"Server starting with DB: {db_path}")

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
