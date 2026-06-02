"""いい部屋ネット rental property scraper (eheya.net) — via __NEXT_DATA__ JSON."""

from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

EHEYA_WARD_CODES: dict[str, str] = {
    "千代田区": "13101", "中央区": "13102", "港区": "13103",
    "新宿区": "13104", "文京区": "13105", "台東区": "13106",
    "墨田区": "13107", "江東区": "13108", "品川区": "13109",
    "目黒区": "13110", "大田区": "13111", "世田谷区": "13112",
    "渋谷区": "13113", "中野区": "13114", "杉並区": "13115",
    "豊島区": "13116", "北区": "13117", "荒川区": "13118",
    "板橋区": "13119", "練馬区": "13120", "足立区": "13121",
    "葛飾区": "13122", "江戸川区": "13123",
}


class EheyaScraper(BaseScraper):
    """Scraper for いい部屋ネット — parses __NEXT_DATA__ JSON."""

    name = "eheya"
    base_url = "https://www.eheya.net"
    rate_limit = 2.0
    max_pages = 5

    def __init__(self, ward_codes: list[str] | None = None) -> None:
        super().__init__()
        self.ward_codes = ward_codes or list(EHEYA_WARD_CODES.values())
        self._current_ward_code = self.ward_codes[0] if self.ward_codes else "13113"

    def build_url(self, page: int) -> str:
        code = self._current_ward_code
        offset = (page - 1) * 20
        # Best-effort rent filter via the SPA's URL state. Even if eheya's
        # frontend ignores it, client-side rent cap in orchestrator keeps us safe.
        filters = "detail.priceMax=YEN_200000"
        if page == 1:
            return f"{self.base_url}/tokyo/area/{code}/search/?{filters}"
        return f"{self.base_url}/tokyo/area/{code}/search/?{filters}&offset={offset}"

    async def fetch_latest(self) -> list[dict]:
        all_listings: list[dict] = []
        for code in self.ward_codes:
            self._current_ward_code = code
            ward_name = next((k for k, v in EHEYA_WARD_CODES.items() if v == code), code)
            logger.info(f"[{self.name}] fetching ward: {ward_name} ({code})")
            listings = await super().fetch_latest()
            all_listings.extend(listings)
            logger.info(f"[{self.name}] {ward_name}: {len(listings)} listings")
        return all_listings

    def parse_total_count(self, html: str) -> int | None:
        soup = BeautifulSoup(html, "html.parser")
        script = soup.select_one("script#__NEXT_DATA__")
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None
        bsr = data.get("props", {}).get("pageProps", {}).get("buildingSearchResult", {})
        total = bsr.get("total") or bsr.get("totalCount") or bsr.get("count")
        if isinstance(total, int) and total > 0:
            return total
        return None

    def parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        script = soup.select_one("script#__NEXT_DATA__")
        if not script or not script.string:
            return []

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return []

        bsr = data.get("props", {}).get("pageProps", {}).get("buildingSearchResult", {})
        buildings = bsr.get("buildings", [])
        results: list[dict] = []

        for b in buildings:
            name = b.get("name", "")
            address = b.get("address", "")
            ward = ""
            m_w = re.search(r"(?:東京都)?(.+?区)", address)
            if m_w:
                ward = m_w.group(1)

            age_years = None
            age_text = b.get("age", "")
            m_age = re.search(r"築(\d+)年", age_text)
            if m_age:
                age_years = int(m_age.group(1))
            elif "新築" in age_text:
                age_years = 0

            total_floors = b.get("story")

            # Station from mainTransportationText: "東急東横線 代官山駅 徒歩4分"
            station_text = b.get("mainTransportationText", "")
            nearest_station = ""
            walk_minutes = None
            line = ""
            m_st = re.match(r"(.+?線?)\s+(.+?駅)\s+徒歩(\d+)分", station_text)
            if m_st:
                line = m_st.group(1)
                nearest_station = m_st.group(2)
                walk_minutes = int(m_st.group(3))

            # Building exterior image
            building_image = ""
            ext_img = b.get("exteriorImage")
            if ext_img and isinstance(ext_img, dict):
                building_image = ext_img.get("url", "")

            for p in b.get("properties", []):
                prop_id = p.get("propertyFullId", "")
                if not prop_id:
                    continue
                prop_id = f"eheya_{prop_id[:20]}"

                price = p.get("price", {})
                rent = price.get("number", 0) if isinstance(price, dict) else 0
                if not rent:
                    continue

                manage = p.get("manageCost", {})
                admin_fee = manage.get("number", 0) if isinstance(manage, dict) else 0

                dep = p.get("securityDeposit", {})
                deposit = int(dep.get("number", 0)) if isinstance(dep, dict) and dep.get("number") else None

                km = p.get("keyMoney", {})
                key_money = int(km.get("number", 0)) if isinstance(km, dict) and km.get("number") else None

                layout = p.get("housePlan", "")
                size = p.get("roomArea")

                floor = None
                floor_text = p.get("floor", "")
                m_f = re.search(r"(\d+)", floor_text)
                if m_f:
                    floor = int(m_f.group(1))

                # Property image
                image_url = building_image
                plan_img = p.get("housePlanImage")
                if plan_img and isinstance(plan_img, dict):
                    image_url = plan_img.get("url", "") or image_url
                ext = p.get("exteriorImage")
                if ext and isinstance(ext, dict) and ext.get("url"):
                    image_url = ext["url"]

                features = []
                if p.get("isPet") or p.get("isPetFriendly"):
                    features.append("ペット可")
                if p.get("isFreeInternet"):
                    features.append("ネット無料")

                results.append({
                    "id": prop_id,
                    "source": "eheya",
                    "source_url": f"{self.base_url}/property/{p.get('propertyFullId', '')}/",
                    "name": p.get("buildingName") or name,
                    "rent": rent,
                    "management_fee": admin_fee,
                    "deposit": deposit,
                    "key_money": key_money,
                    "layout": layout,
                    "size_sqm": size,
                    "floor": floor,
                    "total_floors": total_floors,
                    "building_age_years": age_years,
                    "structure": "",
                    "address": p.get("address") or address,
                    "ward": ward,
                    "nearest_station": nearest_station,
                    "walk_minutes": walk_minutes,
                    "line": line,
                    "image_url": image_url,
                    "features": features,
                    "pet_allowed": p.get("isPet") or p.get("isPetFriendly") or None,
                })

        return results
