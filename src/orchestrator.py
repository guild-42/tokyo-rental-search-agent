"""Orchestrate scraping across multiple sources."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from .db import init_db, mark_stale, run_lifecycle, upsert_properties
from .dedup import deduplicate
from .models import FetchResult
from .normalizer import normalize_batch
from .scrapers.apamanshop import ApamanshopScraper
from .scrapers.chintai import ChintaiScraper
from .scrapers.door import DoorScraper
from .scrapers.eheya import EheyaScraper
from .scrapers.homes import HomesScraper
from .scrapers.housecom import HousecomScraper
from .scrapers.minimini import MiniminiScraper
from .scrapers.suumo import SuumoScraper
from .scrapers.yahoo_realestate import YahooRealestateScraper

logger = logging.getLogger(__name__)


async def fetch_all(db_path: Path, ward_codes: list[str] | None = None, max_pages: int = 10) -> FetchResult:
    """Fetch from all sources, normalize, dedup, store in SQLite."""
    result = FetchResult(fetched_at=datetime.now())
    conn = init_db(db_path)

    try:
        # Initialize scrapers (9 sources)
        scrapers = [
            SuumoScraper(ward_codes=ward_codes),
            ChintaiScraper(ward_codes=ward_codes),
            HomesScraper(ward_codes=ward_codes),
            YahooRealestateScraper(ward_codes=ward_codes),
            DoorScraper(ward_codes=ward_codes),
            EheyaScraper(ward_codes=ward_codes),
            HousecomScraper(ward_codes=ward_codes),
            MiniminiScraper(ward_codes=ward_codes),
            ApamanshopScraper(ward_codes=ward_codes),
        ]

        # Fetch from all sources in parallel
        all_raw: list[dict] = []
        tasks = []
        for scraper in scrapers:
            scraper.max_pages = max_pages
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

        # Deduplicate
        properties, removed = deduplicate(properties)
        result.duplicates_removed = removed

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
