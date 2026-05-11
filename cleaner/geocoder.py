# cleaner/geocoder.py
import time
import logging
import re
# pyrefly: ignore [missing-import]
from geopy.geocoders import Nominatim
# pyrefly: ignore [missing-import]
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)

# ================================================================
# BẢNG TỌA ĐỘ TĨNH — Các thành phố phổ biến Việt Nam
# Nhanh + không cần gọi API
# ================================================================
VIETNAM_COORDINATES = {
    # Thành phố lớn
    "hà nội":           (21.0285, 105.8542),
    "tp. hồ chí minh":  (10.8231, 106.6297),
    "hồ chí minh":      (10.8231, 106.6297),
    "tp hồ chí minh":   (10.8231, 106.6297),
    "ho chi minh":      (10.8231, 106.6297),
    "đà nẵng":          (16.0544, 108.2022),
    "da nang":          (16.0544, 108.2022),
    "cần thơ":          (10.0452, 105.7469),
    "hải phòng":        (20.8449, 106.6881),

    # Tỉnh/thành phổ biến
    "bình dương":       (10.9804, 106.6519),
    "đồng nai":         (10.9457, 106.8243),
    "bà rịa vũng tàu":  (10.5417, 107.2429),
    "vũng tàu":         (10.3460, 107.0843),
    "long an":          (10.5360, 106.4075),
    "tiền giang":       (10.3600, 106.3600),
    "bắc ninh":         (21.1214, 106.1109),
    "hưng yên":         (20.6464, 106.0511),
    "hải dương":        (20.9373, 106.3147),
    "thái nguyên":      (21.5942, 105.8412),
    "nghệ an":          (18.6797, 105.6813),
    "thanh hóa":        (19.8077, 105.7764),
    "huế":              (16.4637, 107.5909),
    "quảng nam":        (15.5394, 108.0191),
    "quảng ngãi":       (15.1214, 108.8040),
    "bình định":        (13.7820, 109.2196),
    "khánh hòa":        (12.2388, 109.1967),
    "nha trang":        (12.2388, 109.1967),
    "lâm đồng":         (11.5753, 108.1429),
    "đà lạt":           (11.9465, 108.4419),
    "bình thuận":       (11.0904, 108.0721),
    "đắk lắk":          (12.6680, 108.0378),
    "gia lai":          (13.9833, 108.0000),
    "kon tum":          (14.3545, 107.9972),
    "quảng bình":       (17.4667, 106.6222),
    "quảng trị":        (16.7500, 107.1833),
    "hà tĩnh":          (18.3559, 105.8877),

    # Remote / Toàn quốc
    "remote":           (16.0000, 106.0000),  # Trung tâm VN
    "toàn quốc":        (16.0000, 106.0000),
    "không xác định":   (16.0000, 106.0000),
}


class Geocoder:
    """
    Chuyển đổi địa chỉ text → tọa độ GPS (lat, lng).
    Ưu tiên: Lookup tĩnh → Nominatim API → Default VN
    """

    def __init__(self, use_api: bool = True):
        self.use_api = use_api
        self.geolocator = Nominatim(
            user_agent="job_crawler_vnm_v1",
            timeout=5
        )
        self._api_cache = {}   # Cache kết quả API
        self._api_calls = 0    # Đếm số lần gọi API

    # ============================================================
    # ENTRY POINT
    # ============================================================

    def geocode(self, location: str) -> tuple[float, float, float]:
        """
        Trả về (latitude, longitude, confidence)
        confidence: 1.0 = lookup tĩnh, 0.8 = API, 0.0 = default
        """
        if not location or str(location).strip() in ["", "nan", "None"]:
            return 16.0, 106.0, 0.0

        location_clean = self._normalize(location)

        # Bước 1: Lookup bảng tĩnh
        result = self._static_lookup(location_clean)
        if result:
            lat, lng = result
            logger.debug(f"📍 Static: '{location}' → ({lat}, {lng})")
            return lat, lng, 1.0

        # Bước 2: Nominatim API
        if self.use_api:
            result = self._api_geocode(location_clean)
            if result:
                lat, lng = result
                logger.debug(f"🌐 API: '{location}' → ({lat}, {lng})")
                return lat, lng, 0.8

        # Bước 3: Default — trung tâm Việt Nam
        logger.debug(f"⚠️  Không geocode được: '{location}' → default VN")
        return 16.0, 106.0, 0.0

    # ============================================================
    # BƯỚC 1: STATIC LOOKUP
    # ============================================================

    def _static_lookup(self, location: str) -> tuple | None:
        """Tìm trong bảng tĩnh — exact match hoặc partial match"""
        loc_lower = location.lower().strip()

        # Exact match
        if loc_lower in VIETNAM_COORDINATES:
            return VIETNAM_COORDINATES[loc_lower]

        # Partial match — tìm key nào nằm trong location
        for key, coords in VIETNAM_COORDINATES.items():
            if key in loc_lower or loc_lower in key:
                return coords

        return None

    # ============================================================
    # BƯỚC 2: NOMINATIM API
    # ============================================================

    def _api_geocode(self, location: str) -> tuple | None:
        """Gọi Nominatim API (OpenStreetMap, miễn phí)"""
        # Kiểm tra cache
        if location in self._api_cache:
            return self._api_cache[location]

        # Rate limit: 1 request/giây (Nominatim policy)
        time.sleep(1.1)

        try:
            query = f"{location}, Vietnam"
            self._api_calls += 1
            result = self.geolocator.geocode(query)

            if result:
                coords = (result.latitude, result.longitude)
                self._api_cache[location] = coords
                return coords

        except GeocoderTimedOut:
            logger.warning(f"⏱️  Timeout geocoding: {location}")
        except GeocoderServiceError as e:
            logger.error(f"❌ Geocoder API error: {e}")
        except Exception as e:
            logger.error(f"❌ Geocoder error: {e}")

        self._api_cache[location] = None
        return None

    # ============================================================
    # NORMALIZE
    # ============================================================

    def _normalize(self, location: str) -> str:
        """Chuẩn hóa location text trước khi lookup"""
        s = str(location).strip().lower()

        # Xóa "(mới)", "(new)"
        s = re.sub(r'\s*\(mới\)', '', s)
        s = re.sub(r'\s*\(new\)', '', s, flags=re.IGNORECASE)

        # Chuẩn hóa tên thành phố
        replacements = {
            "tp. hồ chí minh": "hồ chí minh",
            "tp.hcm": "hồ chí minh",
            "tphcm": "hồ chí minh",
            "hcm": "hồ chí minh",
            "ha noi": "hà nội",
            "ho chi minh city": "hồ chí minh",
            "da nang": "đà nẵng",
        }
        for old, new in replacements.items():
            s = s.replace(old, new)

        return s.strip()

    # ============================================================
    # BATCH PROCESSING
    # ============================================================

    def geocode_dataframe(self, df):
        """Geocode toàn bộ DataFrame — thêm cột lat/lng"""
        import pandas as pd

        logger.info(f"🗺️  Geocoding {len(df)} jobs...")

        unique_locations = df["location"].dropna().unique()
        logger.info(f"   → {len(unique_locations)} unique locations")

        # Geocode từng unique location (tránh gọi API nhiều lần)
        location_map = {}
        for loc in unique_locations:
            lat, lng, conf = self.geocode(str(loc))
            location_map[str(loc)] = (lat, lng, conf)

        # Map vào DataFrame
        df = df.copy()
        df["latitude"]             = df["location"].map(
            lambda x: location_map.get(str(x), (16.0, 106.0, 0.0))[0]
        )
        df["longitude"]            = df["location"].map(
            lambda x: location_map.get(str(x), (16.0, 106.0, 0.0))[1]
        )
        df["geocoding_confidence"] = df["location"].map(
            lambda x: location_map.get(str(x), (16.0, 106.0, 0.0))[2]
        )

        # Thống kê
        high_conf = (df["geocoding_confidence"] >= 0.8).sum()
        low_conf  = (df["geocoding_confidence"] == 0.0).sum()
        logger.info(f"   ✅ Geocoded chính xác: {high_conf}/{len(df)}")
        logger.info(f"   ⚠️  Dùng default:       {low_conf}/{len(df)}")
        logger.info(f"   🌐 API calls:           {self._api_calls}")

        return df