# cleaner/facebook_nlp.py
import re
import unicodedata
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import hashlib
import logging

logger = logging.getLogger(__name__)

# ================================================================
# SPAM KEYWORDS
# ================================================================
SPAM_PATTERNS = [
    # Exact phrases
    "thu nhập khủng",
    "việc nhẹ lương cao",
    "kiếm tiền tại nhà",
    "ngồi nhà kiếm tiền",
    "làm tại nhà.*lương",
    "đa cấp",
    "cọc tiền",
    "đặt cọc",
    "không cần đi làm",
    "tuyển ctv online",
    # ✅ Thêm mới — match Post 3
    r"\d+tr.*tháng.*không cần",
    r"thu nhập.*\d+tr.*tháng",
]

# ================================================================
# LOCATION MAP
# ================================================================
LOCATION_MAP = {
    "đà nẵng": "Đà Nẵng",
    "da nang": "Đà Nẵng",
    "hà nội": "Hà Nội",
    "hanoi": "Hà Nội",
    "hồ chí minh": "TP. Hồ Chí Minh",
    "hcm": "TP. Hồ Chí Minh",
    "tp.hcm": "TP. Hồ Chí Minh",
    "bình dương": "Bình Dương",
    "đồng nai": "Đồng Nai",
}


class FacebookNLP:
    """
    NLP Pipeline cho Facebook job posts.
    Clean → Extract → Normalize → Score → Classify
    """

    # Post type constants
    TYPE_RECRUITING  = "recruiting"   # Người tuyển dụng
    TYPE_JOB_SEEKING = "job_seeking"  # Người tìm việc
    TYPE_UNKNOWN     = "unknown"       # Không xác định

    # ============================================================
    # CLEAN TEXT
    # ============================================================

    def clean_text(self, text: str) -> str:
        """Clean toàn bộ: emoji, ký tự lạ, whitespace"""
        if not text:
            return ""

        # Xóa emoji + unicode đặc biệt
        text = self._remove_emoji(text)

        # Xóa bold facebook (𝐀𝐁𝐂 → ABC)
        text = self._normalize_unicode(text)

        # Xóa "...Xem thêm", "See more"
        text = re.sub(r'\.{3,}Xem thêm', '', text)
        text = re.sub(r'\.{3,}See more', '', text)

        # Xóa ký tự đặc biệt thừa
        text = re.sub(r'[-=*]{3,}', '', text)

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def _remove_emoji(self, text: str) -> str:
        emoji_pattern = re.compile(
            "[\U00010000-\U0010ffff"
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\u2600-\u26FF\u2700-\u27BF]+",
            flags=re.UNICODE
        )
        return emoji_pattern.sub(" ", text)

    def _normalize_unicode(self, text: str) -> str:
        """Chuyển bold/italic unicode Facebook về ASCII"""
        result = []
        for char in text:
            normalized = unicodedata.normalize('NFKD', char)
            ascii_char = normalized.encode('ascii', 'ignore').decode('ascii')
            result.append(ascii_char if ascii_char else char)
        return ''.join(result)

    # ============================================================
    # EXTRACT FIELDS
    # ============================================================

    def extract_title(self, content: str) -> str:
        """Lấy dòng đầu có nghĩa làm title"""
        content = self.clean_text(content)
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        for line in lines[:5]:
            if 10 < len(line) < 200:
                return line
        return lines[0][:200] if lines else ""

    def extract_salary(self, content: str) -> str:
        """Trích xuất thông tin lương — hỗ trợ nhiều định dạng."""
        # Normalize: 5TR5 → 5.5TR, 5tr5 → 5.5tr
        # Pattern này bắt "5TR5", "7TR", "5tr5" (số giữa hai chữ viết tắt)
        content_norm = re.sub(
            r'(\d+)tr(\d)\b',
            lambda m: f"{m.group(1)}.{m.group(2)}tr",
            content.lower()
        )
        content_norm = re.sub(
            r'(\d+)TR(\d)\b',
            lambda m: f"{m.group(1)}.{m.group(2)}TR",
            content
        )

        patterns = [
            # "thu nhập 5tr5-7tr" hoặc "lương 5tr-7tr"
            r'(?:thu\s*nhập|lương)[:\s]+([^\n]{3,60})',
            # "5TR5-7TR" (in hoa, kiểu Facebook)
            r'(\d+[.,]?\d*\s*TR\d?\s*[-–]đến\s*\d+[.,]?\d*\s*TR\d?)',
            # "5tr5-7tr" hoặc "5.5tr-7tr"
            r'(\d+[.,]?\d*\s*tr\d?\s*[-–đến]+\s*\d+[.,]?\d*\s*tr\d?)',
            # "5-7 triệu" / "5tr - 7tr"
            r'(\d+[\.,]?\d*\s*(?:triệu|tr)(?:[^\n,\.]{0,20}))',
            r'(\d+[\.,]?\d*\s*k\b(?:[^\n,\.]{0,15}))',
            r'up\s*to[:\s]+([^\n,\.]{3,40})',
            r'từ\s+(\d+[\.,]?\d*\s*(?:triệu|tr|k))',
            r'(\d+k?[-–]\d+k?\s*(?:triệu|tr|k)?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, content_norm, re.IGNORECASE)
            if match:
                salary = match.group(1).strip()
                if len(salary) < 80:
                    return salary.upper() if salary.isupper() else salary
        return "Thỏa thuận"

    def extract_location(self, content: str) -> str:
        """Trích xuất địa điểm — ưu tiên địa chỉ cụ thể."""
        content_lower = content.lower()

        # Pattern sau từ khóa địa chỉ cụ thể (ưu tiên cao nhất)
        patterns = [
            r'chi\s*nhánh[:\s]+([^\n]{5,100})',
            r'chi\s*nhanh[:\s]+([^\n]{5,100})',          # ASCII fallback ← THÊM
            r'địa\s*chỉ[:\s]+([^\n]{5,100})',
            r'dia\s*chi[:\s]+([^\n]{5,100})',             # ASCII fallback ← THÊM
            r'địa\s*điểm[:\s]+([^\n]{5,80})',
            r'làm\s*việc\s*tại[:\s]+([^\n]{5,80})',
            r'khu\s*vực[:\s]+([^\n]{5,60})',
            r'vị\s*trí[:\s]+([^\n]{5,60})',
            r'vi\s*tri[:\s]+([^\n]{5,60})',               # ASCII fallback ← THÊM
            r'(?:tại|ở)\s+([^\n,\.]{5,60})',
        ]
        for pattern in patterns:
            match = re.search(pattern, content_lower)
            if match:
                loc = match.group(1).strip()
                # Lấy phần trước dấu phẩy đầu tiên nếu quá dài
                loc_short = re.split(r'[\n]', loc)[0].strip()
                if 5 <= len(loc_short) <= 120:
                    # Trả về nguyên vẹn (có thể có số nhà, tên đường)
                    for key, val in LOCATION_MAP.items():
                        if key in loc_short:
                            return val
                    return loc_short.title()

        # Fallback: tìm tên thành phố trực tiếp
        for key, val in LOCATION_MAP.items():
            if key in content_lower:
                return val

        return "Đà Nẵng"  # Default

    def extract_phone(self, content: str) -> str:
        """Trích xuất số điện thoại"""
        # Chuẩn hóa: xóa space/dash giữa số
        content_clean = re.sub(r'(\d)\s+(\d)', r'\1\2', content)
        pattern = r'(?:0|\+84)\d{9}'
        match = re.search(pattern, content_clean)
        return match.group().strip() if match else ""

    def extract_company(self, content: str) -> str:
        """Trích xuất tên công ty/cửa hàng."""
        # Words phổ biến trong tên công ty (dùng để lấy toàn bộ cụm từ sau prefix)
        STOP_AFTER = r'(?:tuyển|cần|đang|thông|thời|tìm|\.{2,}|\n)'
        patterns = [
            # Có dấu hai chấm rõ ràng
            r'(?:công ty|cty|ct)[:\s]+([^\n]{3,100})',
            r'(?:nhà hàng|khách sạn|resort|hotel)[:\s]+([^\n]{3,80})',
            r'(?:cửa hàng|quán)[:\s]+([^\n]{3,60})',
            # Shop + tên (không cần dấu hai chấm): "Shop good's tuyển..."
            r'^(?:shop|cửa\s*hàng|quán|nhà\s*hàng)\s+([\w\s\'\"&]+?)(?=\s+(?:tuyển|cần|\.{2}|$))',
            # Tên bắt đầu dòng với chữ hoa hoặc từ nhận biết
            r'(?:bênH viện|trường|viện)[:\s]+([^\n]{3,80})',
        ]
        content_lower = content.lower()
        for i, pattern in enumerate(patterns):
            src = content_lower if i < 3 else content
            match = re.search(pattern, src, re.MULTILINE)
            if match:
                name = match.group(1).strip()
                # Loại bỏ phần sau stop words
                name = re.split(STOP_AFTER, name, flags=re.IGNORECASE)[0].strip()
                if 2 <= len(name) <= 120:
                    return name[:120]
        return ""

    def extract_skills(self, content: str) -> list:
        """Trích xuất kỹ năng yêu cầu"""
        skills_dict = {
            "word": ["word", "microsoft word"],
            "excel": ["excel", "microsoft excel"],
            "photoshop": ["photoshop", "ps"],
            "canva": ["canva"],
            "tiếng anh": ["tiếng anh", "english", "anh văn"],
            "tiếng nhật": ["tiếng nhật", "japanese"],
            "tiếng trung": ["tiếng trung", "chinese"],
            "lái xe": ["lái xe", "bằng b1", "bằng b2", "xe máy"],
            "bán hàng": ["bán hàng", "sales"],
            "pha chế": ["pha chế", "bartender"],
            "phục vụ": ["phục vụ", "waiter"],
            "kế toán": ["kế toán", "accounting"],
            "lập trình": ["lập trình", "coding", "developer"],
        }
        content_lower = content.lower()
        found = []
        for skill, aliases in skills_dict.items():
            if any(alias in content_lower for alias in aliases):
                found.append(skill)
        return found

    # ============================================================
    # SPAM DETECTION
    # ============================================================

    def is_spam(self, content: str) -> tuple[bool, float, str]:
        content_lower = content.lower()
        spam_hits = []

        for pattern in SPAM_PATTERNS:
            try:
                if re.search(pattern, content_lower):
                    spam_hits.append(pattern)
            except re.error:
                if pattern in content_lower:
                    spam_hits.append(pattern)

        # ✅ Fix: 1 pattern đủ để là spam nếu nghiêm trọng
        serious = ["thu nhập khủng", "đa cấp", "cọc"]
        for hit in spam_hits:
            if any(s in hit for s in serious):
                return True, 1.0, hit

        spam_score = min(len(spam_hits) / 2.0, 1.0)
        is_spam_flag = spam_score >= 0.5

        reason = "; ".join(spam_hits[:3]) if spam_hits else ""
        return is_spam_flag, spam_score, reason

    # ============================================================
    # QUALITY SCORING
    # ============================================================

    def quality_score(self, content: str) -> float:
        """
        Chấm điểm chất lượng bài đăng (0.0 → 1.0).
        Càng nhiều thông tin → điểm càng cao.
        """
        score = 0.0
        content_lower = content.lower()

        # Có salary → +0.25
        if re.search(r'\d+\s*(?:triệu|tr|k)', content_lower):
            score += 0.25

        # Có số điện thoại → +0.25
        if re.search(r'(?:0|\+84)\d{9}', content):
            score += 0.25

        # Có địa điểm cụ thể → +0.20
        if any(city in content_lower for city in LOCATION_MAP):
            score += 0.20

        # Có thời gian làm việc → +0.15
        if re.search(r'(?:fulltime|part.?time|ca sáng|ca tối|giờ làm)', content_lower):
            score += 0.15

        # Độ dài hợp lý (50-500 chars) → +0.15
        if 50 <= len(content) <= 500:
            score += 0.15

        return round(min(score, 1.0), 2)

    # ============================================================
    # POST TYPE CLASSIFIER — Phân biệt tuyển vs tìm việc
    # ============================================================

    # Tín hiệu mạnh: Đây là bài TUYỂN DỤNG
    _RECRUIT_SIGNALS = [
        r'\btu[yy][eế]n\b',            # "tuyển"
        r'cần tuy[eế]n',              # "cần tuyển"
        r'\btu[yy][eế]n gấp\b',        # "tuyển gấp"
        r'cần ng[uư][oớ][iì]',          # "cần người"
        r'tuy[eế]n d[uụ]ng',           # "tuyển dụng"
        r'li[eế]n hệ .{0,20}(?:ứng tuy[eế]n|g[aặ]p)',  # "liên hệ ứng tuyển"
        r'(?:ứng vi[eế]n|ng[uư][oớ][iì] ứng tuy[eế]n)',  # "ứng viên"
        r'(?:m[oô]i tr[uư][oớ]ng|chế đ[oộ]|ph[uú]c l[oợ]i)',  # "môi trường"/"phúc lợi"
        r'(?:nh[aà]n vi[eế]n n[uư] ?:|n[aầ]m ?:)',  # "nhân viên nữ:"
        r'nhi[eế]m v[uụ]',              # "nhiệm vụ"
        r'y[eế]u cầu',                  # "yêu cầu"
        r'quy[eế]n l[oợ]i',              # "quyền lợi"
        r'\bCV\b',                       # "CV"
        r'[Cc][Tt][Yy] |c[oô]ng ty',    # "cty "/"công ty"
        r't[iì]m\s*đ[oồ]ng\s*đ[oộ]i',  # "tìm đồng đội"
        r'nh[aâ]n\s*vi[eê]n',          # "nhân viên"
        r'fulltime|parttime|part-time',
        r'ca\s*l[aà]m\s*vi[eệ]c',
        r'm[uứ]c\s*l[uư][oơ]ng',        # "mức lương"
        r'v[iị]\s*tr[ií]',             # "vị trí"
        r't[iì]m\s*b[aạ]n\s*(?:l[aà]m|ph[uụ])', # "tìm bạn làm/phụ"
        r'cần\s*t[iì]m\s*(?:nam|n[uữ])\s*ph[uụ]', # "cần tìm nam/nữ phụ"
    ]

    # Tín hiệu mạnh: Đây là bài TÌM VIỆC
    _SEEKING_SIGNALS = [
        # ── Ngôi thứ nhất + hành động tìm kiếm ───────────────────
        r'(?:t[oô]i|m[iì]nh|em|ch[iị]|anh|b[aạ]n)\s*(?:cần|đang\s*t[iì]m|mu[oố]n\s*t[iì]m|đang\s*ki[eế]m)',

        # ── Bài tìm việc trực tiếp ────────────────────────────────
        r't[iì]m\s*vi[eế]c',
        r'xin\s*vi[eế]c',
        r'cần\s*t[iì]m\s*vi[eế]c',
        r'cần\s*vi[eế]c\s*l[aà]m',          # "cần việc làm" ← THÊM
        r'ki[eế]m\s*vi[eế]c(?:\s*l[aà]m)?',
        r'cần\s*ki[eế]m\s*vi[eế]c',

        # ── Giới tính + tuổi/năm sinh rút gọn + cần/tìm ──────────
        # "nữ 2k9 cần việc", "nam 20t tìm việc", "nữ 2005 cần"
        r'(?:nữ|nam|girl|boy)\s*(?:\d{2}t|\d{4}|2k\d)\s*.{0,30}(?:cần|t[iì]m|ki[eế]m|xin)',  # ← THÊM
        # "2k9 cần việc", "sinh năm 2004 cần"
        r'\b2k\d\b.{0,30}(?:cần|t[iì]m|ki[eế]m|vi[eế]c)',    # ← THÊM
        r'sinh\s*năm\s*\d{4}.{0,30}(?:cần|t[iì]m)',            # ← THÊM
        # "là nữ X tuổi/t cần"
        r'(?:là\s*)?(?:nữ|nam)\s*\d{2}\s*(?:t|tuổi).{0,40}(?:cần|t[iì]m|ki[eế]m)',  # ← THÊM

        # ── Số người + cần/tìm ────────────────────────────────────
        r'\d+\s*(?:nam|n[uữ]|ng[uư][oờ][iì]|sv|sinh\s*vi[eê]n|b[aạ]n)\s*.{0,30}(?:cần|t[iì]m|ki[eế]m)',

        # ── Sinh viên + cần/tìm ───────────────────────────────────
        r'(?:sv|sinh\s*vi[eê]n|svi[eê]n)\s*.{0,20}(?:cần|t[iì]m|ki[eế]m)',

        # ── Tuổi + cần/tìm ────────────────────────────────────────
        r'\d{2}\s*tu[oổ]i.{0,30}(?:cần|t[iì]m|ki[eế]m)',

        # ── Muốn đi làm ──────────────────────────────────────────
        r'mu[oố]n\s*(?:t[iì]m|xin|đi\s*l[aà]m)',

        # ── Câu hỏi tìm việc ─────────────────────────────────────
        r'ai\s*c[oó]\s*vi[eế]c',
        r'ai\s*bi[eế]t\s*ch[oỗ]\s*n[aà]o',
        r'có\s*ch[oỗ]\s*n[aà]o\s*(?:tuy[eể]n|c[aầ]n)',

        # ── Tự giới thiệu bản thân (kỹ năng ngôn ngữ) ────────────
        # "biết tiếng anh/trung/nhật" + ngữ cảnh xin việc ← THÊM
        r'bi[eế]t\s*ti[eế]ng\s*(?:anh|trung|nh[aậ]t|h[aà]n|ph[aá]p).{0,60}(?:cần|t[iì]m|xin|vi[eế]c)',  # ← THÊM
        r'(?:cần|t[iì]m|xin).{0,60}bi[eế]t\s*ti[eế]ng',       # ← THÊM: "cần việc...biết tiếng"
        r'(?:mình|em|tôi)\s*(?:biết|có thể|đã học).{0,30}ti[eế]ng',  # ← THÊM: "mình biết tiếng"

        # ── "Đã từng" — tự kể kinh nghiệm bản thân ───────────────
        r'đã\s*t[uừ]ng\s*.{0,50}(?:cần|t[iì]m|xin|vi[eế]c)',  # ← THÊM: "đã từng pvu cf...cần việc"
        r'(?:mình|em|tôi)\s*đã\s*t[uừ]ng',                     # ← THÊM: "mình đã từng..."

        # ── Điều kiện giờ giấc cá nhân ───────────────────────────
        r'nh[aậ]n\s*l[uư][oơ]ng\s*(?:li[eề]n|ngay|hàng\s*ngày)',  # ← THÊM: "nhận lương liền"
        r'l[aà]m\s*(?:hè|thêm\s*mùa\s*hè|thời\s*vụ)',          # ← THÊM: "làm hè", "làm thêm mùa hè"
        r'(?:không\s*làm|kh[oô]ng\s*làm)\s*khuya',              # "không làm khuya" — điều kiện cá nhân

        # ── Tự giới thiệu kinh nghiệm ─────────────────────────────
        r'(?:m[iì]nh|t[oô]i|em)\s*c[oó]\s*th[eể]\s*l[aà]m',
        r's[aẵ]n\s*s[aà]ng\s*l[aà]m',
        r'kinh\s*nghi[eế]m\s*b[aả]n\s*th[aâ]n',
        r'(?:kh[oô]ng|ch[uư]a)\s*c[oó]\s*kinh\s*nghi[eế]m',
        r'mới\s*tốt\s*nghiệp',
        r'đang\s*(?:thất\s*nghiệp|trống\s*lịch|rảnh|không\s*có\s*việc)',

        # ── Mong muốn cá nhân ────────────────────────────────────
        r'(?:m[iì]nh|em|t[oô]i)\s*(?:c[aầ]n|mu[oố]n|đang\s*c[aầ]n)\s*(?:vi[eế]c|l[uư][oơ]ng|thu\s*nhập)',
        r'g[aắ]n\s*b[oó]\s*l[aâ]u\s*d[aà]i.{0,40}(?:m[iì]nh|t[oô]i|em|(?:ch[uú]ng?\s*)?t[oô]i)',
        r'kiếm\s*thêm\s*(?:thu\s*nhập|tiền)',
        r'việc\s*gì\s*cũng\s*làm',
        r'có\s*việc\s*gì\s*(?:không|nhỉ)',
    ]

    def classify_post_type(self, content: str) -> tuple:
        """
        Phân loại bài đăng: 'recruiting' hay 'job_seeking'.
        Match trên cả văn bản có dấu và không dấu (ASCII stripped).

        Returns:
            (post_type: str, recruit_score: int, seeking_score: int)
        """
        text = content.lower()
        # Strip diacritics để match bài gõ không dấu (vd: "can tim viec lam he")
        text_ascii = self._normalize_unicode(text)

        recruit_score = 0
        seeking_score = 0

        for pattern in self._RECRUIT_SIGNALS:
            if re.search(pattern, text) or re.search(pattern, text_ascii):
                recruit_score += 1

        for pattern in self._SEEKING_SIGNALS:
            if re.search(pattern, text) or re.search(pattern, text_ascii):
                seeking_score += 1

        # Quyết định
        if seeking_score >= 2 and seeking_score > recruit_score:
            return self.TYPE_JOB_SEEKING, recruit_score, seeking_score
        elif recruit_score >= 1 and recruit_score >= seeking_score:
            return self.TYPE_RECRUITING, recruit_score, seeking_score
        elif seeking_score == 1 and recruit_score == 0:
            return self.TYPE_JOB_SEEKING, recruit_score, seeking_score
        else:
            return self.TYPE_UNKNOWN, recruit_score, seeking_score

    def is_recruiting_post(self, content: str) -> tuple:
        """
        Shortcut: True nếu bài là tuyển dụng (có thể dùng trực tiếp trong crawler).

        Returns:
            (is_recruiting: bool, reason: str)
        """
        post_type, r_score, s_score = self.classify_post_type(content)

        if post_type == self.TYPE_RECRUITING:
            return True, f"recruit_signals={r_score}"
        elif post_type == self.TYPE_JOB_SEEKING:
            return False, f"job_seeking: seek_signals={s_score}, recruit_signals={r_score}"
        else:
            # Unknown: chấp nhận nếu có keyword tuyển dụng cơ bản
            basic = ["tuyển", "cần người", "việc làm"]
            has_basic = any(kw in content.lower() for kw in basic)
            return has_basic, f"unknown: basic_kw={has_basic}"