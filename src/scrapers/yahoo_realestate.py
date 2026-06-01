"""Yahoo!不動産 rental property scraper (realestate.yahoo.co.jp)."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from .base import BaseScraper

logger = logging.getLogger(__name__)

YAHOO_WARD_CODES: dict[str, str] = {
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
    text = text.strip()
    if not text or text in ("-", "無", "なし"):
        return 0
    m = re.search(r"([\d.]+)\s*万円", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"([\d,]+)\s*円", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0


class YahooRealestateScraper(BaseScraper):
    """Scraper for Yahoo!不動産 rental listings.

    Structure: li.ListBukken__item contains both
    div.ListCassette (building info) and div.ListCassetteRoom (room list).
    """

    name = "yahoo"
    base_url = "https://realestate.yahoo.co.jp"
    rate_limit = 2.5
    # Yahoo doesn't accept any URL-based rent filter we can find. We grab
    # deeply, rely on base.py's early-stop when a whole page > 10万, and on
    # the orchestrator's final rent filter.
    max_pages = 5

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        self.ward_codes = ward_codes or list(YAHOO_WARD_CODES.values())
        self._current_ward_code = self.ward_codes[0] if self.ward_codes else "13101"

    def build_url(self, page: int) -> str:
        code = self._current_ward_code
        if page == 1:
            return f"{self.base_url}/rent/search/03/13/{code}/"
        return f"{self.base_url}/rent/search/03/13/{code}/?page={page}"

    async def fetch_latest(self) -> list[dict]:
        """Override: fetch each ward separately."""
        all_listings: list[dict] = []
        for code in self.ward_codes:
            self._current_ward_code = code
            ward_name = next((k for k, v in YAHOO_WARD_CODES.items() if v == code), code)
            logger.info(f"[{self.name}] fetching ward: {ward_name} ({code})")
            listings = await super().fetch_latest()
            all_listings.extend(listings)
            logger.info(f"[{self.name}] {ward_name}: {len(listings)} listings")
        return all_listings

    def parse_total_count(self, html: str) -> int | None:
        """Yahoo!不動産 shows '全XX件中' in the result header."""
        from .base import parse_total_count_japanese
        return parse_total_count_japanese(html)

    def parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        # Each li.ListBukken__item contains one building + its rooms
        bukken_items = soup.select("li.ListBukken__item")
        results: list[dict] = []

        for item in bukken_items:
            try:
                rooms = self._parse_bukken(item)
                results.extend(rooms)
            except Exception as e:
                logger.warning(f"[yahoo] parse error: {e}")
                continue

        return results

    def _parse_bukken(self, item: Tag) -> list[dict]:
        """Parse a ListBukken__item containing building + room data."""
        # --- Building info from ListCassette ---
        cassette = item.select_one("div.ListCassette")
        name = ""
        address = ""
        ward = ""
        stations = []
        age_years = None
        structure = ""
        building_image = ""

        if cassette:
            title_el = cassette.select_one("h2.ListCassette__ttl__txt")
            name = title_el.text.strip() if title_el else ""

            img_el = cassette.select_one("img.ListCassette__thumb__img")
            if img_el:
                building_image = img_el.get("src", "")
                if building_image.startswith("//"):
                    building_image = "https:" + building_image

            # Info spans contain: stations, address, age/structure
            spans = cassette.select("span.ListCassette__txt")
            for span in spans:
                text = span.text.strip()

                # Station: "XX駅/XX線 徒歩X分"
                m_st = re.search(r"(.+?駅)[/／](.+?線?)\s+徒歩(\d+)分", text)
                if not m_st:
                    m_st = re.search(r"(.+?駅)[/／](.+?)\s+徒歩(\d+)", text)
                if m_st:
                    stations.append({
                        "station": m_st.group(1),
                        "line": m_st.group(2),
                        "walk_minutes": int(m_st.group(3)),
                    })
                    continue

                # "徒歩1分以内" pattern
                m_st2 = re.search(r"(.+?駅)[/／](.+?)\s+徒歩\d+分以内", text)
                if m_st2:
                    stations.append({
                        "station": m_st2.group(1),
                        "line": m_st2.group(2),
                        "walk_minutes": 1,
                    })
                    continue

                # Address (contains 区 or 都)
                if re.search(r"東京都|[区]", text) and not re.search(r"駅|線|築|階建", text):
                    address = text
                    m_w = re.search(r"(?:東京都)?(.+?区)", text)
                    if m_w:
                        ward = m_w.group(1)
                    continue

                # Age / structure: "築12年/地上21階建て/鉄骨鉄筋コンクリート"
                m_age = re.search(r"築(\d+)年", text)
                if m_age:
                    age_years = int(m_age.group(1))
                if "新築" in text:
                    age_years = 0
                for s in ("鉄骨鉄筋", "鉄筋", "鉄骨", "RC", "SRC", "木造", "軽量鉄骨"):
                    if s in text:
                        structure = text
                        break

        # --- Room data from ListCassetteRoom ---
        rooms = []
        room_items = item.select("li.ListCassetteRoom__item")

        for ri in room_items:
            # Rent
            price_el = ri.select_one("div.ListCassetteRoom__dtl__price")
            if not price_el:
                continue
            price_text = price_el.text.strip()
            rent = _parse_rent(price_text)
            if not rent:
                continue

            # Admin fee
            admin_fee = 0
            m_admin = re.search(r"管理費等\s*([\d,]+)\s*円", price_text)
            if m_admin:
                admin_fee = int(m_admin.group(1).replace(",", ""))
            else:
                m_admin = re.search(r"管理費等\s*([\d.]+)\s*万円", price_text)
                if m_admin:
                    admin_fee = int(float(m_admin.group(1)) * 10000)

            # Layout + area
            layout = ""
            size = None
            layout_els = ri.select("div.ListCassetteRoom__dtl__layout")
            if len(layout_els) >= 1:
                l_text = layout_els[0].text.strip()
                m_l = re.match(r"(\d[A-Z]+K?|ワンルーム|1R)", l_text)
                if m_l:
                    layout = m_l.group(1)
                    if layout == "ワンルーム":
                        layout = "1R"
            if len(layout_els) >= 2:
                s_text = layout_els[1].text.strip()
                m_s = re.search(r"([\d.]+)\s*m", s_text)
                if m_s:
                    size = float(m_s.group(1))

            # Deposit / key money
            deposit = None
            key_money = None
            dep_el = ri.select_one("div.ListCassetteRoom__dtl__deposit")
            if dep_el:
                dep_text = dep_el.text.strip()
                # "敷 30.1万円 / 礼 30.1万円" or similar
                m_dep = re.search(r"敷.*?([\d.]+)\s*万円", dep_text)
                if m_dep:
                    deposit = int(float(m_dep.group(1)) * 10000)
                m_key = re.search(r"礼.*?([\d.]+)\s*万円", dep_text)
                if m_key:
                    key_money = int(float(m_key.group(1)) * 10000)

            # Floor
            floor = None
            floor_el = ri.select_one("div.ListCassetteRoom__dtl__floor")
            if floor_el:
                m_f = re.search(r"(\d+)階", floor_el.text)
                if m_f:
                    floor = int(m_f.group(1))

            # Room image
            room_img = ri.select_one("img.ListCassetteRoom__thumb__img")
            if not room_img:
                room_img = ri.select_one("img")
            room_image = ""
            if room_img:
                room_image = room_img.get("src", "")
                if room_image.startswith("//"):
                    room_image = "https:" + room_image

            # Detail link
            detail_link = ri.select_one("a[href*='/rent/detail/']")
            if not detail_link:
                detail_link = ri.select_one("a[href*='/rent/']")
            detail_url = ""
            if detail_link:
                href = detail_link.get("href", "")
                detail_url = href if href.startswith("http") else f"{self.base_url}{href}"

            # ID from URL
            prop_id = ""
            if detail_url:
                m_id = re.search(r"/detail/[_]?([a-f0-9]{16,})", detail_url)
                if m_id:
                    prop_id = f"yahoo_{m_id.group(1)[:16]}"
                else:
                    m_id = re.search(r"/detail/([^/]+)", detail_url)
                    if m_id:
                        clean = re.sub(r"[^a-f0-9]", "", m_id.group(1))
                        prop_id = f"yahoo_{clean[:16]}" if clean else ""

            if not prop_id:
                continue

            primary = stations[0] if stations else {}

            rooms.append({
                "id": prop_id,
                "source": "yahoo",
                "source_url": detail_url,
                "name": name,
                "rent": rent,
                "management_fee": admin_fee,
                "deposit": deposit or None,
                "key_money": key_money or None,
                "layout": layout,
                "size_sqm": size,
                "floor": floor,
                "total_floors": None,
                "building_age_years": age_years,
                "structure": structure,
                "address": address,
                "ward": ward,
                "nearest_station": primary.get("station", ""),
                "walk_minutes": primary.get("walk_minutes"),
                "line": primary.get("line", ""),
                "image_url": room_image or building_image,
                "features": [],
            })

        return rooms
