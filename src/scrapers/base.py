from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod

import httpx

from .constants import RENT_MAX_YEN

logger = logging.getLogger(__name__)

# Shared "X件中" / "X件" patterns used by parse_total_count_japanese().
# Order matters: more specific patterns first.
_TOTAL_COUNT_PATTERNS = (
    re.compile(r"全\s*([\d,]+)\s*件中"),
    re.compile(r"該当件数[:：\s]*([\d,]+)\s*件"),
    re.compile(r"([\d,]+)\s*件中"),
    re.compile(r"検索結果\s*([\d,]+)\s*件"),
    re.compile(r"([\d,]+)\s*件\s*[/／]\s*[\d,]+\s*件"),
)


def parse_total_count_japanese(html: str) -> int | None:
    """Best-effort extract of an advertised total count from Japanese listing HTML.

    Tries several common phrasings ("○○件中", "該当件数: X件", etc.) and
    returns the first plausible integer, or None if nothing matches.
    """
    for pattern in _TOTAL_COUNT_PATTERNS:
        m = pattern.search(html)
        if not m:
            continue
        try:
            value = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if value > 0:
            return value
    return None

# Rotate user-agents to look like a normal browser
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
]


class BaseScraper(ABC):
    """Abstract base for all rental site scrapers."""

    name: str = ""
    base_url: str = ""
    rate_limit: float = 1.5  # seconds between requests
    timeout: int = 30
    max_pages: int = 10
    retry_count: int = 3

    def __init__(self) -> None:
        self._ua_index = 0

    def _next_ua(self) -> str:
        ua = _USER_AGENTS[self._ua_index % len(_USER_AGENTS)]
        self._ua_index += 1
        return ua

    @abstractmethod
    def build_url(self, page: int) -> str:
        """Build search URL for the given page number (1-indexed)."""
        ...

    @abstractmethod
    def parse_listings(self, html: str) -> list[dict]:
        """Parse HTML and return list of raw property dicts."""
        ...

    def parse_total_count(self, html: str) -> int | None:
        """Extract the advertised total result count (e.g. '1,234件中').

        Override in scrapers that can reliably parse this. Return None when
        unknown. Used by the coverage verifier and for truncation warnings.
        """
        return None

    async def fetch_page(self, client: httpx.AsyncClient, url: str) -> str | None:
        """Fetch a single page with retries and exponential backoff.

        202 is treated as a separate, more-patient retry budget because HOME'S
        (and some others) use it as a soft throttle and the original 3×exp
        backoff (max 14s) was too aggressive — the retries failed mid-session
        and we lost the page entirely.
        """
        # More generous budget for 202 throttling: up to 6 attempts, up to 60s wait.
        max_202_attempts = 6
        attempt = 0
        error_attempt = 0
        while attempt < max_202_attempts and error_attempt < self.retry_count:
            try:
                headers = {
                    "User-Agent": self._next_ua(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Cache-Control": "max-age=0",
                    "DNT": "1",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                    "Priority": "u=0, i",
                    "Referer": self.base_url or "https://www.google.com/",
                }
                resp = await client.get(url, headers=headers, timeout=self.timeout, follow_redirects=True)
                if resp.status_code == 202:
                    attempt += 1
                    wait = min(60.0, 5.0 * (1.8 ** (attempt - 1)))
                    logger.warning(
                        f"[{self.name}] 202 throttle for {url} "
                        f"(attempt {attempt}/{max_202_attempts}), waiting {wait:.0f}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                error_attempt += 1
                wait = (2 ** error_attempt) * 1.0
                logger.warning(
                    f"[{self.name}] attempt {error_attempt}/{self.retry_count} "
                    f"failed for {url}: {e}. Retry in {wait}s"
                )
                await asyncio.sleep(wait)
        logger.error(f"[{self.name}] gave up on {url} (202×{attempt}, err×{error_attempt})")
        return None

    async def fetch_latest(self) -> list[dict]:
        """Fetch listings from all pages, newest first."""
        all_listings: list[dict] = []
        expected_total: int | None = None
        async with httpx.AsyncClient() as client:
            for page in range(1, self.max_pages + 1):
                url = self.build_url(page)
                logger.info(f"[{self.name}] fetching page {page}: {url}")
                html = await self.fetch_page(client, url)
                if html is None:
                    break
                if page == 1:
                    try:
                        expected_total = self.parse_total_count(html)
                    except Exception:
                        expected_total = None
                    if expected_total is not None:
                        logger.info(f"[{self.name}] advertised total: {expected_total} listings")
                listings = self.parse_listings(html)
                if not listings:
                    logger.info(f"[{self.name}] no listings on page {page}, stopping")
                    break
                all_listings.extend(listings)
                logger.info(f"[{self.name}] page {page}: {len(listings)} listings (total: {len(all_listings)})")
                # Early stop: if all listings on this page exceed the rent cap,
                # the rest almost certainly do too (results are typically sorted
                # by price/newness and a whole page >10万 means the cheap stock
                # ended). Saves time on sites without URL-based rent filter.
                if listings and all(
                    (item.get("rent") or 0) > RENT_MAX_YEN for item in listings
                ):
                    logger.info(
                        f"[{self.name}] page {page} all listings > {RENT_MAX_YEN}, stopping early"
                    )
                    break
                # Rate limiting between pages
                await asyncio.sleep(self.rate_limit)
            else:
                # Loop finished because we hit max_pages. If the last page was
                # non-empty the site likely has more listings we didn't fetch.
                if all_listings:
                    logger.warning(
                        f"[{self.name}] hit max_pages={self.max_pages} cap, "
                        f"possibly truncated (fetched {len(all_listings)})"
                    )
        if expected_total is not None and len(all_listings) < expected_total:
            logger.warning(
                f"[{self.name}] coverage low: fetched {len(all_listings)} / "
                f"advertised {expected_total} ({len(all_listings) * 100 // max(expected_total, 1)}%)"
            )
        return all_listings
