"""DOOR賃貸 rental property scraper (door.ac)."""

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
    m = re.search(r"([\d.]+)\s*万", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"([\d,]+)\s*円", text)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r"([\d.]+)", text)
    if m and float(m.group(1)) < 100:
        return int(float(m.group(1)) * 10000)
    return 0


class DoorScraper(BaseScraper):
    """Scraper for DOOR賃貸 rental listings."""

    name = "door"
    base_url = "https://door.ac"
    rate_limit = 2.0
    max_pages = 5

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        # DOOR uses different URL structure - just fetch all Tokyo
        self.ward_codes = ward_codes

    def build_url(self, page: int) -> str:
        if page == 1:
            return f"{self.base_url}/tokyo/list"
        return f"{self.base_url}/tokyo/list?page={page}"

    def parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        buildings = soup.select("div.building-box")
        results: list[dict] = []

        for building in buildings:
            try:
                rooms = self._parse_building(building)
                results.extend(rooms)
            except Exception as e:
                logger.warning(f"[door] parse error: {e}")
                continue

        return results

    def _parse_building(self, el: Tag) -> list[dict]:
        # Building name
        heading = el.select_one("h2.heading")
        if not heading:
            heading = el.select_one("div.building-box__head")
        name = heading.text.strip() if heading else ""

        # Building type
        label_el = el.select_one("div.label")
        building_type = label_el.text.strip() if label_el else ""

        # Description items
        address = ""
        ward = ""
        stations = []
        age_years = None
        total_floors = None
        structure = ""

        desc_items = el.select("dl.description-item")
        for dl in desc_items:
            dt = dl.select_one("dt")
            dd = dl.select_one("dd")
            if not dt or not dd:
                continue
            label = dt.text.strip()
            value = dd.text.strip()

            if "住所" in label or "所在地" in label:
                address = value
                m = re.search(r"東京都(.+?区)", address)
                if m:
                    ward = m.group(1)

            elif "交通" in label:
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

            elif "階建" in label:
                m = re.search(r"(\d+)階建", value)
                if m:
                    total_floors = int(m.group(1))

            elif "構造" in label:
                structure = value

        # Station from dedicated element
        station_dls = el.select("dl.description-item--station")
        for dl in station_dls:
            dd = dl.select_one("dd")
            if dd:
                for m in re.finditer(r"(.+?線?)[/／\s]+(.+?駅)\s*.*?徒歩\s*(\d+)分", dd.text):
                    stations.append({
                        "line": m.group(1).strip(),
                        "station": m.group(2).strip(),
                        "walk_minutes": int(m.group(3)),
                    })

        # Image
        img_el = el.select_one("img")
        image_url = ""
        if img_el:
            image_url = img_el.get("src", img_el.get("data-src", ""))
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        # Parse room rows from table
        rooms = []
        table = el.select_one("table.table-secondary")
        if not table:
            return rooms

        rows = table.select("tr")
        for row in rows:
            if row.select_one(".table-head"):
                continue
            tds = row.select("td")
            if len(tds) < 5:
                continue

            # Parse columns: floor, rent, admin, deposit/key, layout, area
            floor = None
            m_f = re.search(r"(\d+)階", tds[0].text)
            if m_f:
                floor = int(m_f.group(1))

            # Rent
            rent_el = tds[1].select_one("em.emphasis-primary")
            if rent_el:
                rent = _parse_rent(rent_el.text)
            else:
                rent = _parse_rent(tds[1].text)
            if not rent:
                continue

            # Admin fee
            admin_fee = _parse_rent(tds[2].text) if len(tds) > 2 else 0

            # Deposit / key money
            deposit = None
            key_money = None
            if len(tds) > 3:
                dep_text = tds[3].text.strip()
                parts = re.split(r"[/／\n]", dep_text)
                if len(parts) >= 1:
                    deposit = _parse_rent(parts[0]) or None
                if len(parts) >= 2:
                    key_money = _parse_rent(parts[1]) or None

            # Layout
            layout = ""
            if len(tds) > 4:
                m_l = re.match(r"(\d[A-Z]+K?|ワンルーム|1R)", tds[4].text.strip())
                if m_l:
                    layout = m_l.group(1)
                    if layout == "ワンルーム":
                        layout = "1R"

            # Size
            size = None
            if len(tds) > 5:
                m_s = re.search(r"([\d.]+)\s*m", tds[5].text)
                if m_s:
                    size = float(m_s.group(1))

            # Detail URL — door uses /buildings/.../properties/... pattern
            detail_link = row.select_one("a[href*='/properties/']")
            if not detail_link:
                detail_link = row.select_one("a[href*='/buildings/']")
            detail_url = ""
            if detail_link:
                href = detail_link.get("href", "")
                detail_url = href if href.startswith("http") else f"{self.base_url}{href}"

            # Also check building-level link
            if not detail_url:
                bld_link = el.select_one("a[href*='/buildings/']")
                if bld_link:
                    href = bld_link.get("href", "")
                    detail_url = href if href.startswith("http") else f"{self.base_url}{href}"

            # ID
            prop_id = ""
            if detail_url:
                m_id = re.search(r"/properties/([a-f0-9-]+)", detail_url)
                if m_id:
                    prop_id = f"door_{m_id.group(1)[:16]}"
                else:
                    m_id = re.search(r"/buildings/([a-f0-9-]+)", detail_url)
                    if m_id:
                        prop_id = f"door_{m_id.group(1)[:16]}_{floor or 0}"
            if not prop_id:
                safe_name = re.sub(r"\W", "", name)[:12]
                prop_id = f"door_{safe_name}_{floor or 0}_{rent}"

            primary = stations[0] if stations else {}

            rooms.append({
                "id": prop_id,
                "source": "door",
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
                "structure": structure or building_type,
                "address": address,
                "ward": ward,
                "nearest_station": primary.get("station", ""),
                "walk_minutes": primary.get("walk_minutes"),
                "line": primary.get("line", ""),
                "image_url": image_url,
                "features": [],
            })

        return rooms
