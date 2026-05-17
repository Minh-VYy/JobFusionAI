# cleaner/cross_source_detector.py
"""
Cross-Source Duplicate Detection System
Phát hiện job trùng lặp giữa nhiều nguồn: Facebook, TopCV, ITviec, VietnamWorks
"""
import re
import unicodedata
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

logger = logging.getLogger(__name__)

# ================================================================
# WEIGHTS — Tổng = 1.0
# ================================================================
SCORE_WEIGHTS = {
    "phone":    0.40,
    "location": 0.20,
    "salary":   0.15,
    "title":    0.15,
    "company":  0.10,
}

DUPLICATE_THRESHOLD = 0.85   # Score > 0.85 → coi là duplicate

# Map từ đồng nghĩa cho location
LOCATION_ALIASES: Dict[str, str] = {
    "hc": "hải châu", "hai chau": "hải châu",
    "tq": "thanh khê", "thanh khe": "thanh khê",
    "son tra": "sơn trà", "ngu hanh son": "ngũ hành sơn",
    "da nang": "đà nẵng", "dn": "đà nẵng",
    "hanoi": "hà nội", "ha noi": "hà nội", "hn": "hà nội",
    "hcm": "hồ chí minh", "ho chi minh": "hồ chí minh", "tphcm": "hồ chí minh",
    "binh duong": "bình dương", "dong nai": "đồng nai",
}

# ================================================================
# DATACLASS — Features đã normalize
# ================================================================
@dataclass
class JobFeatures:
    job_id:         str = ""
    source:         str = ""   # facebook / topcv / itviec / vietnamworks

    # Raw
    raw_title:      str = ""
    raw_company:    str = ""
    raw_location:   str = ""
    raw_salary:     str = ""
    raw_phone:      str = ""
    raw_description:str = ""

    # Normalized (dùng để so sánh)
    norm_title:     str = ""
    norm_company:   str = ""
    norm_location:  str = ""
    salary_min:     float = 0.0
    salary_max:     float = 0.0
    phones:         List[str] = field(default_factory=list)   # list vì có thể nhiều SĐT
    skills:         List[str] = field(default_factory=list)
    fingerprint:    str = ""


# ================================================================
# NORMALIZER
# ================================================================
class JobNormalizer:
    """Normalize mọi field về dạng chuẩn để so sánh."""

    # ── Text ──────────────────────────────────────────────────────
    def normalize_text(self, text: str) -> str:
        """Lowercase, remove emoji/bold unicode, strip special chars."""
        if not text:
            return ""
        text = self._remove_emoji(text)
        text = self._flatten_unicode(text)
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _remove_emoji(self, text: str) -> str:
        return re.sub(
            r"[\U00010000-\U0010ffff\U0001F600-\U0001F64F"
            r"\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            r"\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]+",
            " ", text, flags=re.UNICODE
        )

    def _flatten_unicode(self, text: str) -> str:
        """Bold / italic Facebook → ASCII."""
        result = []
        for ch in text:
            n = unicodedata.normalize("NFKD", ch)
            a = n.encode("ascii", "ignore").decode("ascii")
            result.append(a if a else ch)
        return "".join(result)

    # ── Title ─────────────────────────────────────────────────────
    def normalize_title(self, title: str) -> str:
        """Xóa 'tuyển gấp', 'cần tuyển' noise → extract core role."""
        text = self.normalize_text(title)
        # Xóa các prefix tuyển dụng phổ biến
        noise = [
            r"tuyen gap\b", r"can tuyen\b", r"tuyen dung\b", r"can nguoi\b",
            r"hot\b", r"gap\b", r"urgent\b",
        ]
        for n in noise:
            text = re.sub(n, "", text)
        return re.sub(r"\s+", " ", text).strip()

    # ── Phone ─────────────────────────────────────────────────────
    def extract_phones(self, text: str) -> List[str]:
        """Extract tất cả SĐT và chuẩn hóa về 10 số."""
        clean = re.sub(r"[\s\-\.]", "", text)
        raw = re.findall(r"(?:0|\+84)\d{9}", clean)
        phones = []
        for p in raw:
            if p.startswith("+84"):
                p = "0" + p[3:]
            phones.append(p)
        return list(set(phones))

    # ── Salary ────────────────────────────────────────────────────
    def normalize_salary(self, salary_str: str) -> Tuple[float, float]:
        """
        Parse salary → (min_million_vnd, max_million_vnd).
        Hỗ trợ: 4tr5, 4.5tr, 4-7tr, 20k/h, 8.000.000, 4 triệu, Thỏa thuận
        """
        if not salary_str or salary_str.lower().strip() in ("thỏa thuận", "thoả thuận", "negotiate", ""):
            return 0.0, 0.0

        text = salary_str.lower().strip()
        text = self._flatten_unicode(text)
        # Chuẩn hóa: 4tr5 → 4.5tr
        text = re.sub(r'(\d+)tr(\d)\b', lambda m: f"{m.group(1)}.{m.group(2)}tr", text)
        # Xóa dấu phẩy ngăn cách (4,5tr → 4.5tr)
        text = text.replace(",", ".")

        def to_million(val: float) -> float:
            """Chuyển về đơn vị triệu: nếu > 500 thì đang là VNĐ"""
            if val > 500:
                return round(val / 1_000_000, 2)
            return round(val, 2)

        # Case 1: k/h, k/giờ, khoảng k/h (VD: 20-25k/h, 20k/h)
        # Giữ nguyên giá trị thực (triệu VNĐ), VD: 20k -> 0.02, để phân biệt với 20tr (20.0)
        m_range = re.search(r'(\d+(?:\.\d+)?)\s*(?:k)?\s*[-–~đến]+\s*(\d+(?:\.\d+)?)\s*k\s*(?:/|\s+)?(?:h|gio|hour|gi|ca)', text)
        if m_range:
            lo = float(m_range.group(1)) / 1000.0
            hi = float(m_range.group(2)) / 1000.0
            return round(lo, 3), round(hi, 3)

        m_single = re.search(r'(\d+(?:\.\d+)?)\s*k\s*(?:/|\s+)?(?:h|gio|hour|gi|ca)', text)
        if m_single:
            rate_k = float(m_single.group(1)) / 1000.0
            return round(rate_k, 3), round(rate_k, 3)

        # Case 2: khoảng "5tr - 7tr" / "5~7tr" / "5 đến 7 triệu"
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:tr|trieu|triệu|m|million)?'
            r'\s*[-–~đến]+\s*'
            r'(\d+(?:\.\d+)?)\s*(?:tr|trieu|triệu|m|million)?',
            text
        )
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            # Nếu giá trị lớn (VNĐ dạng 3.355.000 → đã replace dấu . thành số)
            lo, hi = to_million(lo), to_million(hi)
            if lo > 0 and hi >= lo:
                return lo, hi

        # Case 3: VNĐ dạng "8.000.000" (3+ chữ số sau dấu chấm)
        m = re.search(r'(\d{1,3}(?:\.\d{3})+)', text)
        if m:
            raw = float(m.group(1).replace(".", ""))
            v = to_million(raw)
            if v > 0:
                return v, v

        # Case 4: đơn lẻ "7tr" / "7.5tr" / "7 triệu"
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:tr|trieu|triệu|m|million)\b', text)
        if m:
            v = to_million(float(m.group(1)))
            if v > 0:
                return v, v

        # Case 5: khoảng k "20k - 30k" (đơn vị nghìn)
        m = re.search(r'(\d+)\s*k\s*[-–~đến]+\s*(\d+)\s*k', text)
        if m:
            lo_k, hi_k = float(m.group(1)), float(m.group(2))
            return round(lo_k / 1000.0, 3), round(hi_k / 1000.0, 3)

        # Case 6: đơn k "20k"
        m = re.search(r'(\d+)\s*k\b', text)
        if m:
            val = float(m.group(1))
            return round(val / 1000.0, 3), round(val / 1000.0, 3)

        return 0.0, 0.0

    # ── Location ──────────────────────────────────────────────────
    def normalize_location(self, loc: str) -> str:
        text = self.normalize_text(loc)
        for alias, canonical in LOCATION_ALIASES.items():
            if alias in text:
                return canonical
        return text

    # ── Fingerprint ───────────────────────────────────────────────
    def make_fingerprint(self, features: "JobFeatures") -> str:
        """Hash chính xác của các field normalized."""
        parts = [
            features.norm_title,
            features.norm_location,
            ",".join(sorted(features.phones)),
            f"{features.salary_min:.1f}-{features.salary_max:.1f}",
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


# ================================================================
# CROSS-SOURCE DETECTOR
# ================================================================
class CrossSourceDetector:
    """
    Phát hiện duplicate giữa nhiều nguồn.
    Dùng 3 layer:
      L1 — Exact match (phone, url, external_id)
      L2 — Feature similarity (location, salary, company, title)
      L3 — NLP cosine (TF-IDF trên title+description)
    """

    def __init__(self, threshold: float = DUPLICATE_THRESHOLD):
        self.threshold  = threshold
        self.normalizer = JobNormalizer()
        self.vectorizer = TfidfVectorizer(max_features=3000, ngram_range=(1, 2), min_df=1)

        # Index nhanh để tránh O(n²)
        self._phone_index:  Dict[str, List[str]] = {}   # phone → [job_id]
        self._loc_index:    Dict[str, List[str]] = {}   # location → [job_id]
        self._feature_store: Dict[str, JobFeatures] = {}  # job_id → features
        self._corpus:        List[str] = []              # TF-IDF corpus

    # ── Public API ────────────────────────────────────────────────

    def extract_features(self, job: Dict) -> JobFeatures:
        """Chuyển dict job → JobFeatures đã normalize."""
        n = self.normalizer
        f = JobFeatures(
            job_id   = job.get("job_id", job.get("external_id", "")),
            source   = job.get("source", ""),
            raw_title       = job.get("title", ""),
            raw_company     = job.get("company", ""),
            raw_location    = job.get("location", ""),
            raw_salary      = job.get("salary", ""),
            raw_phone       = job.get("phone", ""),
            raw_description = job.get("description", ""),
        )
        f.norm_title    = n.normalize_title(f.raw_title)
        f.norm_company  = n.normalize_text(f.raw_company)
        f.norm_location = n.normalize_location(f.raw_location)
        f.salary_min, f.salary_max = n.normalize_salary(f.raw_salary)
        f.phones  = n.extract_phones(f.raw_phone + " " + f.raw_description)
        f.fingerprint = n.make_fingerprint(f)
        return f

    def is_duplicate(self, new_job: Dict) -> Tuple[bool, float, str]:
        """
        Main API: kiểm tra job mới có trùng với job đã lưu không.

        Returns:
            (is_dup: bool, score: float, matched_job_id: str)
        """
        features = self.extract_features(new_job)

        # ── Layer 1: Exact match ──────────────────────────────────
        for phone in features.phones:
            if phone in self._phone_index:
                for existing_id in self._phone_index[phone]:
                    if existing_id != features.job_id:
                        logger.debug(f"[L1] Phone exact match: {phone} → {existing_id}")
                        return True, 1.0, existing_id

        if features.fingerprint:
            for jid, f in self._feature_store.items():
                if f.fingerprint == features.fingerprint and jid != features.job_id:
                    logger.debug(f"[L1] Fingerprint match → {jid}")
                    return True, 1.0, jid

        # ── Layer 2+3: Candidate filtering + scoring ──────────────
        candidates = self._get_candidates(features)
        best_score = 0.0
        best_id    = ""

        for cid in candidates:
            if cid == features.job_id:
                continue
            existing = self._feature_store[cid]
            score = self._compute_score(features, existing)
            if score > best_score:
                best_score = score
                best_id = cid

        if best_score >= self.threshold:
            logger.debug(f"[L2/3] Score={best_score:.2f} → duplicate {best_id}")
            return True, round(best_score, 3), best_id

        # Không trùng → thêm vào store
        self._register(features)
        return False, round(best_score, 3), ""

    def load_from_db(self, jobs: List[Dict]):
        """Load các job đã có trong DB để làm baseline so sánh."""
        for job in jobs:
            f = self.extract_features(job)
            self._register(f)
        logger.info(f"[CrossSourceDetector] Loaded {len(jobs)} jobs from DB")

    # ── Internal ──────────────────────────────────────────────────

    def _register(self, f: JobFeatures):
        """Thêm job vào các index."""
        self._feature_store[f.job_id] = f
        for phone in f.phones:
            self._phone_index.setdefault(phone, []).append(f.job_id)
        self._loc_index.setdefault(f.norm_location, []).append(f.job_id)

    def _get_candidates(self, f: JobFeatures) -> List[str]:
        """
        Lấy candidates từ location index để tránh O(n²).
        Chỉ so sánh với job cùng khu vực.
        """
        candidates = set()
        loc = f.norm_location

        # Cùng location
        if loc in self._loc_index:
            candidates.update(self._loc_index[loc])

        # Location chứa nhau (ví dụ: "hải châu" ⊂ "đà nẵng")
        for stored_loc, ids in self._loc_index.items():
            if loc and stored_loc and (loc in stored_loc or stored_loc in loc):
                candidates.update(ids)

        # Nếu không đủ candidates → fallback toàn bộ (nhưng giới hạn 200)
        if len(candidates) < 5:
            all_ids = list(self._feature_store.keys())
            candidates.update(all_ids[-200:])

        return list(candidates)

    def _compute_score(self, a: JobFeatures, b: JobFeatures) -> float:
        """
        Tính weighted similarity score giữa 2 jobs.
        Phone=40%, Location=20%, Salary=15%, Title=15%, Company=10%
        """
        scores: Dict[str, float] = {}

        # Phone (L1 đã check → nếu vào đây nghĩa là không trùng phone exact)
        phone_sim = 1.0 if set(a.phones) & set(b.phones) else 0.0
        scores["phone"] = phone_sim

        # Location
        scores["location"] = self._text_sim(a.norm_location, b.norm_location)

        # Salary — overlap của 2 range
        scores["salary"] = self._salary_sim(
            a.salary_min, a.salary_max,
            b.salary_min, b.salary_max
        )

        # Title — TF-IDF cosine
        scores["title"] = self._tfidf_sim(a.norm_title, b.norm_title)

        # Company
        scores["company"] = self._text_sim(a.norm_company, b.norm_company)

        total = sum(SCORE_WEIGHTS[k] * v for k, v in scores.items())
        logger.debug(
            f"[score] {a.source}→{b.source} | "
            + " ".join(f"{k}={v:.2f}" for k, v in scores.items())
            + f" | total={total:.2f}"
        )
        return total

    def _text_sim(self, a: str, b: str) -> float:
        """Jaccard similarity trên token set."""
        if not a or not b:
            return 0.0
        sa, sb = set(a.split()), set(b.split())
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _salary_sim(self, lo1: float, hi1: float, lo2: float, hi2: float) -> float:
        """
        Overlap ratio giữa 2 khoảng lương.
        Nếu cả hai đều 0 (không có info) → 0 (không tính)
        """
        if lo1 == hi1 == 0 or lo2 == hi2 == 0:
            return 0.0
        overlap = max(0, min(hi1, hi2) - max(lo1, lo2))
        total   = max(hi1, hi2) - min(lo1, lo2)
        return overlap / total if total > 0 else 0.0

    def _tfidf_sim(self, a: str, b: str) -> float:
        """Cosine similarity bằng TF-IDF."""
        if not a or not b:
            return 0.0
        try:
            matrix = self.vectorizer.fit_transform([a, b])
            sim = cosine_similarity(matrix[0], matrix[1])[0][0]
            return float(sim)
        except Exception:
            return 0.0


# ================================================================
# CONVENIENCE: standalone check function
# ================================================================
def check_cross_duplicate(
    new_job: Dict,
    detector: CrossSourceDetector
) -> Tuple[bool, float, str]:
    """
    Shortcut dùng trong pipeline:
        is_dup, score, matched_id = check_cross_duplicate(job_dict, detector)
    """
    return detector.is_duplicate(new_job)
