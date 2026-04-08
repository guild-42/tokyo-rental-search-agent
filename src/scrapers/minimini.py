"""minimini rental property scraper (minimini.jp)."""

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


class MiniminiScraper(BaseScraper):
    """Scraper for minimini rental listings."""

    name = "minimini"
    base_url = "https://minimini.jp"
    rate_limit = 2.0
    max_pages = 3

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        self.ward_codes = ward_codes

    def build_url(self, page: int) -> str:
        if page == 1:
            return f"{self.base_url}/list/?pref=13"
        return f"{self.base_url}/list/?pref=13&dp={page}"

    def parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("div.bukken.clearfix")
        if not items:
            items = soup.select("div.bukken")
        results: list[dict] = []

        for item in items:
            try:
                parsed = self._parse_item(item)
                if parsed:
                    results.append(parsed)
            except Exception as e:
                logger.warning(f"[minimini] parse error: {e}")
                continue

        return results

    def _parse_item(self, el: Tag) -> dict | None:
        # Name
        title_el = el.select_one("h3") or el.select_one("h2") or el.select_one(".bukken_name")
        name = title_el.text.strip() if title_el else ""

        # Address
        address = ""
        ward = ""
        addr_els = el.select("td")
        text_block = el.text
        m_addr = re.search(r"(東京都.+?区.+?)(?:\s|$)", text_block)
        if m_addr:
            address = m_addr.group(1).strip()
            m_w = re.search(r"東京都(.+?区)", address)
            if m_w:
                ward = m_w.group(1)

        # Station
        stations = []
        for m in re.finditer(r"(.+?線?)[/／\s]+(.+?駅)\s*.*?徒歩\s*(\d+)分", text_block):
            stations.append({
                "line": m.group(1).strip(),
                "station": m.group(2).strip(),
                "walk_minutes": int(m.group(3)),
            })

        # Rent from table
        rent = 0
        rent_td = el.select_one("td.chiryo")
        if rent_td:
            rent = _parse_rent(rent_td.text)
        if not rent:
            # Try finding rent in text
            m_r = re.search(r"([\d.]+)\s*万円", text_block)
            if m_r:
                rent = int(float(m_r.group(1)) * 10000)
        if not rent:
            return None

        # Admin fee
        admin_fee = 0
        admin_td = el.select_one("td.kanrihi")
        if admin_td:
            admin_fee = _parse_rent(admin_td.text)

        # Deposit
        deposit = None
        dep_td = el.select_one("td.shikikin")
        if dep_td:
            deposit = _parse_rent(dep_td.text) or None

        # Key money
        key_money = None
        key_td = el.select_one("td.reikin")
        if key_td:
            key_money = _parse_rent(key_td.text) or None

        # Layout
        layout = ""
        m_l = re.search(r"(\d[A-Z]+K?|ワンルーム|1R)", text_block)
        if m_l:
            layout = m_l.group(1)
            if layout == "ワンルーム":
                layout = "1R"

        # Size
        size = None
        m_s = re.search(r"([\d.]+)\s*m[²2]", text_block)
        if m_s:
            size = float(m_s.group(1))

        # Floor
        floor = None
        m_f = re.search(r"(\d+)階/", text_block)
        if m_f:
            floor = int(m_f.group(1))

        # Age
        age_years = None
        m_age = re.search(r"築(\d+)年", text_block)
        if m_age:
            age_years = int(m_age.group(1))
        elif "新築" in text_block:
            age_years = 0

        # Image
        img_el = el.select_one("img")
        image_url = ""
        if img_el:
            image_url = img_el.get("src", img_el.get("data-src", ""))
            if image_url.startswith("//"):
                image_url = "https:" + image_url
            elif image_url.startswith("/"):
                image_url = f"{self.base_url}{image_url}"

        # Detail URL
        detail_link = el.select_one("a[href*='/detail/']") or el.select_one("a[href*='/room/']")
        detail_url = ""
        if detail_link:
            href = detail_link.get("href", "")
            detail_url = href if href.startswith("http") else f"{self.base_url}{href}"

        # ID
        prop_id = ""
        if detail_url:
            m_id = re.search(r"/(?:detail|room)/([^/]+)", detail_url)
            if m_id:
                prop_id = f"minimini_{m_id.group(1)[:16]}"
        if not prop_id:
            safe = re.sub(r"\W", "", name)[:10]
            prop_id = f"minimini_{safe}_{rent}"

        primary = stations[0] if stations else {}

        return {
            "id": prop_id,
            "source": "minimini",
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
            "building_age_years": age_years,
            "structure": "",
            "address": address,
            "ward": ward,
            "nearest_station": primary.get("station", ""),
            "walk_minutes": primary.get("walk_minutes"),
            "line": primary.get("line", ""),
            "image_url": image_url,
            "features": [],
        }
