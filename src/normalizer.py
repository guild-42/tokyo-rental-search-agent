"""Normalize raw scraper output into Property models."""

from __future__ import annotations

from datetime import datetime

from .models import Property


def normalize(raw: dict) -> Property:
    """Convert a raw scraper dict to a Property model."""
    return Property(
        id=raw.get("id", ""),
        source=raw.get("source", ""),
        source_url=raw.get("source_url", ""),
        scraped_at=datetime.now(),
        name=raw.get("name", ""),
        rent=raw.get("rent", 0),
        management_fee=raw.get("management_fee", 0),
        deposit=raw.get("deposit"),
        key_money=raw.get("key_money"),
        layout=raw.get("layout", ""),
        size_sqm=raw.get("size_sqm"),
        floor=raw.get("floor"),
        total_floors=raw.get("total_floors"),
        building_age_years=raw.get("building_age_years"),
        structure=raw.get("structure", ""),
        address=raw.get("address", ""),
        ward=raw.get("ward", ""),
        lat=raw.get("lat"),
        lng=raw.get("lng"),
        nearest_station=raw.get("nearest_station", ""),
        walk_minutes=raw.get("walk_minutes"),
        line=raw.get("line", ""),
        features=raw.get("features", []),
        pet_allowed=raw.get("pet_allowed"),
        available_from=raw.get("available_from", ""),
        image_url=raw.get("image_url", ""),
    )


TOKYO_23_WARDS = {
    "千代田区", "中央区", "港区", "新宿区", "文京区", "台東区",
    "墨田区", "江東区", "品川区", "目黒区", "大田区", "世田谷区",
    "渋谷区", "中野区", "杉並区", "豊島区", "北区", "荒川区",
    "板橋区", "練馬区", "足立区", "葛飾区", "江戸川区",
}


def normalize_batch(raw_list: list[dict]) -> list[Property]:
    """Normalize a batch of raw dicts, skipping invalid ones.

    Filters to Tokyo 23 wards only.
    """
    results = []
    for raw in raw_list:
        if not raw.get("id"):
            continue
        # Ensure ward is set from address if missing
        ward = raw.get("ward", "")
        if not ward and raw.get("address"):
            import re
            m = re.search(r"(?:東京都)?(.+?区)", raw["address"])
            if m:
                ward = m.group(1)
                raw["ward"] = ward
        # Skip properties outside Tokyo 23 wards
        if ward and ward not in TOKYO_23_WARDS:
            continue
        # Skip properties with no ward at all (can't verify location)
        if not ward:
            continue
        results.append(normalize(raw))
    return results
