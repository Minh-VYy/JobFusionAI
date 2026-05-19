# crawler/topcv_crawler.py
import re
from bs4 import BeautifulSoup
from crawler.base_crawler import BaseCrawler, logger
from models.job_model import JobModel
from datetime import datetime, timedelta

NON_SKILL_PATTERNS = [
    "phần mềm", "giáo dục", "y tế", "thương mại",
    "logistics", "ngân hàng", "bất động sản",
    "marketing", "kế toán", "nhân sự",
    "nghỉ thứ", "nghỉ phép", "năm kinh nghiệm",
    "đại học", "cao đẳng", "trung cấp",
    "toàn thời gian", "bán thời gian",
]

class TopCVCrawler(BaseCrawler):
    """
    Crawler cho TopCV.vn
    URL pattern: https://www.topcv.vn/tim-viec-lam-it?page=1
    """

    BASE_URL = "https://www.topcv.vn/tim-viec-lam-it"
    SOURCE_NAME = "topcv"

    def __init__(self, max_pages: int = 3, headless: bool = True):
        super().__init__(headless=headless)
        self.max_pages = max_pages   # Số trang muốn crawl
        self.jobs = []               # Lưu kết quả

    # ==================== CRAWL DANH SÁCH ====================

    def crawl(self, progress_callback=None) -> list[JobModel]:
        """Entry point — crawl toàn bộ"""
        self.start()
        try:
            for page_num in range(1, self.max_pages + 1):
                if progress_callback:
                    progress_callback(page_num, self.max_pages, len(self.jobs))
                url = f"{self.BASE_URL}?page={page_num}"
                logger.info(f"📄 Crawl trang {page_num}/{self.max_pages}")

                if not self.goto(url):
                    continue

                # Scroll để load hết job cards
                self.scroll_to_bottom()

                # Lấy HTML và parse
                html = self.get_html()
                page_jobs = self.parse_job_list(html)
                logger.info(f"   → Tìm thấy {len(page_jobs)} jobs trên trang")

                for job in page_jobs:
                    # RÚT GỌN CHỈ TEST 5 JOBS THEO YÊU CẦU ĐỂ TIẾT KIỆM THỜI GIAN
                    if len(self.jobs) >= 5:
                        break
                    if job.job_url:
                        self.extract_detail(job)
                    self.jobs.append(job)

                if len(self.jobs) >= 5:
                    break

        finally:
            self.stop()

        logger.info(f"✅ TopCV: Crawl xong {len(self.jobs)} jobs")
        return self.jobs

    # ==================== PARSE DANH SÁCH ====================

    def parse_job_list(self, html: str) -> list[JobModel]:
        """Parse trang danh sách → list JobModel"""
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        # Tìm tất cả job card trên trang
        job_cards = soup.select("div.job-item-search-result")

        if not job_cards:
            logger.warning("⚠️  Không tìm thấy job card — HTML structure có thể thay đổi")
            return []

        for card in job_cards:
            try:
                job = self.parse_single_job(card)
                if job.title:   # Chỉ thêm nếu có title
                    jobs.append(job)
            except Exception as e:
                logger.error(f"❌ Lỗi parse job card: {e}")
                continue

        return jobs

    # ==================== PARSE TỪNG JOB ====================

    def parse_single_job(self, card) -> JobModel:
        job = JobModel(source=self.SOURCE_NAME)

        # --- Title ---
        title_el = card.select_one("h3.title a span")
        if not title_el:
            title_el = card.select_one("h3.title a")
        job.title = title_el.get_text(strip=True) if title_el else ""

        # --- URL ---
        url_el = card.select_one("h3.title a")
        job.job_url = url_el.get("href", "") if url_el else ""
        if job.job_url and not job.job_url.startswith("http"):
            job.job_url = "https://www.topcv.vn" + job.job_url

        # --- Company ---
        company_el = card.select_one("a.company span.company-name")
        if not company_el:
            company_el = card.select_one("a.company")
        job.company = company_el.get_text(strip=True) if company_el else ""

        # ✅ FIX: Selector đúng từ HTML thực tế
        # --- Salary ---
        salary_el = card.select_one("div.box-salary-and-address__salary")
        job.salary = salary_el.get_text(strip=True) if salary_el else "Thỏa thuận"

        # --- Location ---
        location_el = card.select_one("div.box-salary-and-address__address")
        job.location = location_el.get_text(strip=True) if location_el else ""

        # --- Skills ---
        skill_els = card.select("a.item-tag")
        job.skills = [
            s.get_text(strip=True) for s in skill_els
            if s.get_text(strip=True) and self._is_valid_skill_tag(s.get_text(strip=True))
        ]

        return job

    def _is_valid_skill_tag(self, tag: str) -> bool:
        """Kiểm tra tag có phải skill thật không"""
        tag_lower = tag.lower()
        # Bỏ nếu quá dài (ngành nghề thường dài)
        if len(tag) > 30:
            return False
        # Bỏ nếu chứa từ khóa ngành/phúc lợi
        for pattern in NON_SKILL_PATTERNS:
            if pattern in tag_lower:
                return False
        return True

    # ==================== PARSE CHI TIẾT ====================

    def extract_detail(self, job: JobModel):
        """Extract chi tiết từ trang detail (Mô tả, Yêu cầu, Lĩnh vực, Hình thức)"""
        try:
            logger.info(f"   → Đang lấy chi tiết: {job.title}")
            self.goto(job.job_url)
            self.human_sleep(1, 2)
            html = self.get_html()
            soup = BeautifulSoup(html, "lxml")

            desc_parts, req_parts = [], []
            
            # Cấu trúc phổ biến: div có class = job-description__item
            sections = soup.select(".job-description__item")
            if not sections:
                # Cấu trúc cũ
                headers = soup.find_all("h3")
                for h3 in headers:
                    title = h3.get_text(strip=True).lower()
                    content_div = h3.find_next_sibling("div")
                    if content_div:
                        text = content_div.get_text(separator="\n", strip=True)
                        if "mô tả" in title or "quyền lợi" in title:
                            desc_parts.append(text)
                        elif "yêu cầu" in title or "kinh nghiệm" in title:
                            req_parts.append(text)
            else:
                for section in sections:
                    title_el = section.select_one("h3")
                    if not title_el: continue
                    title = title_el.get_text(strip=True).lower()
                    content_div = section.select_one(".job-description__item--content")
                    if content_div:
                        text = content_div.get_text(separator="\n", strip=True)
                        if "mô tả" in title or "quyền lợi" in title:
                            desc_parts.append(text)
                        elif "yêu cầu" in title or "kinh nghiệm" in title:
                            req_parts.append(text)

            if desc_parts:
                job.description = "\n---\n".join(desc_parts)
            if req_parts:
                job.requirements = "\n---\n".join(req_parts)
                
            # Thông tin chung: Hình thức làm việc, Kinh nghiệm, Học vấn
            # Thông tin chung: Hình thức làm việc, Kinh nghiệm, Học vấn
            containers = soup.select("[class*='item'], [class*='info'], [class*='group'], [class*='section']")
            for container in containers:
                title_el = container.select_one("[class*='title']")
                val_el = container.select_one("[class*='value'], [class*='content']")
                if title_el and val_el:
                    if title_el.parent == container and val_el.parent == container:
                        t = title_el.get_text(strip=True).lower()
                        v = val_el.get_text(separator=" ", strip=True)
                        if t and v and t != v.lower():
                            if "hình thức" in t:
                                job.job_type = v
                            elif "kinh nghiệm" in t:
                                job.experience_year = v
                            elif "học vấn" in t or "trình độ" in t or "bằng cấp" in t:
                                job.education = v
                            elif "cấp bậc" in t:
                                pass
                            elif "mức lương" in t:
                                job.salary = v
            
            # Fallback nếu TopCV dùng DOM ẩn hoặc khác cho Kinh nghiệm
            if not job.experience_year:
                import re
                el = soup.find(string=re.compile("Kinh nghiệm", re.IGNORECASE))
                if el:
                    parent = el.find_parent(["div", "span", "p"])
                    if parent:
                        sib = parent.find_next_sibling(["div", "span", "strong", "p"])
                        if sib:
                            job.experience_year = sib.get_text(strip=True)
            
            # Bổ sung kỹ năng (skills) nếu trang chi tiết có
            if job.skills is None:
                job.skills = []
            
            # Quét theo thẻ a (cách cũ)
            detail_skills = soup.select(".job-detail__skill--content a, .box-category .job-detail__box--content a, .job-detail__info--item-content a, .job-detail__category a")
            for s in detail_skills:
                t = s.get_text(strip=True)
                if t and self._is_valid_skill_tag(t) and t not in job.skills:
                    job.skills.append(t)

            # Quét theo thẻ theo label (DOM mới của TopCV)
            for label_text in ["Kỹ năng cần có", "Kỹ năng nên có", "Chuyên môn"]:
                label_el = soup.find(string=re.compile(label_text, re.IGNORECASE))
                if label_el:
                    parent = label_el.find_parent(["div", "h3"])
                    if parent:
                        container = parent.find_next_sibling("div") or parent.parent
                        if container:
                            for tag in container.select("span, a, div[class*='tag'], div[class*='content']"):
                                text = tag.get_text(strip=True)
                                if text and len(text) < 40 and label_text not in text:
                                    if text not in job.skills and self._is_valid_skill_tag(text):
                                        job.skills.append(text)

            # Ngành nghề / Lĩnh vực (Industry)
            # Dò tìm đúng label để tránh vướng phải Footer (Top Ngành Nghề)
            for label in soup.find_all(string=re.compile(r"Lĩnh vực|Ngành nghề|Chuyên môn", re.IGNORECASE)):
                text = label.get_text(strip=True).lower()
                # Bỏ qua các tiêu đề thuộc Footer hoặc Widget gợi ý
                if len(text) > 20 or "top" in text or "tìm" in text or "việc làm" in text or "khác" in text:
                    continue
                
                parent = label.find_parent(["div", "li", "h3", "td"])
                if parent:
                    # Các ngành nghề thường nằm kế bên
                    sib = parent.find_next_sibling(["div", "p", "a", "span", "ul"])
                    if sib:
                        job.industry = sib.get_text(separator=", ", strip=True)
                        break

            # Địa điểm làm việc chi tiết (Location)
            loc_label = soup.find(string=re.compile(r"Địa điểm làm việc", re.IGNORECASE))
            if loc_label:
                parent = loc_label.find_parent(["div", "h3", "h2"])
                if parent:
                    loc_container = parent.find_next_sibling("div")
                    if loc_container:
                        loc_text = loc_container.get_text(separator=", ", strip=True)
                        if loc_text and len(loc_text) > 5 and len(loc_text) < 500:
                            job.location = re.sub(r"^\-\s*", "", loc_text.strip())

            # Kỹ năng (Skills) deduplication fix (chỉ lọc những skill rác)
            if job.skills:
                unique_skills = []
                for s in job.skills:
                    if not any(s.lower() == us.lower() for us in unique_skills):
                        unique_skills.append(s)
                job.skills = unique_skills

            # ── Deadline (Hạn nộp hồ sơ) ─────────────────────────────
            # TopCV thường hiển thị Hạn nộp hồ sơ thay vì Ngày đăng
            date_selectors = [
                "time[datetime]",
                ".deadline span",
                "span[class*='date']",
                "span[class*='time']",
                ".job-detail__info--deadline",
                ".job-detail__info--updated-date",
                "div[class*='deadline']",
                ".box-info-job time",
                ".job-detail__box-general-right time",
            ]
            for sel in date_selectors:
                el = soup.select_one(sel)
                if el:
                    datetime_attr = el.get("datetime", "")
                    if datetime_attr:
                        pd = self._parse_posted_date(datetime_attr)
                    else:
                        pd = self._parse_posted_date(el.get_text(strip=True))
                    if pd:
                        job.deadline = pd
                        break

            # Fallback: tìm label "Hạn nộp hồ sơ" hoặc "Hết hạn"
            if not job.deadline:
                date_label = soup.find(string=re.compile(r"Hạn nộp|Deadline|Hết hạn", re.IGNORECASE))
                if date_label:
                    parent = date_label.find_parent(["div", "span", "li"])
                    if parent:
                        sib = parent.find_next_sibling(["div", "span", "strong", "p"])
                        if sib:
                            pd = self._parse_posted_date(sib.get_text(strip=True))
                            if pd:
                                job.deadline = pd
            
            # Ngày đăng để None vì TopCV không hiển thị
            job.posted_date = ""

            # Smart Parser: Đọc free-text để điền các ô còn trống
            self._fill_missing_fields_from_text(job)

        except Exception as e:
            logger.warning(f"   ⚠️ Lỗi extract detail: {e}")

    def _fill_missing_fields_from_text(self, job: JobModel):
        """
        Smart Parser: Đọc toàn bộ nội dung requirements/description 
        để vét nốt các thông tin bị thiếu (NULL).
        """
        full_text = f"{job.requirements or ''} {job.description or ''}".lower()
        if not full_text.strip(): return

        # 1. Experience Year
        if not job.experience_year or "kinh nghiệm" == job.experience_year.lower().strip():
            job.experience_year = ""  # Reset nếu bị lấy nhầm chữ "Kinh nghiệm"
            exp_match = re.search(r"(từ\s*\d+\s*đến\s*\d+\s*năm|\d+\+?\s*(?:năm|year)s?\s*(?:kinh nghiệm|experience)|ít nhất\s*\d+\s*năm)", full_text)
            if exp_match:
                job.experience_year = exp_match.group(1).title()
            elif re.search(r"(không yêu cầu kinh nghiệm|no experience required|fresher)", full_text):
                job.experience_year = "Không yêu cầu kinh nghiệm"

        # 2. Education
        if not job.education:
            if re.search(r"(bachelor|đại học|cử nhân)", full_text):
                job.education = "Đại học"
            elif re.search(r"(college|cao đẳng)", full_text):
                job.education = "Cao đẳng"
            elif re.search(r"(master|thạc sĩ)", full_text):
                job.education = "Thạc sĩ"

        # 3. Job Type
        if not job.job_type:
            if "full-time" in full_text or "toàn thời gian" in full_text:
                job.job_type = "Full-time"
            elif "part-time" in full_text or "bán thời gian" in full_text:
                job.job_type = "Part-time"
            elif "freelance" in full_text:
                job.job_type = "Freelance"

        # 4. Skills (vét từ text nếu trống)
        if not job.skills:
            job.skills = []
            common_skills = ["python", "java", "javascript", "react", "node.js", "c#", ".net", "sql", "aws", "docker", "php", "vue", "angular"]
            for skill in common_skills:
                if re.search(r"\b" + re.escape(skill) + r"\b", full_text):
                    job.skills.append(skill.upper() if len(skill) <= 3 else skill.title())
                    
        # 5. Industry
        if not job.industry:
            job.industry = "IT / Software"

        # 6. Salary (Tìm mức lương ẩn trong bài nếu lương bên ngoài là Thỏa thuận hoặc trống)
        if not job.salary or job.salary.lower() in ["thỏa thuận", "thoả thuận", "thương lượng", "negotiable"]:
            text_to_search = f"{job.title} {full_text}".lower()
            sal_patterns = [
                r"(\$[\d,\.]+\s*(?:-|to|đến|~)\s*\$[\d,\.]+)", # $1000 - $2000
                r"([\d,\.]+\s*(?:-|to|đến|~)\s*[\d,\.]+\s*(?:usd|triệu|tr|vnđ|vnd|k))", # 1000 - 2000 usd, 15 - 20 triệu
                r"((?:up to|lên đến|tới|maximum|max)\s*\$?\s*[\d,\.]+\s*(?:usd|triệu|tr|k)?)", # up to $2000
                r"((?:mức lương|thu nhập|salary|lương).{0,15}?\$?\s*[\d,\.]+\s*(?:usd|triệu|tr|k))", # salary: 2000 usd
            ]
            for p in sal_patterns:
                sal_match = re.search(p, text_to_search)
                if sal_match:
                    job.salary = sal_match.group(1).title()
                    break

    def _parse_posted_date(self, text: str) -> str:
        """Parse ngày đăng bài từ TopCV - hỗ trợ nhiều format."""
        if not text:
            return ""
        text = text.strip()
        text_lower = text.lower()

        # ISO 8601: 2026-05-18T... hoặc 2026-05-18
        m = re.match(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)

        # dd/mm/yyyy hoặc dd-mm-yyyy
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
        if m:
            try:
                return datetime(
                    int(m.group(3)), int(m.group(2)), int(m.group(1))
                ).strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Relative date
        now = datetime.now()
        num_match = re.search(r"(\d+)", text_lower)
        num = int(num_match.group(1)) if num_match else 1

        if any(w in text_lower for w in ["giờ", "hour", "hr"]):
            return (now - timedelta(hours=num)).strftime("%Y-%m-%d")
        elif any(w in text_lower for w in ["ngày", "day"]):
            return (now - timedelta(days=num)).strftime("%Y-%m-%d")
        elif any(w in text_lower for w in ["tuần", "week"]):
            return (now - timedelta(weeks=num)).strftime("%Y-%m-%d")
        elif any(w in text_lower for w in ["tháng", "month"]):
            return (now - timedelta(days=num * 30)).strftime("%Y-%m-%d")
        elif any(w in text_lower for w in ["hôm nay", "today", "just now", "vừa"]):
            return now.strftime("%Y-%m-%d")
        elif any(w in text_lower for w in ["hôm qua", "yesterday"]):
            return (now - timedelta(days=1)).strftime("%Y-%m-%d")

        return ""

    def debug_save_html(self, page_num: int = 1):
        """
        Lưu HTML thực tế ra file để inspect selector.
        Chạy 1 lần để xem HTML structure thật của TopCV.
        """
        self.start()
        try:
            url = f"{self.BASE_URL}?page={page_num}"
            self.goto(url)
            self.scroll_to_bottom()
            html = self.get_html()

            with open("debug_topcv.html", "w", encoding="utf-8") as f:
                f.write(html)

            print("✅ Đã lưu: debug_topcv.html")
            print(f"   File size: {len(html):,} bytes")
        finally:
            self.stop()