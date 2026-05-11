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
    dlat     = math.radians(lat2 - lat1)
    dlon     = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def is_within_radius(
    job_lat: float, job_lng: float,
    user_lat: float, user_lng: float,
    radius_km: float
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
        "hải châu":     (16.0679, 108.2208),
        "thanh khê":    (16.0679, 108.1958),
        "sơn trà":      (16.1000, 108.2394),
        "ngũ hành sơn": (15.9938, 108.2600),
        "cẩm lệ":       (16.0231, 108.1889),
        "liên chiểu":   (16.1056, 108.1608),
        "hòa vang":     (16.0069, 108.1189),
        "trung tâm":    (16.0544, 108.2022),
        "đà nẵng":      (16.0544, 108.2022),
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "JobAgentBot/1.0 (contact@example.com)"
        })
        self._cache: dict = {}

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

        # Tầng 1: Nominatim
        result = self._geocode_nominatim(address_normalized)

        # Tầng 2: Google Maps (nếu có key)
        if not result and config.GOOGLE_MAPS_API_KEY:
            result = self._geocode_google(address_normalized)

        # Tầng 3: Fallback thủ công theo quận Đà Nẵng
        if not result:
            result = self._geocode_fallback(address_normalized)

        if result:
            self._cache[address_normalized] = result

        return result

    def _normalize_address(self, address: str) -> str:
        """Chuẩn hóa địa chỉ tiếng Việt."""
        address = address.strip()
        # Thêm ", Đà Nẵng, Việt Nam" nếu chưa có
        if "đà nẵng" not in address.lower() and "da nang" not in address.lower():
            address = f"{address}, Đà Nẵng, Việt Nam"
        return address

    def _geocode_nominatim(self, address: str) -> Optional[dict]:
        """Geocoding sử dụng Nominatim (OpenStreetMap)."""
        try:
            resp = self.session.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q":              address,
                    "format":         "json",
                    "limit":          1,
                    "countrycodes":   "vn",
                    "accept-language":"vi",
                },
                timeout=config.REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            if data:
                item = data[0]
                return {
                    "lat":               float(item["lat"]),
                    "lng":               float(item["lon"]),
                    "confidence":        min(float(item.get("importance", 0.5)), 1.0),
                    "formatted_address": item.get("display_name", address),
                    "source":            "nominatim",
                }

            time.sleep(1)  # Rate limit Nominatim: 1 req/s

        except Exception as e:
            logger.warning(f"[Geocoding] Nominatim error: {e}")

        return None

    def _geocode_google(self, address: str) -> Optional[dict]:
        """Geocoding sử dụng Google Maps API."""
        try:
            resp = self.session.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "address": address,
                    "key":     config.GOOGLE_MAPS_API_KEY,
                    "language":"vi",
                    "region":  "vn",
                },
                timeout=config.REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "OK" and data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                return {
                    "lat":               loc["lat"],
                    "lng":               loc["lng"],
                    "confidence":        0.9,
                    "formatted_address": data["results"][0].get("formatted_address", address),
                    "source":            "google",
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
                logger.info(f"[Geocoding] Fallback match: '{district}' → ({lat}, {lng})")
                return {
                    "lat":               lat,
                    "lng":               lng,
                    "confidence":        0.3,  # Thấp - chỉ trung tâm quận
                    "formatted_address": f"{district.title()}, Đà Nẵng, Việt Nam",
                    "source":            "fallback",
                }

        return None

    def batch_geocode(self, addresses: list[str], delay: float = 1.1) -> list[Optional[dict]]:
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
            logger.info(f"[Geocoding] Batch {i+1}/{len(addresses)}: {addr[:50]}... → {result}")
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


# ── Singleton Instance ────────────────────────────────────────────────────────
geocoder = GeocodingProcessor()
