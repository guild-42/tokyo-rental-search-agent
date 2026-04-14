"""SUUMO rental property scraper (suumo.jp)."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Tokyo ward codes for SUUMO search
TOKYO_WARD_CODES: dict[str, str] = {
    "千代田区": "13101", "中央区": "13102", "港区": "13103",
    "新宿区": "13104", "文京区": "13105", "台東区": "13106",
    "墨田区": "13107", "江東区": "13108", "品川区": "13109",
    "目黒区": "13110", "大田区": "13111", "世田谷区": "13112",
    "渋谷区": "13113", "中野区": "13114", "杉並区": "13115",
    "豊島区": "13116", "北区": "13117", "荒川区": "13118",
    "板橋区": "13119", "練馬区": "13120", "足立区": "13121",
    "葛飾区": "13122", "江戸川区": "13123",
}


def _parse_rent(text: str) -> int:
    """Parse rent text like '18万円' or '18.5万円' to integer yen."""
    text = text.strip()
    if not text or text == "-":
        return 0
    m = re.search(r"([\d.]+)万円", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"([\d,]+)円", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0


def _parse_admin_fee(text: str) -> int:
    """Parse management fee like '11000円' or '1.1万円'."""
    text = text.strip()
    if not text or text == "-":
        return 0
    return _parse_rent(text)


def _parse_size(text: str) -> float | None:
    """Parse floor area like '29.14m2'."""
    m = re.search(r"([\d.]+)\s*m", text.strip())
    return float(m.group(1)) if m else None


def _parse_age(text: str) -> int | None:
    """Parse building age like '築25年' or '新築'."""
    text = text.strip()
    if "新築" in text:
        return 0
    m = re.search(r"築(\d+)年", text)
    return int(m.group(1)) if m else None


def _parse_floors_info(text: str) -> tuple[int | None, int | None]:
    """Parse building floors like '地下1地上2階建' or '5階建'.
    Returns (underground_floors, total_above_ground_floors)."""
    total = None
    m = re.search(r"(\d+)階建", text)
    if m:
        total = int(m.group(1))
    # Check for underground
    m_under = re.search(r"地下(\d+)", text)
    if m_under and total:
        total += int(m_under.group(1))
    return total


def _parse_room_floor(text: str) -> int | None:
    """Parse room floor like '2階'."""
    m = re.search(r"(\d+)階", text.strip())
    return int(m.group(1)) if m else None


def _parse_station_info(text: str) -> list[dict]:
    """Parse station access info like '京王新線/幡ヶ谷駅 歩9分'."""
    stations = []
    for line in text.strip().split("\n"):
        line = line.strip()
        m = re.match(r"(.+?)/(.+?駅)\s*歩(\d+)分", line)
        if m:
            stations.append({
                "line": m.group(1),
                "station": m.group(2),
                "walk_minutes": int(m.group(3)),
            })
    return stations


class SuumoScraper(BaseScraper):
    """Scraper for SUUMO rental listings."""

    name = "suumo"
    base_url = "https://suumo.jp"
    rate_limit = 1.5
    max_pages = 200

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        # Default: all Tokyo 23 wards
        self.ward_codes = ward_codes or list(TOKYO_WARD_CODES.values())
        self._current_ward_code: str = self.ward_codes[0] if self.ward_codes else "13104"

    def build_url(self, page: int) -> str:
        """Single-ward SUUMO URL with rent ≤10万 (ct=10.0), newest first (po1=25),
        50 listings per page (maximum allowed by SUUMO).
        """
        return (
            f"{self.base_url}/jj/chintai/ichiran/FR301FC001/"
            f"?ar=030&bs=040&ta=13&sc={self._current_ward_code}"
            f"&cb=0.0&ct=10.0&et=9999999&cn=9999999"
            f"&po1=25&pc=50&page={page}"
        )

    async def fetch_latest(self) -> list[dict]:
        """Fetch each ward as a separate SUUMO query so we can actually
        paginate through everything. SUUMO truncates hard when multiple sc=
        are combined in one URL.
        """
        all_listings: list[dict] = []
        for code in self.ward_codes:
            self._current_ward_code = code
            ward_name = next((k for k, v in TOKYO_WARD_CODES.items() if v == code), code)
            logger.info(f"[{self.name}] fetching ward: {ward_name} ({code})")
            listings = await super().fetch_latest()
            all_listings.extend(listings)
            logger.info(f"[{self.name}] {ward_name}: {len(listings)} listings")
        return all_listings

    def parse_total_count(self, html: str) -> int | None:
        """SUUMO shows '新宿区エリア12,189件の物件をご紹介' in the header."""
        m = re.search(r"エリア\s*([\d,]+)\s*件の物件", html)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        from .base import parse_total_count_japanese
        return parse_total_count_japanese(html)

    def parse_listings(self, html: str) -> list[dict]:
        """Parse SUUMO search results HTML into property dicts."""
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".cassetteitem")
        results: list[dict] = []

        for item in items:
            try:
                building = self._parse_building(item)
                rooms = self._parse_rooms(item, building)
                results.extend(rooms)
            except Exception as e:
                logger.warning(f"[suumo] failed to parse listing: {e}")
                continue

        return results

    def _parse_building(self, item: Tag) -> dict:
        """Extract building-level info from a cassetteitem."""
        title_el = item.select_one(".cassetteitem_content-title")
        label_el = item.select_one(".cassetteitem_content-label")
        col1 = item.select_one(".cassetteitem_detail-col1")
        col2 = item.select_one(".cassetteitem_detail-col2")
        col3 = item.select_one(".cassetteitem_detail-col3")

        # Image
        img_el = item.select_one(".cassetteitem_object-item img")
        image_url = ""
        if img_el:
            image_url = img_el.get("rel", img_el.get("src", ""))
            if isinstance(image_url, list):
                image_url = image_url[0] if image_url else ""
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        # Station info
        stations = _parse_station_info(col2.text if col2 else "")

        # Building age and floors
        col3_text = col3.text.strip() if col3 else ""
        age = _parse_age(col3_text)
        total_floors = _parse_floors_info(col3_text)

        # Address
        address = col1.text.strip() if col1 else ""
        ward = ""
        for w in TOKYO_WARD_CODES:
            if w in address:
                ward = w
                break

        return {
            "building_name": title_el.text.strip() if title_el else "",
            "building_type": label_el.text.strip() if label_el else "",
            "address": f"東京都{address}" if address and not address.startswith("東京都") else address,
            "ward": ward,
            "stations": stations,
            "building_age_years": age,
            "total_floors": total_floors,
            "image_url": image_url,
        }

    def _parse_rooms(self, item: Tag, building: dict) -> list[dict]:
        """Extract room-level info from table rows."""
        table = item.select_one("table")
        if not table:
            return []

        rows = table.select("tbody tr")
        rooms: list[dict] = []

        for row in rows:
            tds = row.select("td")
            if len(tds) < 7:
                continue

            # Floor (3rd td, 0-indexed: td[2])
            floor_text = tds[2].text.strip()
            floor = _parse_room_floor(floor_text)

            # Rent + admin fee (4th td)
            rent_span = row.select_one(".cassetteitem_price--rent")
            admin_span = row.select_one(".cassetteitem_price--administration")
            rent = _parse_rent(rent_span.text if rent_span else "")
            admin_fee = _parse_admin_fee(admin_span.text if admin_span else "")

            # Deposit + key money (5th td)
            deposit_span = row.select_one(".cassetteitem_price--deposit")
            gratuity_span = row.select_one(".cassetteitem_price--gratuity")
            deposit = _parse_rent(deposit_span.text if deposit_span else "")
            key_money = _parse_rent(gratuity_span.text if gratuity_span else "")

            # Layout + area (6th td)
            madori = row.select_one(".cassetteitem_madori")
            menseki = row.select_one(".cassetteitem_menseki")
            layout = madori.text.strip() if madori else ""
            size = _parse_size(menseki.text if menseki else "")

            # Detail URL
            detail_link = row.select_one("a[href*='/chintai/']")
            detail_url = ""
            if detail_link:
                href = detail_link.get("href", "")
                detail_url = f"{self.base_url}{href}" if href.startswith("/") else href

            # Extract a unique ID from the URL
            prop_id = ""
            if detail_url:
                m = re.search(r"jnc_(\d+)", detail_url)
                if m:
                    prop_id = f"suumo_{m.group(1)}"

            # Primary station
            primary_station = building["stations"][0] if building["stations"] else {}

            rooms.append({
                "id": prop_id,
                "source": "suumo",
                "source_url": detail_url,
                "name": building["building_name"],
                "rent": rent,
                "management_fee": admin_fee,
                "deposit": deposit or None,
                "key_money": key_money or None,
                "layout": layout,
                "size_sqm": size,
                "floor": floor,
                "total_floors": building["total_floors"],
                "building_age_years": building["building_age_years"],
                "structure": building["building_type"],
                "address": building["address"],
                "ward": building["ward"],
                "nearest_station": primary_station.get("station", ""),
                "walk_minutes": primary_station.get("walk_minutes"),
                "line": primary_station.get("line", ""),
                "image_url": building["image_url"],
                "features": [],
            })

        return rooms
