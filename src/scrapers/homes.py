"""LIFULL HOME'S rental property scraper (homes.co.jp)."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Ward code (SUUMO-compatible) -> LIFULL HOME'S URL slug
HOMES_WARD_SLUGS: dict[str, str] = {
    "13101": "chiyoda-city", "13102": "chuo-city", "13103": "minato-city",
    "13104": "shinjuku-city", "13105": "bunkyo-city", "13106": "taito-city",
    "13107": "sumida-city", "13108": "koto-city", "13109": "shinagawa-city",
    "13110": "meguro-city", "13111": "ota-city", "13112": "setagaya-city",
    "13113": "shibuya-city", "13114": "nakano-city", "13115": "suginami-city",
    "13116": "toshima-city", "13117": "kita-city", "13118": "arakawa-city",
    "13119": "itabashi-city", "13120": "nerima-city", "13121": "adachi-city",
    "13122": "katsushika-city", "13123": "edogawa-city",
}


def _parse_rent(text: str) -> int:
    text = text.strip()
    if not text or text == "-" or text == "無":
        return 0
    m = re.search(r"([\d.]+)万円", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"([\d,]+)円", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0


def _parse_size(text: str) -> float | None:
    m = re.search(r"([\d.]+)\s*m", text)
    return float(m.group(1)) if m else None


class HomesScraper(BaseScraper):
    """Scraper for LIFULL HOME'S rental listings."""

    name = "homes"
    base_url = "https://www.homes.co.jp"
    rate_limit = 2.0
    max_pages = 5

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        self.ward_codes = ward_codes or list(HOMES_WARD_SLUGS.keys())
        self._current_slug = HOMES_WARD_SLUGS.get(self.ward_codes[0], "") if self.ward_codes else ""

    def build_url(self, page: int) -> str:
        if self._current_slug:
            return f"{self.base_url}/chintai/tokyo/{self._current_slug}/list/?sort=new&page={page}"
        return f"{self.base_url}/chintai/tokyo/list/?sort=new&page={page}"

    async def fetch_latest(self) -> list[dict]:
        """Override: fetch each ward separately, then combine."""
        all_listings: list[dict] = []
        for code in self.ward_codes:
            slug = HOMES_WARD_SLUGS.get(code)
            if not slug:
                continue
            self._current_slug = slug
            ward_name = next((k for k, v in HOMES_WARD_SLUGS.items() if v == slug), code)
            logger.info(f"[{self.name}] fetching ward: {ward_name} ({slug})")
            listings = await super().fetch_latest()
            all_listings.extend(listings)
            logger.info(f"[{self.name}] {ward_name}: {len(listings)} listings")
        return all_listings

    def parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        buildings = soup.select(".prg-building")
        results: list[dict] = []

        for building in buildings:
            try:
                binfo = self._parse_building(building)
                rooms = self._parse_rooms(building, binfo)
                results.extend(rooms)
            except Exception as e:
                logger.warning(f"[homes] parse error: {e}")
                continue

        return results

    def _parse_building(self, el: Tag) -> dict:
        name_el = el.select_one(".bukkenName")
        name = name_el.text.strip() if name_el else ""

        spec_el = el.select_one(".bukkenSpec")
        spec_text = spec_el.text.strip() if spec_el else ""

        # Parse address
        address = ""
        m = re.search(r"所在地(東京都.+?)交通", spec_text)
        if m:
            address = m.group(1).strip()

        # Ward
        ward = ""
        m_ward = re.search(r"東京都(.+?区)", address)
        if m_ward:
            ward = m_ward.group(1)

        # Station access
        stations = []
        for m in re.finditer(r"(.+?線)\s+(.+?駅)\s*徒歩(\d+)分", spec_text):
            stations.append({
                "line": m.group(1),
                "station": m.group(2),
                "walk_minutes": int(m.group(3)),
            })

        # Age
        age = None
        if "新築" in spec_text:
            age = 0
        else:
            m_age = re.search(r"(\d+)年\s*/", spec_text)
            if m_age:
                age = int(m_age.group(1))

        # Floors
        total_floors = None
        m_floors = re.search(r"(\d+)階建", spec_text)
        if m_floors:
            total_floors = int(m_floors.group(1))

        # Image
        img_el = el.select_one(".bukkenPhoto img")
        image_url = ""
        if img_el:
            image_url = img_el.get("data-original", img_el.get("src", ""))
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        return {
            "name": name,
            "address": address,
            "ward": ward,
            "stations": stations,
            "building_age_years": age,
            "total_floors": total_floors,
            "image_url": image_url,
        }

    def _parse_rooms(self, el: Tag, building: dict) -> list[dict]:
        rows = el.select(".prg-roomRow")
        rooms: list[dict] = []

        for row in rows:
            price_td = row.select_one(".price")
            layout_td = row.select_one(".layout")
            floor_td = row.select_one(".floar")
            detail_link = row.select_one("a[href*='/chintai/room/']")

            if not price_td:
                continue

            # Price: "7.2万円/-1ヶ月/1ヶ月/-/-"
            price_text = price_td.text.strip()
            parts = re.split(r"[/／]", price_text)

            rent = _parse_rent(parts[0]) if len(parts) > 0 else 0
            admin_fee = _parse_rent(parts[1]) if len(parts) > 1 else 0

            # Deposit/key money: "1ヶ月" means 1 month of rent
            deposit = None
            if len(parts) > 2:
                dep_text = parts[2].strip()
                m = re.search(r"([\d.]+)ヶ月", dep_text)
                if m:
                    deposit = int(float(m.group(1)) * rent) if rent else 0
                elif dep_text not in ("-", "無", "なし", ""):
                    deposit = _parse_rent(dep_text)

            key_money = None
            if len(parts) > 3:
                key_text = parts[3].strip()
                m = re.search(r"([\d.]+)ヶ月", key_text)
                if m:
                    key_money = int(float(m.group(1)) * rent) if rent else 0
                elif key_text not in ("-", "無", "なし", ""):
                    key_money = _parse_rent(key_text)

            # Layout: "1K25.51m²"
            layout_text = layout_td.text.strip() if layout_td else ""
            layout = ""
            size = None
            m_layout = re.match(r"(\d[A-Z]+K?)", layout_text)
            if m_layout:
                layout = m_layout.group(1)
            else:
                m_layout = re.match(r"(ワンルーム|1R)", layout_text)
                if m_layout:
                    layout = "1R"
            size = _parse_size(layout_text)

            # Floor: "1階101"
            floor = None
            if floor_td:
                m_floor = re.search(r"(\d+)階", floor_td.text.strip())
                if m_floor:
                    floor = int(m_floor.group(1))

            # URL
            detail_url = ""
            if detail_link:
                href = detail_link.get("href", "")
                detail_url = href if href.startswith("http") else f"{self.base_url}{href}"

            # ID from URL
            prop_id = ""
            if detail_url:
                m_id = re.search(r"/room/([a-f0-9]+)", detail_url)
                if m_id:
                    prop_id = f"homes_{m_id.group(1)[:16]}"

            if not prop_id:
                continue

            primary = building["stations"][0] if building["stations"] else {}

            rooms.append({
                "id": prop_id,
                "source": "homes",
                "source_url": detail_url,
                "name": building["name"],
                "rent": rent,
                "management_fee": admin_fee,
                "deposit": deposit,
                "key_money": key_money,
                "layout": layout,
                "size_sqm": size,
                "floor": floor,
                "total_floors": building["total_floors"],
                "building_age_years": building["building_age_years"],
                "structure": "",
                "address": building["address"],
                "ward": building["ward"],
                "nearest_station": primary.get("station", ""),
                "walk_minutes": primary.get("walk_minutes"),
                "line": primary.get("line", ""),
                "image_url": building["image_url"],
                "features": [],
            })

        return rooms
