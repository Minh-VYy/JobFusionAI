# cleaner/facebook_cleaner.py
import re
import hashlib
import unicodedata

class FacebookCleaner:
    """Clean và extract data từ Facebook post content"""

    # ============================================================
    # SECTION HEADERS — để tách nội dung theo cấu trúc bài
    # ============================================================
    _SECTION_HEADERS = [
        "mô tả công việc", "công việc của bạn", "nhiệm vụ",
        "yêu cầu", "yêu cầu nhỏ", "yêu cầu công việc",
        "quyền lợi", "chế độ", "phúc lợi", "ưu đãi",
        "liên hệ", "ứng tuyển", "contact",
        "địa chỉ", "địa điểm", "thời gian", "lương",
    ]

    # ============================================================
    # EXTRACT FIELDS
    # ============================================================

    def extract_title(self, content: str) -> str:
        """
        Trích xuất tiêu đề công việc.
        Chiến lược: Tìm dòng chứa tên vị trí thực sự (nhân viên X, tuyển X...)
        Tránh lấy câu kêu gọi, nội dung giữa bài, hoặc số lượng.
        """
        content = self._strip_facebook_noise(content)
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if not lines:
            return ""

        # --- Bước 1: Dòng có pattern "tuyển [vị trí]" hoặc "[Tên cty] tuyển [vị trí]" ---
        pattern_recruit = re.compile(
            r'(?:cần tuyển|tuyển dụng|tuyển gấp|tuyển)\s*[:·]?\s*(.{5,80})',
            re.IGNORECASE
        )
        # Chỉ xét 5 dòng đầu
        for line in lines[:5]:
            m = pattern_recruit.search(line)
            if m:
                candidate = m.group(1).strip().rstrip(":,.")
                # Loại bỏ nếu bắt đầu bằng số (vd: "20 nhân viên" → số lượng, không phải title)
                if not re.match(r'^\d+\s+', candidate) and 5 < len(candidate) < 120:
                    return self._normalize_title(candidate)

        # --- Bước 1b: "tìm đồng đội" → lấy dòng tiếp theo ---
        for line in lines[:3]:
            if re.search(r't[iì]m\s*đ[oồ]ng\s*đ[oộ]i', line, re.IGNORECASE):
                # Lấy dòng thứ 2 nếu có
                idx = lines.index(line)
                if idx + 1 < len(lines):
                    candidate = re.sub(r'^[\-•*\d+\s]+', '', lines[idx + 1]).strip()
                    if not re.match(r'^\d+\s+', candidate) and 5 < len(candidate) < 120:
                        return self._normalize_title(candidate)
                break

        # --- Bước 2: Dòng có tên vị trí job phổ biến ---
        job_role_pattern = re.compile(
            r'^[\-•*▪️►]?\s*((?:nhân viên|phục vụ|thu ngân|đầu bếp|phụ bếp|pha chế|'
            r'bartender|barista|bảo vệ|tài xế|shipper|kế toán|lập trình|kỹ thuật|'
            r'thiết kế|marketing|sale|sales|tư vấn|thợ may|thợ hàn|công nhân|'
            r'trưởng|quản lý|giám sát|chuyên viên|trợ lý|thực tập)[^\n]{0,60})',
            re.IGNORECASE
        )
        for line in lines[:8]:
            m = job_role_pattern.search(line)
            if m:
                candidate = m.group(1).strip().rstrip(":,.")
                if not re.match(r'^\d+\s+', candidate) and 5 < len(candidate) < 120:
                    return self._normalize_title(candidate)

        # --- Bước 3: Dòng đầu tiên nếu ngắn và có vẻ là tên/thương hiệu ---
        # Lọc dòng đầu: chỉ dùng nếu < 80 ký tự và không phải câu hỏi/cảm thán
        first = lines[0]
        if len(first) < 80 and not re.search(r'[?!]', first):
            # Cắt bỏ phần "cần tuyển" header
            for kw in ["cần tuyển", "tuyển dụng", "tuyển", "tìm đồng đội"]:
                if kw.lower() in first.lower():
                    if len(lines) > 1:
                        candidate = re.sub(r'^[\-•*▪️►\s]+', '', lines[1]).strip()
                        if 5 < len(candidate) < 120:
                            return self._normalize_title(candidate)
            return self._normalize_title(first)[:120]

        # --- Bước 4: Fallback --- lấy dòng đầu có độ dài hợp lý
        for line in lines[:5]:
            if 10 < len(line) < 100:
                return self._normalize_title(line)

        return self._normalize_title(lines[0])[:120]

    def extract_company(self, content: str) -> str:
        """
        Trích xuất tên công ty/cửa hàng/nhà hàng.
        Ưu tiên: dòng đầu trước "cần tuyển", hoặc tên sau prefix thương hiệu.
        """
        content = self._strip_facebook_noise(content)
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if not lines:
            return ""

        # --- Bước 1: Tên cty/thương hiệu trước "cần tuyển/tuyển dụng" ---
        m = re.match(
            r'^(.{3,80}?)\s+(?:cần tuyển|tuyển dụng|tuyển gấp|tuyển|tìm đồng đội|thông báo)',
            lines[0], re.IGNORECASE
        )
        if m:
            company = self._clean_text(m.group(1)).strip()
            # Cắt bỏ động từ hành động thừa ở cuối (ĐANG, cần, đang tuyển...)
            company = re.sub(r'\s+(?:đang|cần|sẽ|vừa|mới)$', '', company, flags=re.IGNORECASE).strip()
            company = company.rstrip(":,")
            # Phải là tên thực (không phải câu hỏi, không toàn số, không quá ngắn)
            if 2 < len(company) < 100 and not re.match(r'^\d+$', company):
                return company

        # --- Bước 2: Prefix nhận diện loại hình ---
        prefix_pattern = re.compile(
            r'(?:nhà hàng|quán|shop|cửa hàng|công ty|cty|spa|salon|gym|'
            r'trường|trung tâm|khách sạn|resort|cafe|coffee|tiệm|xưởng|'
            r'công ty tnhh|công ty cp)\s+([^\n,]{3,80})',
            re.IGNORECASE
        )
        m = prefix_pattern.search(content[:500])  # Chỉ tìm trong 500 ký tự đầu
        if m:
            start, end = m.start(1), m.end(1)
            name = self._clean_text(content[start:end]).strip().rstrip(":,")
            # Cắt tại stop words
            name = re.split(r'\s+(?:cần|tuyển|đang|thông)', name, flags=re.IGNORECASE)[0]
            if 2 < len(name) < 100:
                return name

        first_cleaned = self._clean_text(lines[0])
        # --- Bước 3: Dòng đầu viết hoa hoàn toàn VÀ ngắn = tên thương hiệu ---
        if lines[0].isupper() and 3 < len(lines[0]) < 80 and len(lines[0].split()) <= 4:
            return first_cleaned

        # --- Bước 4: Fallback — kiểm tra dòng đầu là câu nhắn/cảm thán hay tên thực ---
        first_lower = lines[0].lower()
        non_company_signals = [
            'bạn ', 'các bạn', 'vậy ', 'ai ', 'hãy ', 'mình ', 'chúng ta',
            'cần ', 'ưu tiên', 'thông báo', 'nhận hồ sơ',
            'khi nào', 'như thế nào', 'thực sự', 'may mắn', 'nhận ra',
            'là khi', 'chần chờ', 'chờ gì', 'nhận ra mình', 'mom ',
        ]
        # Câu quá dài (> 5 từ) hoặc chứa dấu chấm cuối câu thường là câu mô tả
        is_descriptive = len(lines[0].split()) > 5 or lines[0].rstrip().endswith('.')
        if not any(sig in first_lower for sig in non_company_signals) and not is_descriptive:
            if len(lines[0]) < 80 and '?' not in lines[0]:
                name = self._clean_text(lines[0]).strip()
                if len(name.split()) >= 2:
                    return name

        return ""

    def extract_salary(self, content: str) -> str:
        """
        Trích xuất thông tin lương.
        Fix: loại số điện thoại, hỗ trợ 4tr5, định dạng VNĐ.
        """
        # Xóa số điện thoại khỏi nội dung trước khi tìm lương
        content_no_phone = re.sub(r'(?:0|\+84)[\d\.\-\s]{9,13}', 'SĐT', content)
        content_lower = content_no_phone.lower()

        # Chuẩn hóa 4tr5 → 4.5tr trước khi match
        content_lower = re.sub(
            r'(\d+)tr(\d)\b',
            lambda m: f"{m.group(1)}.{m.group(2)}tr",
            content_lower
        )

        patterns = [
            # Ưu tiên: sau từ khóa lương (chính xác nhất)
            r'(?:lương|thu nhập|salary|mức lương)[:\s]+([^\n]{3,60})',
            # Khoảng lương dạng "X ~ Y tr" hoặc "X - Y tr"
            r'(\d+(?:[.,]\d+)?\s*(?:tr|triệu)\s*[~\-–đến]+\s*\d+(?:[.,]\d+)?\s*(?:tr|triệu)(?:\s*/\s*tháng)?)',
            # Dạng "đơn" 4tr5, 7tr, 4.5tr
            r'(\d+(?:[.,]\d+)?\s*tr(?:\s*/\s*(?:tháng|ca|h|giờ))?)',
            # VNĐ: 8.000.000, 3.355.000
            r'(\d{1,3}(?:\.\d{3}){1,2}\s*(?:đ|vnd|vnđ)?)',
            # k/h: 20k/h, 25k
            r'(\d+\s*k(?:\s*/\s*(?:h|giờ|ca))?)',
            # triệu rõ ràng
            r'(\d+(?:[.,]\d+)?\s*triệu(?:\s*/\s*tháng)?)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content_lower)
            if matches:
                # Lọc match quá ngắn hoặc là số điện thoại
                valid = [m.strip() for m in matches
                         if len(m.strip()) >= 3
                         and not re.match(r'^\d{9,11}$', m.strip().replace('.', ''))]
                if valid:
                    best = max(valid, key=len)
                    return best[:200]

        return "Thỏa thuận"

    def extract_location(self, content: str) -> str:
        """
        Trích xuất địa chỉ làm việc.
        """
        content_lower = content.lower()

        patterns = [
            r'địa\s*chỉ\s*(?:làm\s*việc)?[:\s]+([^\n]{5,150})',
            r'địa\s*điểm\s*(?:làm\s*việc)?[:\s]+([^\n]{5,150})',
            r'cơ\s*sở\s*\d*\s*[:\s]+([^\n]{5,100})',
            r'làm\s*việc\s*tại[:\s]+([^\n]{5,100})',
            r'khu\s*vực[:\s]+([^\n]{5,80})',
            r'văn\s*phòng[:\s]+([^\n]{5,100})',
        ]

        for pattern in patterns:
            match = re.search(pattern, content_lower)
            if match:
                loc = content[match.start(1):match.end(1)].strip()
                # Cắt tại liên hệ/số điện thoại/xuống dòng
                loc = re.split(r'(?:liên hệ|tel|sđt|hotline|0\d{9}|\n)', loc, flags=re.IGNORECASE)[0]
                loc = loc.rstrip(",.;").strip()
                if 5 < len(loc) < 200:
                    return loc[:255]

        # Fallback: tìm số nhà + tên đường
        street_match = re.search(
            r'(\d+[^\n,]{5,80}(?:đường|phố|ngõ|hẻm|quận|phường|tp\.|thành phố)[^\n,]{3,60})',
            content_lower
        )
        if street_match:
            start = street_match.start(1)
            return content[start:start + 120].strip()

        # Fallback: tên thành phố
        cities = {
            "đà nẵng": "Đà Nẵng", "da nang": "Đà Nẵng",
            "hà nội": "Hà Nội", "hanoi": "Hà Nội",
            "hồ chí minh": "TP. Hồ Chí Minh", "hcm": "TP. Hồ Chí Minh",
            "bình dương": "Bình Dương", "đồng nai": "Đồng Nai",
            "cần thơ": "Cần Thơ", "hải phòng": "Hải Phòng",
        }
        for key, val in cities.items():
            if key in content_lower:
                return val

        return ""

    def extract_skills(self, content: str) -> list:
        """Trích xuất kỹ năng yêu cầu"""
        skill_keywords = [
            "word", "excel", "photoshop", "canva",
            "tiếng anh", "tiếng nhật", "tiếng trung",
            "lái xe", "bằng b2", "bằng lái",
            "giao tiếp", "bán hàng", "tư vấn",
            "kế toán", "thiết kế", "lập trình",
            "pha chế", "phục vụ", "bartender",
        ]
        content_lower = content.lower()
        return [sk for sk in skill_keywords if sk in content_lower]

    def extract_phone(self, content: str) -> str:
        """Trích xuất số điện thoại"""
        # Chuẩn hóa trước: xóa dấu chấm/gạch giữa số
        content_clean = re.sub(r'(\d)[.\-\s](\d)', r'\1\2', content)
        patterns = [
            r'(?:0|\+84)\d{9}',
        ]
        for pat in patterns:
            match = re.search(pat, content_clean)
            if match:
                phone = re.sub(r'[\s\-\.]', '', match.group())
                if len(phone) >= 10:
                    return phone
        return ""

    def extract_job_type(self, content: str) -> str:
        """Trích xuất loại hình công việc"""
        c = content.lower()
        types = []
        if re.search(r'full[\s\-]?time|toàn thời gian', c):
            types.append("Toàn thời gian")
        if re.search(r'part[\s\-]?time|bán thời gian|partime', c):
            types.append("Bán thời gian")
        if "thời vụ" in c:
            types.append("Thời vụ")
        return ", ".join(types) if types else ""

    def extract_requirements(self, content: str) -> str:
        """
        Trích xuất phần yêu cầu công việc.
        Dừng tại: quyền lợi / chế độ / liên hệ / ứng tuyển.
        """
        stop = r'(?:quyền lợi|phúc lợi|chế độ|ưu đãi|liên hệ|ứng tuyển|contact|hồ sơ)'
        match = re.search(
            r'(?:yêu cầu(?:\s+nhỏ)?(?:\s+công\s*việc)?|requirements)[:\s]*(.*?)(?=\n\s*' + stop + r'|\Z)',
            content, re.IGNORECASE | re.DOTALL
        )
        if match:
            req = match.group(1).strip()
            # Xóa "Ẩn bớt" nếu còn sót
            req = re.sub(r'\s*ẩn bớt\s*$', '', req, flags=re.IGNORECASE).strip()
            if len(req) > 10:
                return req
        return ""

    # ============================================================
    # HELPERS
    # ============================================================

    def _strip_facebook_noise(self, text: str) -> str:
        """Xóa các chuỗi rác của Facebook UI"""
        noise = [
            r'\s*ẩn bớt\s*$',        # Nút "Ẩn bớt"
            r'\s*see more\s*$',       # "See more"
            r'\s*xem thêm\s*$',       # "Xem thêm"
        ]
        for pattern in noise:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
        return text.strip()

    def _normalize_title(self, title: str) -> str:
        """Chuẩn hóa title: bỏ emoji, viết hoa chữ đầu, trim"""
        title = self._clean_text(title)
        title = re.sub(r'^[\-•*▪️►\s]+', '', title).strip()
        if title:
            title = title[0].upper() + title[1:]
        return title[:200]

    def _clean_text(self, text: str) -> str:
        """Xóa emoji, bold unicode Facebook, chuẩn hóa viết tắt, normalize space"""
        # Xóa emoji
        emoji_pattern = re.compile(
            "[\U00010000-\U0010ffff"
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\u2600-\u26FF\u2700-\u27BF"
            "]+",
            flags=re.UNICODE
        )
        text = emoji_pattern.sub("", text)

        # Chỉ flatten các ký tự bold/italic unicode Facebook (Mathematical Alphanumeric Symbols)
        # Giữ nguyên tiếng Việt có dấu
        result = []
        for ch in text:
            cp = ord(ch)
            # Bold/Italic Latin: U+1D400–1D7FF
            if 0x1D400 <= cp <= 0x1D7FF:
                norm = unicodedata.normalize('NFKD', ch)
                ascii_ch = norm.encode('ascii', 'ignore').decode('ascii')
                result.append(ascii_ch if ascii_ch else ch)
            else:
                result.append(ch)
        text = ''.join(result)

        # Chuẩn hóa viết tắt phổ biến
        abbreviations = {
            r'\bnv\b': 'nhân viên',
            r'\bpt\b': 'part-time',
            r'\bft\b': 'full-time',
            r'\bđc\b': 'địa chỉ',
            r'\bsp\b': 'sản phẩm',
            r'\bkh\b': 'khách hàng',
            r'\bql\b': 'quản lý',
            r'\bkn\b': 'kinh nghiệm',
            r'\btg\b': 'thời gian',
            r'\blh\b': 'liên hệ',
        }
        for pat, repl in abbreviations.items():
            text = re.sub(pat, repl, text, flags=re.IGNORECASE)

        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def make_fingerprint(self, content: str) -> str:
        """Tạo hash fingerprint để detect duplicate"""
        normalized = re.sub(r'\s+', ' ', content.lower().strip())
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()