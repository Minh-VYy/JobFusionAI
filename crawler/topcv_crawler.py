# crawler/topcv_crawler.py
from bs4 import BeautifulSoup
from crawler.base_crawler import BaseCrawler, logger
from models.job_model import JobModel

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

    def crawl(self) -> list[JobModel]:
        """Entry point — crawl toàn bộ"""
        self.start()
        try:
            for page_num in range(1, self.max_pages + 1):
                url = f"{self.BASE_URL}?page={page_num}"
                logger.info(f"📄 Crawl trang {page_num}/{self.max_pages}")

                if not self.goto(url):
                    continue

                # Scroll để load hết job cards
                self.scroll_to_bottom()

                # Lấy HTML và parse
                html = self.get_html()
                page_jobs = self.parse_job_list(html)
                logger.info(f"   → Tìm thấy {len(page_jobs)} jobs")

                self.jobs.extend(page_jobs)

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