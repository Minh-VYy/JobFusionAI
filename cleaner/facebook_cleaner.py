# cleaner/facebook_cleaner.py
import re
import hashlib

class FacebookCleaner:
    """Clean và extract data từ Facebook post content"""

    # ============================================================
    # EXTRACT FIELDS
    # ============================================================

    def extract_title(self, content: str) -> str:
        """
        Trích xuất tiêu đề job từ bài viết.
        Ưu tiên: Tên quán/công ty + vị trí tuyển dụng từ dòng đầu.
        VD: "Bánh xèo Bà Thuý cần tuyển:" → "Nhân viên phụ quán ăn"
        """
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if not lines:
            return ""

        # Bước 1: Tìm dòng chứa vị trí tuyển dụng cụ thể
        title_patterns = [
            # Dòng có từ khóa vị trí sau dấu +, -, •
            r'^[+\-•*]\s*(.{5,80})$',
            # "tuyển: XXX" hoặc "cần: XXX"
            r'(?:tuyển|cần tuyển|cần|tuyển dụng)[:\s]+(.{5,80})',
            # Vị trí công việc phổ biến
            r'((?:nhân viên|kỹ thuật viên|trưởng|phó|giám sát|quản lý|chuyên viên|lập trình viên|kế toán|thu ngân|bảo vệ|tài xế|shipper|phục vụ|phụ bếp|bartender|barista|đầu bếp|thợ|công nhân)\s+[^\n]{3,60})',
        ]

        for pattern in title_patterns:
            for line in lines[:8]:  # Chỉ xét 8 dòng đầu
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    title = self._clean_text(m.group(1)).strip().rstrip(":,")
                    if 5 < len(title) < 150:
                        return title

        # Bước 2: Dùng dòng đầu tiên nhưng cắt bỏ phần "cần tuyển" header
        first = lines[0]
        for keyword in ["cần tuyển:", "cần tuyển", "tuyển dụng:", "tuyển:"]:
            if keyword.lower() in first.lower():
                # Lấy dòng tiếp theo sau phần header
                if len(lines) > 1:
                    candidate = lines[1].lstrip("+•-* ").strip()
                    if len(candidate) > 5:
                        return self._clean_text(candidate)[:200]

        # Bước 3: Fallback - dùng dòng đầu tiên, giới hạn độ dài
        return self._clean_text(first)[:150]

    def extract_company(self, content: str) -> str:
        """
        Trích xuất tên công ty/cửa hàng/nhà hàng.
        Ưu tiên dòng đầu tiên vì thường chứa tên thương hiệu.
        VD: "Bánh xèo Bà Thuý cần tuyển" → "Bánh xèo Bà Thuý"
        """
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if not lines:
            return ""

        content_lower = content.lower()

        # Pattern 1: Tên công ty trước "cần tuyển / tuyển dụng / thông báo"
        m = re.match(
            r'^(.{3,80}?)\s+(?:cần tuyển|tuyển dụng|tuyển|thông báo|kính mời)',
            lines[0], re.IGNORECASE
        )
        if m:
            company = m.group(1).strip().rstrip(":,")
            if 3 < len(company) < 100:
                return self._clean_text(company)

        # Pattern 2: Sau từ khóa chỉ tên cơ sở
        patterns = [
            r'(?:nhà hàng|quán|shop|cửa hàng|công ty|cty|spa|salon|gym|trường|trung tâm|khách sạn|resort|cafe|coffee)\s+([^\n,]{3,80})',
        ]
        for pattern in patterns:
            match = re.search(pattern, content_lower)
            if match:
                # Lấy lại đúng case từ content gốc (không lower)
                start = match.start(1)
                end = match.end(1)
                return self._clean_text(content[start:end]).strip()[:300]

        return ""

    def extract_salary(self, content: str) -> str:
        """
        Trích xuất thông tin lương.
        Fix: nhận dạng đầy đủ "4tr5", "4.5tr", "4,5 triệu"
        """
        content_lower = content.lower()

        patterns = [
            # Kiểu "4tr5", "4tr", "4.5tr"
            r'(\d+(?:[.,]\d+)?\s*tr\d*(?:\s*\d+)?(?:\s*/\s*(?:tháng|ca|h|giờ))?)',
            # Kiểu "4.500.000", "4,500,000"
            r'(\d{1,3}(?:[.,]\d{3})+\s*(?:đ|vnd|vnđ)?)',
            # Kiểu "4 triệu", "4.5 triệu / tháng"
            r'(\d+(?:[.,]\d+)?\s*triệu(?:\s*/\s*tháng)?)',
            # Kiểu "40k/h", "50k"
            r'(\d+\s*k(?:\s*/\s*(?:h|giờ|ca))?)',
            # Kiểu sau từ khóa lương
            r'(?:lương|thu nhập|salary|mức lương)[:\s]+([^\n]{3,60})',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content_lower)
            if matches:
                # Lấy match dài nhất (đầy đủ nhất)
                best = max(matches, key=len).strip()
                if len(best) >= 2:
                    return best[:200]

        return "Thỏa thuận"

    def extract_location(self, content: str) -> str:
        """
        Trích xuất địa chỉ — chỉ lấy đến hết địa chỉ, không lấy thêm text.
        Fix: cắt đúng tại xuống dòng, không để địa chỉ dính với "Liên hệ 0..."
        """
        content_lower = content.lower()

        patterns = [
            r'địa chỉ[:\s]+([^\n]{5,100})',
            r'địa điểm[:\s]+([^\n]{5,100})',
            r'làm việc tại[:\s]+([^\n]{5,80})',
            r'khu vực[:\s]+([^\n]{5,60})',
            r'tại[:\s]+([^\n]{5,50})',
            r'(?:số|địa)\s+\d+[^\n]{5,80}',
        ]

        for pattern in patterns:
            match = re.search(pattern, content_lower)
            if match:
                loc = match.group(1).strip()
                # Cắt bỏ mọi thứ sau "liên hệ", số điện thoại, hoặc dấu xuống dòng
                loc = re.split(r'(?:liên hệ|tel|sđt|hotline|0\d{9}|\n)', loc, flags=re.IGNORECASE)[0]
                loc = re.split(r'[,\.;]', loc)[0].strip()
                if 3 < len(loc) < 150:
                    return loc[:255]

        # Fallback: tên thành phố
        cities = [
            "đà nẵng", "da nang", "hà nội", "hanoi",
            "hồ chí minh", "hcm", "tp.hcm",
            "bình dương", "đồng nai", "cần thơ",
            "hải phòng", "nha trang", "huế",
        ]
        for city in cities:
            if city in content_lower:
                return city.title()

        return ""

    def extract_skills(self, content: str) -> list:
        """Trích xuất kỹ năng yêu cầu"""
        skill_keywords = [
            "word", "excel", "photoshop", "canva",
            "tiếng anh", "tiếng nhật", "tiếng trung",
            "lái xe", "bằng b2", "bằng lái",
            "giao tiếp", "bán hàng", "tư vấn",
            "kế toán", "thiết kế", "lập trình",
        ]
        content_lower = content.lower()
        return [sk for sk in skill_keywords if sk in content_lower]

    def extract_phone(self, content: str) -> str:
        """Trích xuất số điện thoại"""
        patterns = [
            r'(?:0|\+84)[\s\-\.]?(?:\d[\s\-\.]?){9}',
            r'0\d{9,10}',
        ]
        for pat in patterns:
            match = re.search(pat, content)
            if match:
                phone = re.sub(r'[\s\-\.]', '', match.group())
                if len(phone) >= 10:
                    return phone
        return ""

    # ============================================================
    # CLEAN TEXT
    # ============================================================

    def _clean_text(self, text: str) -> str:
        """Xóa emoji, ký tự đặc biệt, normalize space"""
        emoji_pattern = re.compile(
            "[\U00010000-\U0010ffff"
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "]+",
            flags=re.UNICODE
        )
        text = emoji_pattern.sub("", text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def make_fingerprint(self, content: str) -> str:
        """Tạo hash fingerprint để detect duplicate"""
        normalized = re.sub(r'\s+', ' ', content.lower().strip())
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()