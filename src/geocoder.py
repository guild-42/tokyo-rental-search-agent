"""Address → lat/lng resolver using OpenStreetMap Nominatim.

Nominatim's usage policy asks for ≤1 req/sec and a descriptive User-Agent.
We cache every lookup in the ``geocache`` SQLite table so repeat addresses
don't burn through the rate budget across fetch cycles.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "tokyo-rental-search-agent/1.0 (contact: guild42)"
RATE_LIMIT_SECONDS = 1.05  # a smidge over 1s/req


def _normalize_address(address: str) -> str:
    """Trim building names and unit tags so similar addresses collapse into one cache key."""
    if not address:
        return ""
    # Drop anything after common building/unit delimiters
    addr = re.split(r"[ 　]{2,}| - |,|、", address)[0]
    # Strip floor/room suffixes ("302号室", "5F" etc.)
    addr = re.sub(r"\s*\d+号室.*$", "", addr)
    addr = re.sub(r"\s*[0-9]+[FＦ階]$", "", addr)
    return addr.strip()


async def geocode_one(client: httpx.AsyncClient, address: str) -> tuple[float, float] | None:
    """Single Nominatim request — caller is responsible for rate-limit sleeping."""
    query = _normalize_address(address)
    if not query:
        return None
    try:
        resp = await client.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "jp",
                "accept-language": "ja",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"[geocoder] {address!r}: {e}")
        return None
    if not data:
        return None
    try:
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (KeyError, ValueError, TypeError):
        return None


class Geocoder:
    """Async address → lat/lng resolver with SQLite-backed cache.

    Usage::

        gc = Geocoder(conn)
        await gc.resolve_many(properties)   # populates property.lat/lng in place
    """

    def __init__(self, conn: sqlite3.Connection, *, max_new: int = 300):
        self.conn = conn
        # Per-run safety cap on live Nominatim calls; keeps one fetch cycle
        # from hammering the service when a brand-new DB needs ~17k lookups.
        self.max_new = max_new

    def get_cached(self, address: str) -> tuple[float, float] | None:
        key = _normalize_address(address)
        if not key:
            return None
        row = self.conn.execute(
            "SELECT lat, lng FROM geocache WHERE address = ?", (key,)
        ).fetchone()
        if not row:
            return None
        lat, lng = row
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)

    def set_cached(self, address: str, result: tuple[float, float] | None) -> None:
        key = _normalize_address(address)
        if not key:
            return
        lat, lng = (result or (None, None))
        self.conn.execute(
            "INSERT OR REPLACE INTO geocache (address, lat, lng, cached_at) VALUES (?, ?, ?, ?)",
            (key, lat, lng, datetime.now().isoformat()),
        )

    async def resolve_many(self, properties: list) -> int:
        """Set ``.lat`` / ``.lng`` on each property from cache or Nominatim.

        Returns the number of live Nominatim calls made. Respects ``max_new``
        to avoid blocking a fetch cycle on the 1 req/sec Nominatim limit.
        """
        # First pass: cache fills. Collect the miss list.
        misses: list = []
        for p in properties:
            if p.lat and p.lng:
                continue
            cached = self.get_cached(p.address or "")
            if cached:
                p.lat, p.lng = cached
                continue
            if p.address:
                misses.append(p)

        if not misses:
            self.conn.commit()
            return 0

        live_budget = min(self.max_new, len(misses))
        if live_budget < len(misses):
            logger.info(
                f"[geocoder] {len(misses)} misses, resolving first {live_budget} "
                f"this cycle (cap)"
            )
        resolved = 0
        async with httpx.AsyncClient() as client:
            for idx, p in enumerate(misses[:live_budget]):
                result = await geocode_one(client, p.address or "")
                self.set_cached(p.address or "", result)
                if result:
                    p.lat, p.lng = result
                    resolved += 1
                # Nominatim is strict: 1 req/sec hard ceiling.
                if idx < live_budget - 1:
                    await asyncio.sleep(RATE_LIMIT_SECONDS)

        self.conn.commit()
        logger.info(f"[geocoder] live lookups {live_budget}, successful {resolved}")
        return live_budget
