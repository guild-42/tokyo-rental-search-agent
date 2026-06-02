"""CHINTAI rental property scraper (chintai.net)."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from .base import BaseScraper

logger = logging.getLogger(__name__)

# CHINTAI area codes for Tokyo 23 wards
CHINTAI_WARD_CODES: dict[str, str] = {
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
    m = re.search(r"([\d.]+)万円", text)
    if m:
        return int(float(m.group(1)) * 10000)
    # "26万円" format with separate num span
    m = re.search(r"(\d+)", text)
    if m and "万" in text:
        return int(m.group(1)) * 10000
    m = re.search(r"([\d,]+)円", text)
    if m:
        return int(m.group(1).replace(",", ""))
    # Plain number like "10,000"
    m = re.search(r"([\d,]+)", text)
    if m and len(m.group(1).replace(",", "")) >= 4:
        return int(m.group(1).replace(",", ""))
    return 0


class ChintaiScraper(BaseScraper):
    """Scraper for CHINTAI rental listings."""

    name = "chintai"
    base_url = "https://www.chintai.net"
    rate_limit = 2.0
    max_pages = 5

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        self.ward_codes = ward_codes or list(CHINTAI_WARD_CODES.values())
        self._current_ward_code = self.ward_codes[0] if self.ward_codes else "13101"

    def build_url(self, page: int) -> str:
        # CHINTAI only supports single ward code per URL.
        # ct/cf values are in 千円 units: ct=120 = 120 * 千円 = 12万円 上限.
        code = self._current_ward_code
        filters = "sort=2&cf=0&ct=120"
        if page == 1:
            return f"{self.base_url}/tokyo/area/{code}/list/?{filters}"
        return f"{self.base_url}/tokyo/area/{code}/list/page{page}/?o=10&{filters}"

    async def fetch_latest(self) -> list[dict]:
        """Override: fetch each ward separately, then combine."""
        all_listings: list[dict] = []
        for code in self.ward_codes:
            self._current_ward_code = code
            ward_name = next((k for k, v in CHINTAI_WARD_CODES.items() if v == code), code)
            logger.info(f"[{self.name}] fetching ward: {ward_name} ({code})")
            listings = await super().fetch_latest()
            all_listings.extend(listings)
            logger.info(f"[{self.name}] {ward_name}: {len(listings)} listings")
        return all_listings

    def parse_total_count(self, html: str) -> int | None:
        from .base import parse_total_count_japanese
        return parse_total_count_japanese(html)

    def parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".cassette_item")
        results: list[dict] = []

        for item in items:
            try:
                # Skip PR items
                ttl = item.select_one(".cassette_ttl")
                if ttl and ttl.text.strip().startswith("PR"):
                    continue
                parsed = self._parse_item(item)
                if parsed:
                    results.append(parsed)
            except Exception as e:
                logger.warning(f"[chintai] parse error: {e}")
                continue

        return results

    def _parse_item(self, item: Tag) -> dict | None:
        # Title: building type + name
        ttl = item.select_one(".cassette_ttl h2")
        if not ttl:
            return None

        type_el = ttl.select_one(".icn_typeB")
        building_type = type_el.text.strip() if type_el else ""
        name = ttl.text.replace(building_type, "").strip()

        # Building info table
        info_table = item.select_one(".bukken_information table")
        address = ""
        ward = ""
        stations = []
        age_years = None
        total_floors = None
        structure = ""
        lat = None
        lng = None

        if info_table:
            rows = info_table.select("tr")
            for row in rows:
                ths = row.select("th")
                tds = row.select("td")
                for th, td in zip(ths, tds):
                    label = th.text.strip()
                    value = td.text.strip()

                    if label == "住所":
                        address = re.sub(r"\s*周辺地図\s*", "", value).strip()
                        m = re.search(r"東京都(.+?区)", address)
                        if m:
                            ward = m.group(1)

                    elif label == "交通":
                        for li in td.select("li"):
                            m = re.match(r"(.+?)[/／](.+?駅)\s*徒歩(\d+)分", li.text.strip())
                            if m:
                                stations.append({
                                    "line": m.group(1),
                                    "station": m.group(2),
                                    "walk_minutes": int(m.group(3)),
                                })

                    elif label == "築年":
                        m = re.search(r"築(\d+)年", value)
                        if m:
                            age_years = int(m.group(1))
                        elif "新築" in value:
                            age_years = 0

                    elif label == "階建":
                        m = re.search(r"(\d+)階建", value)
                        if m:
                            total_floors = int(m.group(1))

                    elif label == "構造":
                        structure = value

        # Extract lat/lng from onclick="showGoogleMap(lat, lng, ...)"
        map_link = item.select_one("a[onclick*='showGoogleMap']")
        if map_link:
            onclick = map_link.get("onclick", "")
            m = re.search(r"showGoogleMap\(([\d.]+),\s*([\d.]+)", onclick)
            if m:
                lat = float(m.group(1))
                lng = float(m.group(2))

        # Room detail from cassette_detail table
        detail_table = item.select_one(".cassette_detail table")
        if not detail_table:
            return None

        tbody = detail_table.select_one("tbody.js-detailLinkUrl")
        if not tbody:
            return None

        detail_url_path = tbody.get("data-detailurl", "")
        detail_url = f"{self.base_url}{detail_url_path}" if detail_url_path else ""
        bk_key = tbody.get("data-bkkey", "")

        tr = tbody.select_one("tr.detail-inner")
        if not tr:
            return None

        # Floor
        floor = None
        floor_td = tr.select_one("td.floar")
        if floor_td:
            m = re.search(r"(\d+)階", floor_td.text.strip())
            if m:
                floor = int(m.group(1))

        # Rent + admin
        rent = 0
        admin_fee = 0
        price_td = tr.select_one("td.price")
        if price_td:
            # Rent: <span class="num">26</span>万円 or <span class="num">12.6</span>万円
            num_span = price_td.select_one("span.num")
            if num_span:
                rent = int(float(num_span.text.strip()) * 10000)
            else:
                rent = _parse_rent(price_td.text.strip())
            # Admin fee: after <br/>, e.g. "10,000円"
            br = price_td.find("br")
            if br and br.next_sibling:
                admin_text = br.next_sibling.strip() if isinstance(br.next_sibling, str) else br.next_sibling.text.strip()
                admin_fee = _parse_rent(admin_text)

        # Deposit / key money
        deposit = None
        key_money = None
        other_td = tr.select_one("td.other_price")
        if other_td:
            spans = other_td.select("span")
            texts = [s.text.strip() for s in spans]
            if not texts:
                texts = [l.strip() for l in other_td.text.strip().split("\n") if l.strip()]
            if len(texts) >= 1:
                dep = texts[0]
                m = re.search(r"([\d.]+)ヶ月", dep)
                if m:
                    deposit = int(float(m.group(1)) * rent) if rent else 0
                elif dep not in ("-", "無", "なし", ""):
                    deposit = _parse_rent(dep)
            if len(texts) >= 2:
                key = texts[1]
                m = re.search(r"([\d.]+)ヶ月", key)
                if m:
                    key_money = int(float(m.group(1)) * rent) if rent else 0
                elif key not in ("-", "無", "なし", ""):
                    key_money = _parse_rent(key)

        # Layout + size (6th td)
        layout = ""
        size = None
        layout_tds = tr.select("td.clickArea")
        for ltd in layout_tds:
            text = ltd.text.strip()
            if re.search(r"\d[A-Z]|ワンルーム|1R", text):
                m_l = re.match(r"(\d[A-Z]+K?|ワンルーム|1R)", text)
                if m_l:
                    layout = m_l.group(1)
                    if layout == "ワンルーム":
                        layout = "1R"
                m_s = re.search(r"([\d.]+)\s*m", text)
                if m_s:
                    size = float(m_s.group(1))
                break

        # Image
        img_el = item.select_one(".photo_box img.photo")
        image_url = ""
        if img_el:
            image_url = img_el.get("data-original", img_el.get("src", ""))
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        prop_id = f"chintai_{bk_key[:20]}" if bk_key else ""
        if not prop_id:
            return None

        primary = stations[0] if stations else {}

        return {
            "id": prop_id,
            "source": "chintai",
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
            "lat": lat,
            "lng": lng,
            "nearest_station": primary.get("station", ""),
            "walk_minutes": primary.get("walk_minutes"),
            "line": primary.get("line", ""),
            "image_url": image_url,
            "features": [],
        }
