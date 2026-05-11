# crawler/vietnamworks_crawler.py
from bs4 import BeautifulSoup
from crawler.base_crawler import BaseCrawler, logger
from models.job_model import JobModel


class VietnamWorksCrawler(BaseCrawler):
    """
    Crawler cho VietnamWorks.com
    Selector: div.new-job-card
    """

    SOURCE_NAME = "vietnamworks"

    def __init__(self, max_pages: int = 3, headless: bool = True):
        super().__init__(headless=headless)
        self.max_pages = max_pages
        self.jobs = []

    def crawl(self) -> list[JobModel]:
        self.start()
        try:
            for page_num in range(1, self.max_pages + 1):
                logger.info(f"📄 VietnamWorks - Crawl trang {page_num}/{self.max_pages}")

                # ✅ Thử URL dạng mới (ngành IT g=21)
                url = f"https://www.vietnamworks.com/viec-lam?g=21&ignoreLocation=true&page={page_num}"

                try:
                    logger.info(f"🌐 Đang truy cập: {url}")
                    self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"⚠️  Lỗi goto: {e}")

                self.random_sleep(4, 5)

                # Chờ job card — thử nhiều selector
                job_appeared = False
                for selector in ["div.new-job-card", "div[class*='job-card']", "div[class*='card']"]:
                    try:
                        self.page.wait_for_selector(selector, timeout=8000)
                        logger.info(f"✅ Tìm thấy selector: {selector}")
                        job_appeared = True
                        break
                    except Exception:
                        continue

                if not job_appeared:
                    logger.warning("⚠️  Không thấy job card — lưu HTML để debug")
                    html = self.get_html()
                    with open(f"debug_vw_page{page_num}.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    logger.info(f"   → Đã lưu debug_vw_page{page_num}.html")
                    continue

                self.scroll_to_bottom()
                self.random_sleep(2, 3)

                html = self.get_html()
                page_jobs = self.parse_job_list(html)
                logger.info(f"   → Tìm thấy {len(page_jobs)} jobs")
                self.jobs.extend(page_jobs)

        finally:
            self.stop()

        logger.info(f"✅ VietnamWorks: Crawl xong {len(self.jobs)} jobs")
        return self.jobs

    def parse_job_list(self, html: str) -> list[JobModel]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        # ✅ Selector đúng từ debug
        job_cards = soup.select("div.new-job-card")

        if not job_cards:
            logger.warning("⚠️  VietnamWorks: Không tìm thấy job card")
            return []

        logger.info(f"   → Parse {len(job_cards)} cards...")

        for card in job_cards:
            try:
                job = self.parse_single_job(card)
                if job.title:
                    jobs.append(job)
            except Exception as e:
                logger.error(f"❌ Lỗi parse VietnamWorks: {e}")
                continue

        return jobs

    def parse_single_job(self, card) -> JobModel:
        job = JobModel(source=self.SOURCE_NAME)

        # --- Title ---
        # <h2><a ...>Tên Job</a></h2>
        title_el = card.select_one("h2 a")
        job.title = title_el.get_text(strip=True) if title_el else ""

        # --- URL ---
        if title_el:
            href = title_el.get("href", "")
            job.job_url = (
                href if href.startswith("http")
                else f"https://www.vietnamworks.com{href}"
            )

        # --- Company ---
        # Tìm thẻ a trỏ tới trang company
        company_el = card.select_one("a[href*='company'], a[href*='nha-tuyen-dung']")
        if not company_el:
            # Fallback: thẻ h3 hoặc span gần title
            company_el = card.select_one("h3")
        job.company = company_el.get_text(strip=True) if company_el else ""

        # --- Salary ---
        # VietnamWorks hiển thị salary dạng text thuần
        salary_el = card.select_one(
            "div[class*='salary'], span[class*='salary'], "
            "div[class*='Salary'], span[class*='Salary']"
        )
        if salary_el:
            job.salary = salary_el.get_text(strip=True)
        else:
            # Tìm text chứa "triệu", "$", "USD", "VND"
            for el in card.find_all(["span", "div", "p"]):
                text = el.get_text(strip=True)
                if any(kw in text for kw in [
                    "triệu", "Triệu", "$", "USD",
                    "VND", "Thỏa thuận", "thoả thuận"
                ]):
                    # Bỏ qua nếu text quá dài (không phải salary)
                    if len(text) < 50:
                        job.salary = text
                        break
            else:
                job.salary = "Thỏa thuận"

        # --- Location ---
        for el in card.find_all(["span", "div", "p"]):
            text = el.get_text(strip=True)
            if any(city in text for city in [
                "Hà Nội", "Hồ Chí Minh", "Đà Nẵng",
                "Cần Thơ", "Bình Dương", "Đồng Nai",
                "Hải Phòng", "Remote", "Toàn quốc"
            ]):
                if len(text) < 80:  # Tránh lấy đoạn văn dài
                    job.location = text
                    break

        # --- Skills ---
        skill_els = card.select(
            "a[class*='tag'], span[class*='tag'], "
            "a[class*='skill'], span[class*='skill']"
        )
        job.skills = [
            s.get_text(strip=True) for s in skill_els
            if s.get_text(strip=True)
        ]

        return job