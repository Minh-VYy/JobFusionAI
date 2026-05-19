"""
=============================================
Geocoding Processor - Lớp 3: AI Agents Layer
Công cụ Admin: Chuyển đổi địa chỉ text → GPS
Sử dụng công thức Haversine để tính khoảng cách
=============================================
"""

import math
import re
import time
import requests
from typing import Optional, Tuple
from loguru import logger
import config


# ── Haversine Formula ─────────────────────────────────────────────────────────
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Tính khoảng cách chim bay giữa 2 điểm GPS bằng công thức Haversine.

    Args:
        lat1, lon1: Tọa độ điểm 1 (độ thập phân)
        lat2, lon2: Tọa độ điểm 2 (độ thập phân)

    Returns:
        float: Khoảng cách tính bằng km

    Công thức:
        a = sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlon/2)
        c = 2·atan2(√a, √(1−a))
        d = R·c  (R = 6371 km)
    """
    R = 6371.0  # Bán kính Trái Đất (km)

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def is_within_radius(
    job_lat: float, job_lng: float, user_lat: float, user_lng: float, radius_km: float
) -> Tuple[bool, float]:
    """
    Kiểm tra việc làm có trong bán kính tìm kiếm của người dùng không.

    Returns:
        Tuple[bool, float]: (trong_bán_kính, khoảng_cách_km)
    """
    dist = haversine_distance(user_lat, user_lng, job_lat, job_lng)
    return dist <= radius_km, round(dist, 2)


# ── Geocoding Engine ─────────────────────────────────────────────────────────
class GeocodingProcessor:
    """
    Bộ xử lý Geocoding đa tầng:
    1. Nominatim (OpenStreetMap) - Miễn phí
    2. Google Maps Geocoding API - Backup
    3. Regex-based fallback cho địa chỉ Việt Nam
    """

    # Bản đồ thủ công cho các quận/huyện tại Đà Nẵng
    DANANG_DISTRICTS = {
        "hải châu": (16.0679, 108.2208),
        "thanh khê": (16.0679, 108.1958),
        "sơn trà": (16.1000, 108.2394),
        "ngũ hành sơn": (15.9938, 108.2600),
        "cẩm lệ": (16.0231, 108.1889),
        "liên chiểu": (16.1056, 108.1608),
        "hòa vang": (16.0069, 108.1189),
        "trung tâm": (16.0544, 108.2022),
        "đà nẵng": (16.0544, 108.2022),
    }

    def __init__(self):
        self.session = requests.Session()
        # Nominatim requires proper User-Agent
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 AI-JobAgent/1.0 (+http://localhost:8000)"
            }
        )
        self._cache: dict = {}
        self._last_nominatim_call = 0  # Rate limiting tracker

    def _strip_building_info(self, address: str) -> str:
        """Loại bỏ tên tòa nhà, tầng, phòng để Nominatim dễ nhận biết đường phố hơn."""
        # Loại bỏ các cụm "Tầng X", "Lầu X", "Phòng Y", "Floor X", "Room Y" ở đầu hoặc giữa câu
        address = re.sub(r'(?i)\b(?:tầng|lầu|floor|room|phòng|p\.?)\s*\d+\b\s*(?:-\s*|\,\s*)?', '', address)
        address = re.sub(r'(?i)\b\d+\s*(?:st|nd|rd|th)\s*floor\s*(?:-\s*|\,\s*)?', '', address)
        
        # Loại bỏ các cụm "Tòa nhà X", "Building Y", "OfficeHaus", "OFH Building", "Tower"
        address = re.sub(r'(?i)\b(?:tòa nhà|building|officehaus|ofh building|tower)\s+[\w\s\d\-]+(?:,\s*|\s*)', '', address)
        
        # Làm sạch khoảng trống thừa hoặc dấu phẩy thừa ở đầu/cuối
        address = re.sub(r'^\s*,\s*|\s*,\s*$', '', address)
        return address.strip()

    def _extract_street_and_city(self, address: str) -> Optional[str]:
        """Tách lấy số nhà, tên đường và tên thành phố chính để tìm kiếm tối giản."""
        parts = [p.strip() for p in address.split(',') if p.strip()]
        if len(parts) < 2:
            return None
        
        # Thử lấy phần đầu tiên (số nhà/tên đường) và phần cuối cùng (thành phố)
        street = parts[0]
        city = parts[-1]
        
        # Nếu phần cuối cùng là "Việt Nam", lấy phần kề cuối làm thành phố
        if city.lower() in ["việt nam", "vietnam", "viet nam"] and len(parts) >= 3:
            city = parts[-2]
            
        return f"{street}, {city}, Việt Nam"

    def geocode(self, address: str) -> Optional[dict]:
        """
        Chuyển đổi địa chỉ text → tọa độ GPS.

        Returns:
            dict: {lat, lng, confidence, formatted_address}
        """
        if not address or len(address.strip()) < 3:
            return None

        address_normalized = self._normalize_address(address)

        # Kiểm tra cache
        if address_normalized in self._cache:
            return self._cache[address_normalized]

        result = None

        # Tầng 1: OpenCage (nếu có key) - NHANH NHẤT
        if hasattr(config, "OPENCAGE_API_KEY") and config.OPENCAGE_API_KEY:
            result = self._geocode_opencage(address_normalized)

        # Tầng 2: Nominatim (miễn phí, không cần key)
        if not result:
            result = self._geocode_nominatim(address_normalized)

        # Tầng 3: Google Maps (nếu có key)
        if not result and config.GOOGLE_MAPS_API_KEY:
            result = self._geocode_google(address_normalized)

        # Thử tầng 2.1: Loại bỏ tên tòa nhà/tầng và thử lại
        if not result or result.get("confidence", 0) <= 0.6:
            clean_addr = self._strip_building_info(address_normalized)
            if clean_addr != address_normalized:
                logger.info(f"[Geocoding] Progressive step 1 (strip building): '{address_normalized}' -> '{clean_addr}'")
                temp_res = self._geocode_nominatim(clean_addr)
                if temp_res and temp_res.get("confidence", 0) > (result.get("confidence", 0) if result else 0):
                    result = temp_res

        # Thử tầng 2.2: Tách lấy đường phố + thành phố tối giản và thử lại
        if not result or result.get("confidence", 0) <= 0.6:
            clean_addr = self._strip_building_info(address_normalized)
            simplified_addr = self._extract_street_and_city(clean_addr)
            if simplified_addr:
                logger.info(f"[Geocoding] Progressive step 2 (simplified): '{clean_addr}' -> '{simplified_addr}'")
                temp_res = self._geocode_nominatim(simplified_addr)
                if temp_res and temp_res.get("confidence", 0) > (result.get("confidence", 0) if result else 0):
                    result = temp_res

        # Tầng 4: Fallback thủ công theo quận Đà Nẵng
        if not result:
            result = self._geocode_fallback(address_normalized)

        # Nếu vẫn không có kết quả, thử tìm tên thành phố lớn để định vị tương đối
        if not result:
            cities = [
                "hồ chí minh",
                "ho chi minh",
                "sài gòn",
                "saigon",
                "hà nội",
                "ha noi",
                "đà nẵng",
                "da nang",
                "hải phòng",
                "hai phong",
                "cần thơ",
                "can tho",
            ]
            lower = address.lower()
            for city in cities:
                if city in lower:
                    try_addr = f"{city.title()}, Việt Nam"
                    logger.info(f"[Geocoding] Trying city fallback: {try_addr}")
                    if hasattr(config, "OPENCAGE_API_KEY") and config.OPENCAGE_API_KEY:
                        result = self._geocode_opencage(try_addr)
                    if not result:
                        result = self._geocode_nominatim(try_addr)
                    if result:
                        # Lower confidence because we only matched city
                        result["confidence"] = min(result.get("confidence", 0.5), 0.6)
                        break

            if not result:
                # Nếu không tìm thấy city hoặc không thành công, thử các đoạn chia theo dấu phẩy hoặc ':'
                parts = re.split(r"[,;:\n]+", address)
                # sắp xếp các phần theo độ dài (ưu tiên phần dài hơn)
                parts = [p.strip() for p in parts if len(p.strip()) > 3]
                parts = sorted(parts, key=lambda x: -len(x))
                for part in parts:
                    try_part = self._normalize_address(part)
                    logger.info(f"[Geocoding] Trying part fallback: {try_part}")
                    if hasattr(config, "OPENCAGE_API_KEY") and config.OPENCAGE_API_KEY:
                        result = self._geocode_opencage(try_part)
                    if not result:
                        result = self._geocode_nominatim(try_part)
                    if result:
                        result["confidence"] = min(result.get("confidence", 0.5), 0.5)
                        break

        if result:
            self._cache[address_normalized] = result

        return result

    def _translate_english_terms(self, address: str) -> str:
        """Dịch các từ tiếng Anh thông dụng sang tiếng Việt để công cụ định vị Nominatim nhận biết tốt hơn."""
        # HCM, HCMC, Ho Chi Minh City -> Hồ Chí Minh
        address = re.sub(r'(?i)\b(?:ho chi minh city|hcmc|hcm|saigon|sài gòn)\b', 'Hồ Chí Minh', address)
        # Hanoi, Ha Noi -> Hà Nội
        address = re.sub(r'(?i)\b(?:hanoi|ha noi)\b', 'Hà Nội', address)
        # Da Nang -> Đà Nẵng
        address = re.sub(r'(?i)\b(?:da nang|danang)\b', 'Đà Nẵng', address)
        
        # Street -> Đường
        address = re.sub(r'(?i)\b(?:street|str\.?)\b', 'Đường', address)
        # Ward -> Phường
        address = re.sub(r'(?i)\b(?:ward|w\.?)\b', 'Phường', address)
        # District -> Quận
        address = re.sub(r'(?i)\b(?:district|dist\.?|d\.?)\b', 'Quận', address)
        # Tower -> Tòa nhà
        address = re.sub(r'(?i)\b(?:tower)\b', 'Tòa nhà', address)
        
        return address.strip()

    def _normalize_address(self, address: str) -> str:
        """Chuẩn hóa địa chỉ tiếng Việt - dịch từ tiếng Anh và thêm quốc gia nếu thiếu."""
        if not address:
            return ""

        # 1. Loại bỏ các phần chú thích trong ngoặc đơn chứa chữ "cũ", "mới", "hành chính mới", hoặc tên quận/huyện cũ
        # Ví dụ: "Phường Tam Hiệp (Thành phố Biên Hòa cũ)" -> "Phường Tam Hiệp"
        address = re.sub(r'\s*\([^)]*\bcũ\b[^)]*\)', '', address, flags=re.IGNORECASE)
        address = re.sub(r'\s*\([^)]*\bmới\b[^)]*\)', '', address, flags=re.IGNORECASE)
        address = re.sub(r'\s*\([^)]*\bhành\s*chính[^)]*\)', '', address, flags=re.IGNORECASE)
        
        # 2. Loại bỏ các ngoặc đơn rỗng hoặc ngoặc đơn chứa thông tin phụ không cần thiết cho geocoding
        address = re.sub(r'\s*\([^)]*\)', '', address)
        
        # 3. Làm sạch dấu phẩy kép, dấu hai chấm thừa
        address = re.sub(r'\s*:\s*', ', ', address)
        address = re.sub(r',+', ',', address)
        address = re.sub(r'\s*,\s*', ', ', address)
        address = address.strip(" ,:")
        
        # 4. Dịch các cụm từ tiếng Anh sang tiếng Việt
        address = self._translate_english_terms(address)
        address = address.strip(" ,:")

        # 5. Nếu địa chỉ bắt đầu bằng Tỉnh/Thành phố dạng "Đồng Nai, 161/1 Trương Định", chuyển Tỉnh/Thành xuống cuối câu
        PROVINCES_PATTERN = r"(?i)^(Hồ Chí Minh|Hà Nội|Đà Nẵng|Bình Dương|Đồng Nai|Cần Thơ|Hải Phòng|Long An|Khánh Hòa|Quảng Nam|Thừa Thiên Huế|Bà Rịa\s*-\s*Vũng Tàu|Bà Rịa Vũng Tàu|Hải Dương|Bắc Ninh|Vĩnh Phúc|Quảng Ninh),\s*(.*)$"
        match = re.match(PROVINCES_PATTERN, address)
        if match:
            address = f"{match.group(2).strip()}, {match.group(1).strip()}"

        address_lower = address.lower()

        # Chỉ thêm ", Việt Nam" nếu chưa có tên thành phố lớn hoặc quốc gia
        VN_MARKERS = [
            "việt nam", "vietnam", "viet nam",
            "hà nội", "ha noi", "thành phố hà nội",
            "hồ chí minh", "ho chi minh", "tp.hcm",
            "đà nẵng", "da nang",
            "hải phòng", "hai phong",
            "cần thơ", "can tho",
            "bình dương", "binh duong",
            "đồng nai", "dong nai",
        ]
        has_location_context = any(marker in address_lower for marker in VN_MARKERS)
        if not has_location_context:
            address = f"{address}, Việt Nam"

        # Làm sạch lại lần cuối sau khi ghép quốc gia
        address = re.sub(r',+', ',', address)
        address = re.sub(r'\s*,\s*', ', ', address)
        return address.strip(" ,:")

    def _split_addresses(self, address: str) -> list[str]:
        """
        Tách tổ hợp address chứa nhiều địa chỉ.
        """
        if not address or len(address.strip()) < 5:
            return [address]

        # 1. Tách theo dấu gạch ngang dạng danh sách hoặc dòng mới: "- Hồ Chí Minh: ... - Hà Nội: ..."
        parts = []
        if " - " in address or "\n" in address or " – " in address:
            raw_parts = re.split(r'\s*(?:[\-\n•]| – )\s*', address)
            for p in raw_parts:
                p_clean = p.strip(" ,-:")
                if len(p_clean) > 8:
                    parts.append(p_clean)

        if parts:
            return parts

        # 2. Fallback tìm ranh giới thành phố cũ (nếu có dấu phẩy)
        CITY_BOUNDARY_PATTERN = re.compile(
            r"""(?ix)
            (?P<city_end>
                \b(?:
                    Hanoi|Hà\s*Nội|HAN|HNI|
                    HCM|Ho\s*Chi\s*Minh|Hồ\s*Chí\s*Minh|Saigon|Sài\s*Gòn|HCMC|TP\.?HCM|
                    Thu\s*Duc|Thủ\s*Đức|
                    Da\s*Nang|Đà\s*Nẵng|
                    Hai\s*Phong|Hải\s*Phòng|
                    Can\s*Tho|Cần\s*Thơ|
                    Binh\s*Duong|Bình\s*Dương|
                    Dong\s*Nai|Đồng\s*Nai
                )\b
            )
            ,\s*(?=[A-ZĐẠỮẨỤẦỐẢĂÂÊÔỰ\d])
            """,
        )

        split_points = []
        for m in CITY_BOUNDARY_PATTERN.finditer(address):
            split_points.append(m.end("city_end") + 1)

        if not split_points:
            return [address.strip()]

        parts = []
        prev = 0
        for sp in split_points:
            part = address[prev:sp].rstrip(", ")
            if part.strip():
                parts.append(part.strip())
            prev = sp
        last_part = address[prev:].strip().lstrip(", ")
        if last_part:
            parts.append(last_part)

        parts = [p for p in parts if len(p) > 8]
        return parts if parts else [address.strip()]

    def _geocode_nominatim(self, address: str) -> Optional[dict]:
        """Geocoding sử dụng Nominatim (OpenStreetMap)."""
        # Rate limit: respect Nominatim's 1 req/s policy
        elapsed = time.time() - self._last_nominatim_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)

        try:
            self._last_nominatim_call = time.time()
            resp = self.session.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": address,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "vn",
                    "accept-language": "vi",
                },
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            if data:
                item = data[0]
                return {
                    "lat": float(item["lat"]),
                    "lng": float(item["lon"]),
                    "confidence": min(float(item.get("importance", 0.5)), 1.0),
                    "formatted_address": item.get("display_name", address),
                    "source": "nominatim",
                }

        except Exception as e:
            logger.warning(f"[Geocoding] Nominatim error: {e}")

        return None

    def _geocode_opencage(self, address: str) -> Optional[dict]:
        """
        Geocoding sử dụng OpenCage API (Nhanh + Miễn phí).

        Để dùng, thêm vào config.py:
            OPENCAGE_API_KEY = "your_key_here"  # Lấy từ https://opencagedata.com

        Miễn phí: 2,500 requests/ngày
        """
        if not hasattr(config, "OPENCAGE_API_KEY") or not config.OPENCAGE_API_KEY:
            return None

        try:
            resp = self.session.get(
                "https://api.opencagedata.com/geocode/v1/json",
                params={
                    "q": address,
                    "key": config.OPENCAGE_API_KEY,
                    "language": "vi",
                    "countrycode": "vn",
                },
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("results"):
                loc = data["results"][0]
                geometry = loc["geometry"]
                return {
                    "lat": geometry["lat"],
                    "lng": geometry["lng"],
                    "confidence": min(loc.get("confidence", 7) / 10.0, 1.0),
                    "formatted_address": loc.get("formatted", address),
                    "source": "opencage",
                }

        except Exception as e:
            logger.warning(f"[Geocoding] OpenCage error: {e}")

        return None

    def _geocode_google(self, address: str) -> Optional[dict]:
        """Geocoding sử dụng Google Maps API."""
        if not hasattr(config, "GOOGLE_MAPS_API_KEY") or not config.GOOGLE_MAPS_API_KEY:
            return None

        try:
            resp = self.session.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "address": address,
                    "key": config.GOOGLE_MAPS_API_KEY,
                    "language": "vi",
                    "region": "vn",
                },
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "OK" and data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                return {
                    "lat": loc["lat"],
                    "lng": loc["lng"],
                    "confidence": 0.9,
                    "formatted_address": data["results"][0].get(
                        "formatted_address", address
                    ),
                    "source": "google",
                }

        except Exception as e:
            logger.warning(f"[Geocoding] Google Maps error: {e}")

        return None

    def _geocode_fallback(self, address: str) -> Optional[dict]:
        """
        Fallback: Ánh xạ thủ công dựa trên tên quận/huyện Đà Nẵng.
        Confidence thấp hơn vì chỉ trả về trung tâm quận.
        """
        address_lower = address.lower()

        for district, (lat, lng) in self.DANANG_DISTRICTS.items():
            if district in address_lower:
                logger.info(
                    f"[Geocoding] Fallback match: '{district}' → ({lat}, {lng})"
                )
                return {
                    "lat": lat,
                    "lng": lng,
                    "confidence": 0.3,  # Thấp - chỉ trung tâm quận
                    "formatted_address": f"{district.title()}, Đà Nẵng, Việt Nam",
                    "source": "fallback",
                }

        return None

    def batch_geocode(
        self, addresses: list[str], delay: float = 1.1
    ) -> list[Optional[dict]]:
        """
        Geocoding hàng loạt với rate limiting.

        Args:
            addresses: Danh sách địa chỉ
            delay:     Thời gian chờ giữa các request (giây)
        """
        results = []
        for i, addr in enumerate(addresses):
            result = self.geocode(addr)
            results.append(result)
            logger.info(
                f"[Geocoding] Batch {i + 1}/{len(addresses)}: {addr[:50]}... → {result}"
            )
            if i < len(addresses) - 1:
                time.sleep(delay)
        return results

    def extract_address_from_description(self, description: str) -> Optional[str]:
        """
        Reflection Agent Tool: Trích xuất địa chỉ từ mô tả công việc
        khi địa chỉ không được cung cấp trực tiếp.
        """
        patterns = [
            r"địa\s*chỉ[:\s]+([^\n\.]{10,100})",
            r"văn\s*phòng[:\s]+([^\n\.]{10,100})",
            r"địa\s*điểm[:\s]+([^\n\.]{10,100})",
            r"(?:đường|phố|quận|huyện|phường|xã)\s+[^\n\.]{5,100}",
            r"\d+\s+(?:đường|phố)\s+[^\n\.]{5,80}",
        ]

        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE | re.UNICODE)
            if match:
                return match.group(0).strip()

        return None

    def geocode_dataframe(self, df):
        """
        Geocode toàn bộ DataFrame - thêm cột latitude, longitude, geocoding_confidence.

        Xử lý địa chỉ kép (nhiều địa điểm trong 1 chuỗi):
        - Tách thành nhiều địa chỉ riêng biệt
        - Geocode từng địa chỉ, chọn kết quả có confidence cao nhất làm tọa độ chính
        - Schema DB chỉ có 1 cỗt lat/lng nên dùng địa chỉ đầu tiên hợp lệ

        Returns:
            df: DataFrame đã thêm cột lat/lng
        """
        import pandas as pd

        # Tìm cột địa chỉ
        address_col = None
        for col in ["location", "address_raw", "address"]:
            if col in df.columns:
                address_col = col
                break

        if not address_col:
            logger.warning(
                "[Geocoding] DataFrame không có cột địa chỉ (location/address_raw/address)"
            )
            return df

        logger.info(f"[Geocoding] Geocoding {len(df)} jobs từ cột '{address_col}'...")

        unique_locations = df[address_col].dropna().unique()
        logger.info(f"   → {len(unique_locations)} unique locations")

        # Geocode từng unique location (tránh gọi API nhiều lần)
        location_map = {}  # address_raw -> (lat, lng, confidence, all_locations)

        for loc in unique_locations:
            loc_str = str(loc).strip()
            if not loc_str or loc_str == "nan":
                location_map[loc_str] = (None, None, 0.0, [])
                continue

            # Bước 1: Tách địa chỉ kép thành nhiều địa chỉ riêng
            sub_addresses = self._split_addresses(loc_str)

            if len(sub_addresses) > 1:
                logger.info(
                    f"[Geocoding] Phát hiện {len(sub_addresses)} địa chỉ trong 1 ô:"
                )
                for i, sa in enumerate(sub_addresses):
                    logger.info(f"   [{i+1}] {sa[:80]}")

            # Bước 2: Geocode từng sub-address, chọn kết quả tốt nhất
            best_result = None
            all_locations = []
            
            for sub_addr in sub_addresses:
                result = self.geocode(sub_addr)
                if result:
                    all_locations.append({
                        "address": sub_addr,
                        "lat": result.get("lat"),
                        "lng": result.get("lng"),
                        "confidence": result.get("confidence", 0.0)
                    })
                    
                    # Chọn kết quả có confidence cao nhất
                    if best_result is None or result.get("confidence", 0) > best_result.get("confidence", 0):
                        best_result = result
                        logger.info(
                            f"   [Geocoding] Sub-result: {sub_addr[:50]} "
                            f"→ ({result['lat']:.4f}, {result['lng']:.4f}) "
                            f"conf={result.get('confidence', 0):.2f}"
                        )

            if best_result:
                location_map[loc_str] = (
                    best_result.get("lat"),
                    best_result.get("lng"),
                    best_result.get("confidence", 0.0),
                    all_locations
                )
            else:
                location_map[loc_str] = (None, None, 0.0, [])
                logger.warning(f"[Geocoding] Không geocode được: {loc_str[:60]}")

        # Map vào DataFrame
        df = df.copy()
        df["latitude"] = df[address_col].map(
            lambda x: location_map.get(str(x).strip(), (None, None, 0.0, []))[0]
        )
        df["longitude"] = df[address_col].map(
            lambda x: location_map.get(str(x).strip(), (None, None, 0.0, []))[1]
        )
        df["geocoding_confidence"] = df[address_col].map(
            lambda x: location_map.get(str(x).strip(), (None, None, 0.0, []))[2]
        )
        df["all_locations"] = df[address_col].map(
            lambda x: location_map.get(str(x).strip(), (None, None, 0.0, []))[3]
        )

        # Thống kê
        geocoded = df["latitude"].notna().sum()
        high_conf = (df["geocoding_confidence"] >= 0.7).sum()
        failed = df["latitude"].isna().sum()
        logger.info(f"   Geocoded: {geocoded}/{len(df)} | Confidence>=0.7: {high_conf} | Thất bại: {failed}")

        return df


# ── Singleton Instance ────────────────────────────────────────────────────────
geocoder = GeocodingProcessor()
