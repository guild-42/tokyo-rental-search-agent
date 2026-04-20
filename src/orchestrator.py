"""Orchestrate scraping across multiple sources."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from .db import init_db, mark_stale, run_lifecycle, upsert_properties
from .dedup import deduplicate
from .geocoder import Geocoder
from .models import FetchResult
from .normalizer import normalize_batch
from .scrapers.apamanshop import ApamanshopScraper
from .scrapers.chintai import ChintaiScraper
from .scrapers.constants import RENT_MAX_YEN
from .scrapers.door import DoorScraper
from .scrapers.eheya import EheyaScraper
from .scrapers.homes import HomesScraper
from .scrapers.suumo import SuumoScraper
from .scrapers.yahoo_realestate import YahooRealestateScraper

# housecom and minimini are disabled in phase 1 — their ward/rent filtering
# requires cookie-session POST (housecom) or SJIS + POST form handling
# (minimini), which we haven't solved yet. Leaving the scraper files in place.
# from .scrapers.housecom import HousecomScraper
# from .scrapers.minimini import MiniminiScraper

logger = logging.getLogger(__name__)

# Business rule: this deployment only covers 新宿 / 渋谷 / 中野.
# Any request to fetch other wards is silently forced back to these three.
ALLOWED_WARD_CODES: tuple[str, ...] = ("13104", "13113", "13114", "13115")
ALLOWED_WARD_NAMES: tuple[str, ...] = ("新宿区", "渋谷区", "中野区", "杉並区")


def _enforce_allowed_wards(ward_codes: list[str] | None) -> list[str]:
    if not ward_codes:
        return list(ALLOWED_WARD_CODES)
    filtered = [c for c in ward_codes if c in ALLOWED_WARD_CODES]
    if not filtered:
        logger.warning(
            f"Requested wards {ward_codes} are outside the allowed set; "
            f"falling back to {list(ALLOWED_WARD_CODES)}"
        )
        return list(ALLOWED_WARD_CODES)
    if len(filtered) != len(ward_codes):
        dropped = [c for c in ward_codes if c not in ALLOWED_WARD_CODES]
        logger.warning(f"Dropping disallowed ward codes {dropped}")
    return filtered


async def fetch_all(db_path: Path, ward_codes: list[str] | None = None, max_pages: int | None = None) -> FetchResult:
    """Fetch from all sources, normalize, dedup, store in SQLite.

    ``max_pages`` is intentionally no longer applied as a blanket override —
    each scraper knows its own appropriate max_pages (different sites need
    different depths after rent/ward filtering). The argument is kept for
    backward compatibility but ignored.
    """
    ward_codes = _enforce_allowed_wards(ward_codes)
    result = FetchResult(fetched_at=datetime.now())
    conn = init_db(db_path)

    try:
        # Active phase-1 scrapers. housecom/minimini disabled (see import block).
        scrapers = [
            SuumoScraper(ward_codes=ward_codes),
            ChintaiScraper(ward_codes=ward_codes),
            HomesScraper(ward_codes=ward_codes),
            YahooRealestateScraper(ward_codes=ward_codes),
            DoorScraper(ward_codes=ward_codes),
            EheyaScraper(ward_codes=ward_codes),
            ApamanshopScraper(ward_codes=ward_codes),
        ]

        # Fetch from all sources in parallel — each scraper uses its own
        # per-source max_pages (set as a class attribute).
        all_raw: list[dict] = []
        tasks = []
        for scraper in scrapers:
            tasks.append(scraper.fetch_latest())
            result.sources_searched.append(scraper.name)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for scraper, res in zip(scrapers, results):
            if isinstance(res, Exception):
                logger.error(f"[{scraper.name}] failed: {res}")
                result.errors.append({"source": scraper.name, "error": str(res)})
            else:
                all_raw.extend(res)
                logger.info(f"[{scraper.name}] fetched {len(res)} raw listings")

        # Normalize
        properties = normalize_batch(all_raw)

        # Final rent cap — safety net for sites whose URL-based rent filter
        # doesn't work (Yahoo, door, possibly eheya).
        before_rent_filter = len(properties)
        properties = [p for p in properties if p.rent and p.rent <= RENT_MAX_YEN]
        dropped = before_rent_filter - len(properties)
        if dropped:
            logger.info(f"Dropped {dropped} properties with rent > {RENT_MAX_YEN}")

        # Deduplicate
        properties, removed = deduplicate(properties)
        result.duplicates_removed = removed

        # Populate lat/lng via Nominatim (cache-first). Rate-limited to
        # 1 req/sec with a per-cycle cap so we don't block a fetch on 17K
        # cold-cache lookups — the cache fills up over subsequent cycles.
        try:
            gc = Geocoder(conn, max_new=300)
            await gc.resolve_many(properties)
        except Exception:
            logger.exception("geocoding step failed; continuing with station fallback")

        # Upsert into SQLite
        upsert_stats = upsert_properties(conn, properties)
        result.new_inserted = upsert_stats["inserted"]
        result.total_results = len(properties)
        result.properties = properties

        # Lifecycle: delete very old properties (not seen in 60+ days)
        run_lifecycle(conn)

    finally:
        conn.close()

    return result
