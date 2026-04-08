from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)

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

    async def fetch_page(self, client: httpx.AsyncClient, url: str) -> str | None:
        """Fetch a single page with retries and exponential backoff."""
        for attempt in range(self.retry_count):
            try:
                headers = {
                    "User-Agent": self._next_ua(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
                }
                resp = await client.get(url, headers=headers, timeout=self.timeout, follow_redirects=True)
                # Some sites return 202 as a soft rate-limit; treat as retryable
                if resp.status_code == 202:
                    wait = (2**attempt) * 2.0
                    logger.warning(f"[{self.name}] got 202 for {url}, retrying in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                wait = (2**attempt) * 1.0
                logger.warning(f"[{self.name}] attempt {attempt+1} failed for {url}: {e}. Retry in {wait}s")
                await asyncio.sleep(wait)
        logger.error(f"[{self.name}] gave up on {url} after {self.retry_count} attempts")
        return None

    async def fetch_latest(self) -> list[dict]:
        """Fetch listings from all pages, newest first."""
        all_listings: list[dict] = []
        async with httpx.AsyncClient() as client:
            for page in range(1, self.max_pages + 1):
                url = self.build_url(page)
                logger.info(f"[{self.name}] fetching page {page}: {url}")
                html = await self.fetch_page(client, url)
                if html is None:
                    break
                listings = self.parse_listings(html)
                if not listings:
                    logger.info(f"[{self.name}] no listings on page {page}, stopping")
                    break
                all_listings.extend(listings)
                logger.info(f"[{self.name}] page {page}: {len(listings)} listings (total: {len(all_listings)})")
                # Rate limiting between pages
                await asyncio.sleep(self.rate_limit)
        return all_listings
