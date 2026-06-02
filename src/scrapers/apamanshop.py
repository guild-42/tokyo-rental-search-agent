"""アパマンショップ rental property scraper (apamanshop.com)."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Apamanshop uses 3-digit area codes for Tokyo wards
APAMAN_WARD_CODES: dict[str, str] = {
    "千代田区": "101", "中央区": "102", "港区": "103",
    "新宿区": "104", "文京区": "105", "台東区": "106",
    "墨田区": "107", "江東区": "108", "品川区": "109",
    "目黒区": "110", "大田区": "111", "世田谷区": "112",
    "渋谷区": "113", "中野区": "114", "杉並区": "115",
    "豊島区": "116", "北区": "117", "荒川区": "118",
    "板橋区": "119", "練馬区": "120", "足立区": "121",
    "葛飾区": "122", "江戸川区": "123",
}


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


class ApamanshopScraper(BaseScraper):
    """Scraper for アパマンショップ rental listings."""

    name = "apamanshop"
    base_url = "https://www.apamanshop.com"
    rate_limit = 2.0
    max_pages = 5

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        # Convert standard 5-digit codes to 3-digit apaman codes
        if ward_codes:
            self.apaman_codes = []
            code_map = {v: k for k, v in APAMAN_WARD_CODES.items()}
            std_to_apaman = {}
            for ward, ac in APAMAN_WARD_CODES.items():
                for sw, sc in [("千代田区", "13101"), ("中央区", "13102"), ("港区", "13103"),
                               ("新宿区", "13104"), ("文京区", "13105"), ("台東区", "13106"),
                               ("墨田区", "13107"), ("江東区", "13108"), ("品川区", "13109"),
                               ("目黒区", "13110"), ("大田区", "13111"), ("世田谷区", "13112"),
                               ("渋谷区", "13113"), ("中野区", "13114"), ("杉並区", "13115"),
                               ("豊島区", "13116"), ("北区", "13117"), ("荒川区", "13118"),
                               ("板橋区", "13119"), ("練馬区", "13120"), ("足立区", "13121"),
                               ("葛飾区", "13122"), ("江戸川区", "13123")]:
                    if ward == sw:
                        std_to_apaman[sc] = ac
            for wc in ward_codes:
                if wc in std_to_apaman:
                    self.apaman_codes.append(std_to_apaman[wc])
            if not self.apaman_codes:
                self.apaman_codes = list(APAMAN_WARD_CODES.values())
        else:
            self.apaman_codes = list(APAMAN_WARD_CODES.values())

        self._current_code = self.apaman_codes[0]

    def build_url(self, page: int) -> str:
        # tinryo1 / tinryo2 are rent min / max in yen units. 200000 = 20万円.
        code = self._current_code
        filters = "tinryo1=0&tinryo2=200000"
        if page == 1:
            return f"{self.base_url}/tokyo/{code}/?{filters}"
        return f"{self.base_url}/tokyo/{code}/?{filters}&page={page}"

    def parse_total_count(self, html: str) -> int | None:
        from .base import parse_total_count_japanese
        return parse_total_count_japanese(html)

    async def fetch_latest(self) -> list[dict]:
        all_listings: list[dict] = []
        for code in self.apaman_codes:
            self._current_code = code
            ward_name = next((k for k, v in APAMAN_WARD_CODES.items() if v == code), code)
            logger.info(f"[{self.name}] fetching ward: {ward_name} ({code})")
            listings = await super().fetch_latest()
            all_listings.extend(listings)
            logger.info(f"[{self.name}] {ward_name}: {len(listings)} listings")
        return all_listings

    def parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        # Find listing items
        items = soup.select("div.bukken") or soup.select("div.property_list_item") or soup.select("article")
        results: list[dict] = []

        # Also try room rows
        room_rows = soup.select(".list_icn_room") or soup.select("tr.room_row")

        if items:
            for item in items:
                try:
                    parsed = self._parse_item(item)
                    if parsed:
                        results.extend(parsed) if isinstance(parsed, list) else results.append(parsed)
                except Exception as e:
                    logger.warning(f"[apamanshop] parse error: {e}")

        return results

    def _parse_item(self, el: Tag) -> list[dict]:
        text = el.text
        rooms = []

        # Name
        title_el = el.select_one("h3") or el.select_one("h2") or el.select_one(".bukken_name")
        name = title_el.text.strip() if title_el else ""

        # Address
        address = ""
        ward = ""
        m_addr = re.search(r"(東京都.+?区[^\s]*)", text)
        if m_addr:
            address = m_addr.group(1).strip()
            m_w = re.search(r"東京都(.+?区)", address)
            if m_w:
                ward = m_w.group(1)

        # Stations
        stations = []
        for m in re.finditer(r"(.+?線?)[/／\s]+(.+?駅)\s*.*?徒歩\s*(\d+)分", text):
            stations.append({
                "line": m.group(1).strip(),
                "station": m.group(2).strip(),
                "walk_minutes": int(m.group(3)),
            })

        # Age
        age_years = None
        m_age = re.search(r"築(\d+)年", text)
        if m_age:
            age_years = int(m_age.group(1))

        # Image
        img_el = el.select_one("img")
        image_url = ""
        if img_el:
            image_url = img_el.get("src", img_el.get("data-src", ""))
            if image_url.startswith("//"):
                image_url = "https:" + image_url
            elif image_url.startswith("/"):
                image_url = f"{self.base_url}{image_url}"

        # Find all rent mentions
        rent_matches = list(re.finditer(r"([\d.]+)\s*万円", text))
        if not rent_matches:
            return rooms

        # Detail links — apamanshop uses /tokyo/XXX/bXXX/XXXXX/ pattern
        detail_links = el.select("a[href*='詳細']")
        if not detail_links:
            # Find links containing room IDs (long numeric paths)
            detail_links = [a for a in el.select("a[href]")
                            if re.search(r"/b\d+/\d+/", a.get("href", ""))]
        if not detail_links:
            detail_links = [a for a in el.select("a[href]")
                            if re.search(r"/tokyo/\d+/b\d+", a.get("href", ""))]

        for i, m_r in enumerate(rent_matches[:5]):
            rent = int(float(m_r.group(1)) * 10000)
            if rent < 10000:
                continue

            detail_url = ""
            if i < len(detail_links):
                href = detail_links[i].get("href", "")
                # Strip query params like ?media_nm=
                href = re.sub(r"\?.*$", "", href)
                detail_url = href if href.startswith("http") else f"{self.base_url}{href}"

            # Also try bukken_cd_check input values for room ID
            if not detail_url:
                checks = el.select("input.bukken_cd_check")
                if i < len(checks):
                    val = checks[i].get("value", "")
                    if val:
                        # Construct URL from building link + room value
                        bld_link = el.select_one("a[href*='/b']")
                        if bld_link:
                            bld_href = bld_link.get("href", "")
                            bld_href = re.sub(r"\?.*$", "", bld_href)
                            detail_url = f"{self.base_url}{bld_href}{val}/"

            prop_id = ""
            if detail_url:
                m_id = re.search(r"/(\d{10,})", detail_url)
                if m_id:
                    prop_id = f"apaman_{m_id.group(1)[:16]}"
                else:
                    m_id = re.search(r"/b(\d+)", detail_url)
                    if m_id:
                        prop_id = f"apaman_{m_id.group(1)[:16]}_{i}"
            if not prop_id:
                safe = re.sub(r"\W", "", name)[:10]
                prop_id = f"apaman_{safe}_{rent}_{i}"

            primary = stations[0] if stations else {}

            rooms.append({
                "id": prop_id,
                "source": "apamanshop",
                "source_url": detail_url,
                "name": name,
                "rent": rent,
                "management_fee": 0,
                "deposit": None,
                "key_money": None,
                "layout": "",
                "size_sqm": None,
                "floor": None,
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
            })

        return rooms
