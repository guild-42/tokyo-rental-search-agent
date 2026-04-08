"""ハウスコム rental property scraper (housecom.jp)."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from .base import BaseScraper

logger = logging.getLogger(__name__)


def _parse_rent(text: str) -> int:
    text = text.strip()
    if not text or text in ("-", "無"):
        return 0
    m = re.search(r"([\d.]+)\s*万円", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"([\d,]+)\s*円", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0


class HousecomScraper(BaseScraper):
    """Scraper for ハウスコム rental listings."""

    name = "housecom"
    base_url = "https://www.housecom.jp"
    rate_limit = 2.0
    max_pages = 3

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        self.ward_codes = ward_codes

    def build_url(self, page: int) -> str:
        if page == 1:
            return f"{self.base_url}/search/tokyo/"
        return f"{self.base_url}/search/tokyo/?page={page}"

    def parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article.property")
        if not articles:
            articles = soup.select(".property.u--inner")
        results: list[dict] = []

        for article in articles:
            try:
                rooms = self._parse_property(article)
                results.extend(rooms)
            except Exception as e:
                logger.warning(f"[housecom] parse error: {e}")
                continue

        return results

    def _parse_property(self, el: Tag) -> list[dict]:
        # Building info
        build_el = el.select_one(".property_build")
        name = ""
        address = ""
        ward = ""
        stations = []
        age_years = None
        structure = ""
        total_floors = None

        if build_el:
            title_el = build_el.select_one("h3") or build_el.select_one("h2") or build_el.select_one(".property_name")
            if title_el:
                name = title_el.text.strip()

            # Parse dd elements for info
            for dl in build_el.select("dl"):
                dt = dl.select_one("dt")
                dd = dl.select_one("dd")
                if not dt or not dd:
                    continue
                label = dt.text.strip()
                value = dd.text.strip()

                if "所在地" in label or "住所" in label:
                    address = value
                    m = re.search(r"(?:東京都)?(.+?区)", address)
                    if m:
                        ward = m.group(1)

                elif "交通" in label or "最寄" in label:
                    for m in re.finditer(r"(.+?線?)[/／\s]+(.+?駅)\s*.*?徒歩\s*(\d+)分", value):
                        stations.append({
                            "line": m.group(1).strip(),
                            "station": m.group(2).strip(),
                            "walk_minutes": int(m.group(3)),
                        })

                elif "築年" in label:
                    m = re.search(r"築(\d+)年", value)
                    if m:
                        age_years = int(m.group(1))
                    elif "新築" in value:
                        age_years = 0

                elif "構造" in label:
                    structure = value
                    m = re.search(r"(\d+)階建", value)
                    if m:
                        total_floors = int(m.group(1))

        # Image
        img_el = el.select_one("img")
        image_url = ""
        if img_el:
            image_url = img_el.get("src", img_el.get("data-src", ""))
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        # Room details
        rooms = []
        room_els = el.select(".property_room_info")
        if not room_els:
            room_els = [el]

        for room_el in room_els:
            rent = 0
            admin_fee = 0
            layout = ""
            size = None
            floor = None
            deposit = None
            key_money = None

            # Extract text-based data
            text = room_el.text
            # Rent
            m_rent = re.search(r"([\d.]+)\s*万円", text)
            if m_rent:
                rent = int(float(m_rent.group(1)) * 10000)
            if not rent:
                continue

            # Layout
            m_l = re.search(r"(\d[A-Z]+K?|ワンルーム|1R)", text)
            if m_l:
                layout = m_l.group(1)
                if layout == "ワンルーム":
                    layout = "1R"

            # Size
            m_s = re.search(r"([\d.]+)\s*m[²2]", text)
            if m_s:
                size = float(m_s.group(1))

            # Floor
            m_f = re.search(r"(\d+)階", text)
            if m_f:
                floor = int(m_f.group(1))

            # Detail link — housecom uses /room_XXXX/ pattern
            detail_link = (room_el.select_one("a[href*='/room_']") or
                           el.select_one("a[href*='/room_']") or
                           room_el.select_one("a[href*='/build_']") or
                           el.select_one("a[href*='/build_']"))
            detail_url = ""
            if detail_link:
                href = detail_link.get("href", "")
                detail_url = href if href.startswith("http") else f"{self.base_url}{href}"

            # ID
            prop_id = ""
            if detail_url:
                m_id = re.search(r"/room_(\d+)", detail_url)
                if m_id:
                    prop_id = f"housecom_{m_id.group(1)[:16]}"
                else:
                    m_id = re.search(r"/build_(\d+)", detail_url)
                    if m_id:
                        prop_id = f"housecom_{m_id.group(1)[:16]}"
            if not prop_id:
                safe = re.sub(r"\W", "", name)[:10]
                prop_id = f"housecom_{safe}_{rent}"

            primary = stations[0] if stations else {}

            rooms.append({
                "id": prop_id,
                "source": "housecom",
                "source_url": detail_url,
                "name": name,
                "rent": rent,
                "management_fee": admin_fee,
                "deposit": deposit,
                "key_money": key_money,
                "layout": layout,
                "size_sqm": size,
                "floor": floor,
                "total_floors": total_floors,
                "building_age_years": age_years,
                "structure": structure,
                "address": address,
                "ward": ward,
                "nearest_station": primary.get("station", ""),
                "walk_minutes": primary.get("walk_minutes"),
                "line": primary.get("line", ""),
                "image_url": image_url,
                "features": [],
            })

        return rooms
