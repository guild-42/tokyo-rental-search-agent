from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class Property(BaseModel):
    """Unified property schema across all sources."""

    id: str = Field(description="Source-prefixed unique ID, e.g. suumo_abc123")
    source: str = Field(description="Source name: suumo, homes, athome, chintai")
    source_url: str = ""
    scraped_at: datetime = Field(default_factory=datetime.now)

    # Lifecycle fields (managed by db.py)
    first_seen: str = ""
    last_seen: str = ""
    status: str = "active"

    # Basic info
    name: str = ""
    rent: int = 0  # 家賃（円/月）
    management_fee: int = 0  # 管理費（円/月）
    deposit: int | None = None  # 敷金
    key_money: int | None = None  # 礼金
    layout: str = ""  # 間取り (1K, 1LDK, etc.)
    size_sqm: float | None = None  # 専有面積（㎡）
    floor: int | None = None  # 階
    total_floors: int | None = None  # 建物の階数
    building_age_years: int | None = None  # 築年数
    structure: str = ""  # 構造 (RC, SRC, 木造, etc.)

    # Location
    address: str = ""
    ward: str = ""  # 区
    lat: float | None = None
    lng: float | None = None
    nearest_station: str = ""
    walk_minutes: int | None = None
    line: str = ""  # 路線名

    # Details
    features: list[str] = Field(default_factory=list)
    pet_allowed: bool | None = None
    available_from: str = ""
    image_url: str = ""


class FetchResult(BaseModel):
    """Result of a single fetch run."""

    fetched_at: datetime = Field(default_factory=datetime.now)
    sources_searched: list[str] = Field(default_factory=list)
    total_results: int = 0
    duplicates_removed: int = 0
    new_inserted: int = 0
    properties: list[Property] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
