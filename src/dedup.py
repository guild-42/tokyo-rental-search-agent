"""Deduplicate properties across sources."""

from __future__ import annotations

import hashlib
import re

from .models import Property


def _normalize_address(addr: str) -> str:
    """Normalize address for comparison."""
    # Full-width to half-width numbers
    table = str.maketrans("０１２３４５６７８９", "0123456789")
    addr = addr.translate(table)
    # Remove building name variations
    addr = re.sub(r"\s+.*$", "", addr)
    return addr.strip()


def dedup_key(p: Property) -> str:
    """Generate a dedup key from address + rent + layout + size."""
    addr = _normalize_address(p.address)
    size = f"{p.size_sqm:.1f}" if p.size_sqm else "0"
    raw = f"{addr}|{p.rent}|{p.layout}|{size}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def deduplicate(properties: list[Property]) -> tuple[list[Property], int]:
    """Remove duplicate properties. Returns (unique_list, removed_count)."""
    seen: dict[str, Property] = {}
    for p in properties:
        key = dedup_key(p)
        if key in seen:
            # Keep the one with more data (longer source_url or more features)
            existing = seen[key]
            if len(p.features) > len(existing.features):
                seen[key] = p
        else:
            seen[key] = p
    unique = list(seen.values())
    removed = len(properties) - len(unique)
    return unique, removed
