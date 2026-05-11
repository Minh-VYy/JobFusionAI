# crawler/itviec_crawler.py
from bs4 import BeautifulSoup
from crawler.base_crawler import BaseCrawler, logger
from models.job_model import JobModel


class ITviecCrawler(BaseCrawler):
    """
    Crawler cho ITviec.com
    URL: https://itviec.com/it-jobs?page=1
    """

    BASE_URL = "https://itviec.com/it-jobs"
    SOURCE_NAME = "itviec"

    def __init__(self, max_pages: int = 3, headless: bool = True):
        super().__init__(headless=headless)
        self.max_pages = max_pages
        self.jobs = []

    def crawl(self) -> list[JobModel]:
        self.start()
        try:
            for page_num in range(1, self.max_pages + 1):
                logger.info(f"📄 ITviec - Crawl trang {page_num}/{self.max_pages}")
                url = f"{self.BASE_URL}?page={page_num}"

                if not self.goto(url, wait=3):
                    continue

                # Chờ job-card xuất hiện
                try:
                    self.page.wait_for_selector(
                        "div[class*='job-card']",
                        timeout=10000
                    )
                except Exception:
                    logger.warning("⚠️  Timeout chờ ITviec — tiếp tục...")

                self.scroll_to_bottom()
                self.random_sleep(1, 2)

                html = self.get_html()
                page_jobs = self.parse_job_list(html)
                logger.info(f"   → Tìm thấy {len(page_jobs)} jobs")
                self.jobs.extend(page_jobs)

        finally:
            self.stop()

        logger.info(f"✅ ITviec: Crawl xong {len(self.jobs)} jobs")
        return self.jobs

    def parse_job_list(self, html: str) -> list[JobModel]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        # ✅ Selector đúng từ debug HTML
        job_cards = soup.select("div.job-card")

        if not job_cards:
            logger.warning("⚠️  ITviec: Không tìm thấy job card")
            return []

        logger.info(f"   → Parse {len(job_cards)} cards...")

        for card in job_cards:
            try:
                job = self.parse_single_job(card)
                if job.title:
                    jobs.append(job)
            except Exception as e:
                logger.error(f"❌ Lỗi parse ITviec: {e}")
                continue

        return jobs

    def parse_single_job(self, card) -> JobModel:
        job = JobModel(source=self.SOURCE_NAME)

        # --- Title ---
        # <h3 class="imt-3 text-break" ...>AI Solutions Architect</h3>
        title_el = card.select_one("h3")
        job.title = title_el.get_text(strip=True) if title_el else ""

        # --- URL ---
        # data-search--job-selection-job-url-value="/it-jobs/..."
        job_slug = card.get("data-search--job-selection-job-slug-value", "")
        if job_slug:
            job.job_url = f"https://itviec.com/it-jobs/{job_slug}"
        else:
            # fallback: tìm thẻ a trong card
            a_el = card.select_one("a[href*='/it-jobs/']")
            job.job_url = f"https://itviec.com{a_el['href']}" if a_el else ""

        # --- Company ---
        # <a href="/companies/kms-technology">...</a>
        company_el = card.select_one("a[href*='/companies/']")
        if company_el:
            # Lấy từ title attribute hoặc text
            job.company = (
                company_el.get("data-bs-original-title", "") or
                company_el.get_text(strip=True)
            )

        # --- Salary ---
        # ITviec thường ẩn salary → tìm div chứa "$" hoặc "triệu"
        salary_el = (
            card.select_one("div[class*='salary']") or
            card.select_one("span[class*='salary']") or
            card.select_one("div.sign-in-view-salary")
        )
        if salary_el:
            job.salary = salary_el.get_text(strip=True)
        else:
            # Tìm text có chứa "$" hoặc "triệu" trong card
            for el in card.find_all(["div", "span", "p"]):
                text = el.get_text(strip=True)
                if "$" in text or "triệu" in text.lower() or "USD" in text:
                    job.salary = text
                    break
            else:
                job.salary = "Thỏa thuận"

        # --- Location ---
        # Tìm div/span chứa tên thành phố
        for el in card.find_all(["div", "span", "p"]):
            text = el.get_text(strip=True)
            if any(city in text for city in [
                "Hà Nội", "Ho Chi Minh", "Hồ Chí Minh",
                "Da Nang", "Đà Nẵng", "Ha Noi", "Remote"
            ]):
                job.location = text
                break

        # --- Skills / Tags ---
        # ITviec dùng badge/tag cho tech stack
        skill_els = card.select(
            "a[class*='tag'], span[class*='tag'], "
            "a[class*='badge'], span[class*='badge']"
        )
        job.skills = [
            s.get_text(strip=True) for s in skill_els
            if s.get_text(strip=True)
        ]

        return job