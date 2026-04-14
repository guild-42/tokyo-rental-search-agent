"""Coverage verification: compare advertised total counts vs. actually scraped.

The main question this answers: are we silently truncating listings because
our max_pages cap is too low?

Usage (from main.py):
    python main.py verify --wards 新宿区,渋谷区,中野区 --pages 10
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

from .scrapers.apamanshop import ApamanshopScraper
from .scrapers.base import BaseScraper
from .scrapers.chintai import ChintaiScraper
from .scrapers.door import DoorScraper
from .scrapers.eheya import EheyaScraper
from .scrapers.homes import HomesScraper
from .scrapers.suumo import SuumoScraper
from .scrapers.yahoo_realestate import YahooRealestateScraper

logger = logging.getLogger(__name__)


@dataclass
class CoverageReport:
    source: str
    ward_codes: list[str] = field(default_factory=list)
    expected: int | None = None
    actual: int = 0
    truncated: bool = False
    error: str | None = None

    @property
    def coverage_pct(self) -> float | None:
        if self.expected is None or self.expected == 0:
            return None
        return min(100.0, self.actual * 100.0 / self.expected)


def _make_scrapers(ward_codes: list[str] | None) -> list[BaseScraper]:
    return [
        SuumoScraper(ward_codes=ward_codes),
        HomesScraper(ward_codes=ward_codes),
        YahooRealestateScraper(ward_codes=ward_codes),
        ChintaiScraper(ward_codes=ward_codes),
        DoorScraper(ward_codes=ward_codes),
        EheyaScraper(ward_codes=ward_codes),
        ApamanshopScraper(ward_codes=ward_codes),
    ]


async def _probe_expected(scraper: BaseScraper) -> int | None:
    """Fetch page 1 once and run parse_total_count on it."""
    async with httpx.AsyncClient() as client:
        url = scraper.build_url(1)
        html = await scraper.fetch_page(client, url)
        if not html:
            return None
        try:
            return scraper.parse_total_count(html)
        except Exception:
            logger.exception(f"[{scraper.name}] parse_total_count crashed")
            return None


async def _verify_one(scraper: BaseScraper, max_pages: int | None) -> CoverageReport:
    report = CoverageReport(
        source=scraper.name,
        ward_codes=list(getattr(scraper, "ward_codes", None) or []),
    )
    # Respect per-scraper max_pages default unless the caller explicitly supplies one.
    if max_pages is not None:
        scraper.max_pages = max_pages
    try:
        report.expected = await _probe_expected(scraper)
        listings = await scraper.fetch_latest()
        report.actual = len(listings)
        if report.expected is not None and report.actual < report.expected:
            report.truncated = True
    except Exception as e:
        report.error = str(e)
        logger.exception(f"[{scraper.name}] verify failed")
    return report


async def verify_coverage(ward_codes: list[str] | None, max_pages: int | None = None) -> list[CoverageReport]:
    scrapers = _make_scrapers(ward_codes)
    tasks = [_verify_one(s, max_pages) for s in scrapers]
    return await asyncio.gather(*tasks)


def format_report(reports: list[CoverageReport]) -> str:
    lines = []
    header = f"{'Source':<12}{'Expected':>10}{'Actual':>10}{'Coverage':>12}  Truncated"
    lines.append(header)
    lines.append("-" * len(header))
    for r in reports:
        expected = f"{r.expected:,}" if r.expected is not None else "n/a"
        coverage = f"{r.coverage_pct:.0f}%" if r.coverage_pct is not None else "n/a"
        mark = "YES" if r.truncated else ("-" if r.expected is None else "OK")
        if r.error:
            mark = f"ERR: {r.error[:40]}"
        lines.append(f"{r.source:<12}{expected:>10}{r.actual:>10}{coverage:>12}  {mark}")
    return "\n".join(lines)
