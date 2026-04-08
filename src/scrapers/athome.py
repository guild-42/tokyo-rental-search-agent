"""at home rental property scraper (athome.co.jp)."""

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


ATHOME_WARD_CODES: dict[str, str] = {
    "千代田区": "13101", "中央区": "13102", "港区": "13103",
    "新宿区": "13104", "文京区": "13105", "台東区": "13106",
    "墨田区": "13107", "江東区": "13108", "品川区": "13109",
    "目黒区": "13110", "大田区": "13111", "世田谷区": "13112",
    "渋谷区": "13113", "中野区": "13114", "杉並区": "13115",
    "豊島区": "13116", "北区": "13117", "荒川区": "13118",
    "板橋区": "13119", "練馬区": "13120", "足立区": "13121",
    "葛飾区": "13122", "江戸川区": "13123",
}


class AtHomeScraper(BaseScraper):
    """Scraper for at home rental listings."""

    name = "athome"
    base_url = "https://www.athome.co.jp"
    rate_limit = 2.0
    max_pages = 5

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        self.ward_codes = ward_codes or list(ATHOME_WARD_CODES.values())

    def build_url(self, page: int) -> str:
        return f"{self.base_url}/chintai/tokyo/list/?DOWN=2&page={page}"

    def parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        buildings = soup.select("div.p-property.p-property--building")
        if not buildings:
            buildings = soup.select("div.p-property")
        results: list[dict] = []

        for building in buildings:
            try:
                rooms = self._parse_building(building)
                results.extend(rooms)
            except Exception as e:
                logger.warning(f"[athome] parse error: {e}")
                continue

        return results

    def _parse_building(self, el: Tag) -> list[dict]:
        # Building name
        title_el = el.select_one("h2.p-property__title--building")
        if not title_el:
            title_el = el.select_one(".p-property__title")
        name = title_el.text.strip() if title_el else ""

        # Address
        address = ""
        ward = ""
        info_hints = el.select("dl.p-property__information-hint")
        for dl in info_hints:
            dt = dl.select_one("dt")
            dd = dl.select_one("dd")
            if dt and dd and "所在地" in dt.text:
                address = dd.text.strip()
                m = re.search(r"東京都(.+?区)", address)
                if m:
                    ward = m.group(1)
                break

        # Station access
        stations = []
        for dl in info_hints:
            dt = dl.select_one("dt")
            dd = dl.select_one("dd")
            if dt and dd and "交通" in dt.text:
                text = dd.text.strip()
                for m in re.finditer(r"(.+?線?)[/／\s]+(.+?駅)\s*.*?徒歩\s*(\d+)分", text):
                    stations.append({
                        "line": m.group(1).strip(),
                        "station": m.group(2).strip(),
                        "walk_minutes": int(m.group(3)),
                    })

        # Image
        img_el = el.select_one("img.js-imgarea")
        if not img_el:
            img_el = el.select_one(".p-property__photo img")
        image_url = ""
        if img_el:
            image_url = img_el.get("src", img_el.get("data-src", ""))
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        # Parse room details
        rooms = []
        room_boxes = el.select("div.p-property__room--detailbox")
        if not room_boxes:
            room_boxes = [el]

        for box in room_boxes:
            # Rent
            rent_el = box.select_one("b.p-property__information-rent")
            if not rent_el:
                rent_el = box.select_one(".p-property__information-price")
            if not rent_el:
                continue

            rent_text = rent_el.text.strip()
            rent = 0
            m = re.search(r"([\d.]+)", rent_text)
            if m:
                rent = int(float(m.group(1)) * 10000)

            # Admin fee
            admin_fee = 0
            price_el = box.select_one("p.p-property__information-price")
            if price_el:
                price_text = price_el.text.strip()
                m_admin = re.search(r"([\d,]+)\s*円", price_text.replace(rent_text, ""))
                if m_admin:
                    admin_fee = int(m_admin.group(1).replace(",", ""))

            # Layout
            layout = ""
            size = None
            floor_el = box.select_one("div.p-property__floor")
            if floor_el:
                layout_text = floor_el.text.strip()
                m_l = re.match(r"(\d[A-Z]+K?|ワンルーム|1R)", layout_text)
                if m_l:
                    layout = m_l.group(1)
                    if layout == "ワンルーム":
                        layout = "1R"

            # Size
            size_els = box.select("div.p-property__information-data")
            for se in size_els:
                text = se.text.strip()
                m_s = re.search(r"([\d.]+)\s*m", text)
                if m_s:
                    size = float(m_s.group(1))
                    break

            # Detail URL
            detail_link = box.select_one("a[href*='/chintai/']")
            detail_url = ""
            if detail_link:
                href = detail_link.get("href", "")
                detail_url = href if href.startswith("http") else f"{self.base_url}{href}"

            # ID
            prop_id = ""
            if detail_url:
                m_id = re.search(r"/(\d{10,})", detail_url)
                if m_id:
                    prop_id = f"athome_{m_id.group(1)[:16]}"
                else:
                    m_id = re.search(r"[/_]([a-z0-9]{8,})", detail_url)
                    if m_id:
                        prop_id = f"athome_{m_id.group(1)[:16]}"

            if not prop_id or not rent:
                continue

            # Floor
            floor = None
            room_num = box.select_one("li.p-property__room-number")
            if room_num:
                m_f = re.search(r"(\d+)階", room_num.text)
                if m_f:
                    floor = int(m_f.group(1))

            # Deposit / key money
            deposit = None
            key_money = None
            dep_els = box.select("div.p-property__information-deposit")
            if not dep_els:
                dep_els = box.select("span.p-property__information-deposit")
            for de in dep_els:
                text = de.text.strip()
                if "敷" in text:
                    deposit = _parse_rent(text)
                elif "礼" in text:
                    key_money = _parse_rent(text)

            primary = stations[0] if stations else {}

            rooms.append({
                "id": prop_id,
                "source": "athome",
                "source_url": detail_url,
                "name": name,
                "rent": rent,
                "management_fee": admin_fee,
                "deposit": deposit,
                "key_money": key_money,
                "layout": layout,
                "size_sqm": size,
                "floor": floor,
                "total_floors": None,
                "building_age_years": None,
                "structure": "",
                "address": address,
                "ward": ward,
                "nearest_station": primary.get("station", ""),
                "walk_minutes": primary.get("walk_minutes"),
                "line": primary.get("line", ""),
                "image_url": image_url,
                "features": [],
            })

        return rooms
