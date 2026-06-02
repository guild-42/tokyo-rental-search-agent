"""at home rental property scraper (athome.co.jp)."""

from __future__ import annotations

import asyncio
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

# athome URLs are per-ward path slugs (romaji + "-city"), e.g. shinjuku-city.
ATHOME_WARD_SLUGS: dict[str, str] = {
    "13101": "chiyoda-city", "13102": "chuo-city", "13103": "minato-city",
    "13104": "shinjuku-city", "13105": "bunkyo-city", "13106": "taito-city",
    "13107": "sumida-city", "13108": "koto-city", "13109": "shinagawa-city",
    "13110": "meguro-city", "13111": "ota-city", "13112": "setagaya-city",
    "13113": "shibuya-city", "13114": "nakano-city", "13115": "suginami-city",
    "13116": "toshima-city", "13117": "kita-city", "13118": "arakawa-city",
    "13119": "itabashi-city", "13120": "nerima-city", "13121": "adachi-city",
    "13122": "katsushika-city", "13123": "edogawa-city",
}


class AtHomeScraper(BaseScraper):
    """Scraper for at home rental listings."""

    name = "athome"
    base_url = "https://www.athome.co.jp"
    # athome serves a JS "認証中" interstitial under rapid access, so pace
    # requests generously to stay under its bot-protection threshold.
    rate_limit = 4.0
    max_pages = 5

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        self.ward_codes = ward_codes or list(ATHOME_WARD_CODES.values())
        first = self.ward_codes[0] if self.ward_codes else "13104"
        self._current_slug = ATHOME_WARD_SLUGS.get(first, "shinjuku-city")

    def build_url(self, page: int) -> str:
        # Per-ward slug path, newest-first, path-based pagination.
        base = f"{self.base_url}/chintai/tokyo/{self._current_slug}/list"
        if page == 1:
            return f"{base}/?bukken-sort=newdate"
        return f"{base}/page{page}/?bukken-sort=newdate"

    async def fetch_latest(self) -> list[dict]:
        """Fetch each ward separately (athome paths are per-ward slugs).

        Resilience mirrors HOME'S: athome throttles with a "認証中" page
        (HTTP 200, no listings) under load, so isolate each ward with
        try/except — one challenged ward shouldn't kill the rest. A
        CancelledError (orchestrator timeout) returns partial results.
        """
        all_listings: list[dict] = []
        for code in self.ward_codes:
            slug = ATHOME_WARD_SLUGS.get(code)
            if not slug:
                continue
            self._current_slug = slug
            logger.info(f"[athome] fetching ward: {code} ({slug})")
            try:
                listings = await super().fetch_latest()
            except asyncio.CancelledError:
                logger.warning(
                    f"[athome] cancelled during {slug}, "
                    f"returning {len(all_listings)} partial listings"
                )
                return all_listings
            except Exception as e:
                logger.warning(f"[athome] {slug} failed: {e}, skipping")
                continue
            all_listings.extend(listings)
            logger.info(f"[athome] {slug}: {len(listings)} listings")
        return all_listings

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

        # Address + station access.
        # Current HTML uses dl.p-property__information-hint with EMPTY <dt>;
        # the <dd>s are positional/content-based: an address line (contains
        # 区/市 but no 駅), an access line (contains 駅 + 徒歩), and a building
        # type line. Detect by content rather than dt labels.
        address = ""
        ward = ""
        stations: list[dict] = []
        info_hints = el.select("dl.p-property__information-hint")
        for dl in info_hints:
            dd = dl.select_one("dd")
            if not dd:
                continue
            text = dd.get_text(" ", strip=True)
            if "駅" in text and "徒歩" in text:
                for m in re.finditer(
                    r"([^\s「」/／]+線)\s*[「『]?([^「」『』\s]+?)[」』]?\s*駅\s*徒歩\s*(\d+)\s*分",
                    text,
                ):
                    stations.append({
                        "line": m.group(1).strip(),
                        "station": m.group(2).strip(),
                        "walk_minutes": int(m.group(3)),
                    })
            elif not address and re.search(r"[都道府県]?\S*?[区市]\S", text):
                address = text
                m = re.search(r"(\S+?[区市])", text)
                if m:
                    ward = m.group(1)

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

            # Size — current HTML embeds it in the room box text (e.g. "43.50m²").
            box_text = box.get_text(" ", strip=True)
            m_s = re.search(r"([\d.]+)\s*(?:m²|m2|㎡|平米|平方メートル)", box_text)
            if m_s:
                try:
                    size = float(m_s.group(1))
                except ValueError:
                    size = None

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
