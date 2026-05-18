# crawler/itviec_crawler.py
from typing import Optional
from bs4 import BeautifulSoup
from crawler.base_crawler import BaseCrawler, logger
from models.job_model import JobModel
import re
from datetime import datetime, timedelta


class ITviecCrawler(BaseCrawler):
    """
    Crawler ITviec V4 - Fix dual scroll panel
    Đăng nhập sẵn → UI 2 cột → scroll panel trái
    """
    BASE_URL = "https://itviec.com/it-jobs"
    SOURCE_NAME = "itviec"

    def __init__(self, max_pages: int = 1, headless: bool = True):
        super().__init__(headless=headless)
        self.max_pages = max_pages
        self.jobs = []

    # ============================================================
    # CRAWL CHÍNH
    # ============================================================

    def crawl(self) -> list[JobModel]:
        self.start()
        try:
            for page_num in range(1, self.max_pages + 1):
                logger.info(f"📄 ITviec - Trang {page_num}/{self.max_pages}")
                url = f"{self.BASE_URL}?page={page_num}"
                if not self.goto(url):
                    continue

                self.human_sleep(3, 5)

                # Chờ danh sách job load
                try:
                    self.page.wait_for_selector(".job-card", timeout=20000)
                    logger.info("   ✅ Job list loaded")
                except Exception:
                    logger.warning("   ⚠️ Timeout đợi .job-card")
                    continue

                # ✅ FIX: Scroll panel trái thay vì window
                self._scroll_job_list_panel()

                # Lấy các thẻ job card
                cards = self.page.locator(".job-card")
                count = min(cards.count(), 5) # CHỈ LẤY 5 DỮ LIỆU ĐỂ TEST
                logger.info(f"   👉 Sẽ test click {count} jobs từ list...")

                if count == 0:
                    logger.warning("   ⚠️ Không tìm thấy job card nào")
                    continue

                # Click từng card và extract từ panel phải (Split-View)
                for i in range(count):
                    try:
                        logger.info(f"--- [JOB {i+1}/{count}] ---")
                        card = cards.nth(i)

                        # KHÔNG lấy href từ card trái nữa vì dễ bị nhầm thẻ skill tag.
                        # Ta sẽ trích xuất url chính xác ở bên trong right panel.
                        detail_url = ""

                        # 2. Click vào card để load data bên panel phải
                        card.click()
                        self.human_sleep(2, 3)

                        # 3. Scroll panel phải để đảm bảo load hết thông tin
                        self._scroll_right_panel()

                        # 4. Extract data
                        job = JobModel(
                            source=self.SOURCE_NAME,
                            job_url=detail_url
                        )
                        self.extract_detail(job)

                        if self._is_valid_job(job):
                            logger.info(f"   ✅ {job.title} | {job.company}")
                            self.jobs.append(job)
                        else:
                            logger.warning(
                                f"   ⚠️ Validation fail: "
                                f"title={bool(job.title)} "
                                f"company={bool(job.company)} "
                                f"desc_len={len(job.description)}"
                            )

                    except Exception as e:
                        logger.warning(f"   ❌ Error at job {i+1}: {e}")
                        continue

                # Quay lại listing nếu còn trang
                if page_num < self.max_pages:
                    self.goto(url)
                    self.human_sleep(2, 3)

        finally:
            self.stop()

        logger.info(f"✅ ITviec: {len(self.jobs)} jobs")
        return self.jobs

    # ============================================================
    # FIX CORE: SCROLL PANEL TRÁI
    # ============================================================

    def _scroll_job_list_panel(self):
        """
        ITviec dùng layout 2 cột:
        - Panel trái (.card-jobs-list) có overflow-y: scroll riêng
        - Phải scroll PANEL này, không phải window
        """
        logger.info("   🔄 Scrolling job list panel...")

        # Các selector có thể chứa danh sách job
        panel_selectors = [
            ".card-jobs-list",
            "div[class*='jobs-list']",
            "div[class*='job-list']",
            ".search-results",
            "div[class*='search-result']",
        ]

        panel_found = False
        for selector in panel_selectors:
            try:
                panel = self.page.locator(selector).first
                if panel.count() > 0:
                    logger.info(f"   ✅ Panel found: {selector}")
                    panel_found = True

                    # Scroll panel xuống nhiều lần
                    for i in range(5):
                        panel.evaluate("""
                            el => {
                                el.scrollTop += 800;
                            }
                        """)
                        self.human_sleep(1.5, 2.5)

                        # Đếm jobs sau mỗi scroll
                        count = self.page.locator(".job-card").count()
                        logger.info(f"      Scroll {i+1}: {count} cards")

                    break
            except Exception:
                continue

        if not panel_found:
            logger.warning("   ⚠️ Không tìm thấy scroll panel — fallback window scroll")
            # Fallback: scroll window
            for i in range(5):
                self.page.evaluate("window.scrollBy(0, 800)")
                self.human_sleep(1.5, 2.5)
                count = self.page.locator(".job-card").count()
                logger.info(f"      Window scroll {i+1}: {count} cards")

    def _scroll_right_panel(self):
        """Scroll thanh cuộn thứ 2 (panel chi tiết công việc bên phải)"""
        logger.info("   🔄 Scrolling right panel (Job Details)...")
        panel_selectors = [
            ".preview-job-content",     # Đây là thẻ chứa scrollbar thực sự
            ".i-scrollbar",
            ".preview-job-wrapper",
            "div[class*='preview-job']",
            ".job-details",
            ".jd-page__container",
            "div[class*='job-detail']"
        ]

        panel_found = False
        for selector in panel_selectors:
            try:
                panel = self.page.locator(selector).first
                if panel.count() > 0:
                    panel_found = True
                    # Cuộn 5 lần, mỗi lần 800px với hiệu ứng smooth để người dùng có thể thấy
                    for _ in range(5):
                        try:
                            panel.evaluate("el => el.scrollBy({ top: 800, left: 0, behavior: 'smooth' })")
                        except:
                            self.page.evaluate("window.scrollBy({ top: 800, left: 0, behavior: 'smooth' })")
                        self.human_sleep(1.2, 1.8)
                    break
            except Exception:
                continue

        if not panel_found:
            logger.warning("   ⚠️ Không tìm thấy thanh cuộn bên phải!")

    # ============================================================
    # COLLECT JOB URLS
    # ============================================================

    def _collect_job_urls(self) -> list[str]:
        """Lấy tất cả job URLs từ listing page"""
        job_links = []

        try:
            cards = self.page.locator(".job-card")
            count = cards.count()
            logger.info(f"   → {count} cards tìm thấy")

            for i in range(count):
                card = cards.nth(i)
                try:
                    # Thử nhiều selector để lấy link
                    link_el = None
                    for sel in ["h3 a", "a[href*='/it-jobs/']", "a.job-title"]:
                        try:
                            link_el = card.locator(sel).first
                            href = link_el.get_attribute("href", timeout=2000)
                            if href and "/it-jobs/" in href:
                                break
                            href = None
                        except Exception:
                            continue

                    if href:
                        full_url = (
                            f"https://itviec.com{href}"
                            if href.startswith("/")
                            else href
                        )
                        # Bỏ query params thừa
                        full_url = full_url.split("?")[0]
                        if full_url not in job_links:
                            job_links.append(full_url)

                except Exception:
                    continue

        except Exception as e:
            logger.error(f"   ❌ Collect URLs error: {e}")

        return job_links

    # ============================================================
    # EXTRACT DETAIL PAGE
    # ============================================================

    def extract_detail(self, job: JobModel):
        """Extract data từ right panel (Split-View)"""
        try:
            # Lấy HTML của riêng right panel để tránh nhầm với list bên trái
            html = ""
            for sel in [".preview-job-wrapper", "div[class*='preview-job']", ".job-details", ".jd-page__container", "div[class*='job-detail']"]:
                try:
                    panel = self.page.locator(sel).first
                    if panel.count() > 0:
                        html = panel.inner_html()
                        break
                except Exception:
                    pass

            if not html:
                logger.warning("   ⚠️ Không tìm thấy right panel HTML, fallback page.content()")
                html = self.page.content()

            soup = BeautifulSoup(html, "lxml")

            # ── Title ──────────────────────────────────────────
            for sel in [
                "h2.text-break",
                "h2.text-it-black.text-hover-red",
                "h2.job-details__title",
                "h1.job-details__title",
                ".job-details__header h2",
                ".job-details__header h1",
                "h2",
                "h1"
            ]:
                title_el = soup.select_one(sel)
                if title_el:
                    t = title_el.get_text(strip=True)
                    if "jobs in" not in t.lower() and len(t) > 3:
                        job.title = t
                        break

            # ── Job URL ────────────────────────────────────────
            for sel in [
                ".preview-job-header a[href*='/it-jobs/']",
                "a[data-controller='utm-tracking'][href*='/it-jobs/']"
            ]:
                el = soup.select_one(sel)
                if el:
                    href = el.get("href")
                    if href:
                        job.job_url = f"https://itviec.com{href.split('?')[0]}"
                        break

            # ── Company ────────────────────────────────────────
            for sel in [
                ".preview-job-header a[href*='/companies/']:not(.logo-employer-preview)",
                ".job-details__sub-title a",
                ".employer-name a",
                ".job-details__company-name a",
                "a[href*='/companies/']",
            ]:
                el = soup.select_one(sel)
                if el:
                    job.company = el.get_text(strip=True)
                    break

            # ── Salary ─────────────────────────────────────────
            for sel in [
                ".salary span.fw-500",
                ".salary",
                ".job-details__salary",
                ".salary-content",
                "div[class*='salary']",
            ]:
                el = soup.select_one(sel)
                if el:
                    salary_text = el.get_text(strip=True)
                    # Nếu salary bị ẩn (vd: You'll love it) -> Đặt là Thỏa thuận
                    if "love" in salary_text.lower() or "thỏa thuận" in salary_text.lower():
                        job.salary = "Thỏa thuận"
                    else:
                        job.salary = salary_text
                    break

            # ── Parse salary_min / salary_max ──────────────────
            job.salary_min, job.salary_max = self._parse_salary(job.salary)

            # ── Location ───────────────────────────────────────
            for sel in [
                ".preview-job-overview svg[href*='map-pin'] ~ span",
                ".preview-job-overview svg use[href*='map-pin']",
                ".preview-job-overview span.text-rich-grey",
                ".job-details__address",
                ".address",
                "div[class*='location']",
                "span[class*='location']",
            ]:
                el = soup.select_one(sel)
                if el and el.name != "use":
                    job.location = el.get_text(strip=True)
                    break
                elif el and el.name == "use":
                    # Fallback for parent handling
                    parent = el.find_parent("div")
                    if parent:
                        span = parent.find("span")
                        if span:
                            job.location = span.get_text(strip=True)
                            break

            # ── Skills/Tags ────────────────────────────────────
            skill_els = soup.select(
                ".job-details__tag-list a, "
                "a[class*='tag'], "
                "span[class*='tag']"
            )
            job.skills = [
                s.get_text(strip=True) for s in skill_els
                if s.get_text(strip=True)
            ]

            # ── Job Type ───────────────────────────────────────
            for item in soup.select(".preview-header-item, .job-details__overview-item"):
                text = item.get_text(strip=True)
                if text in ["At office", "Remote", "Hybrid"] or "làm việc" in text.lower() or "remote" in text.lower():
                    job.job_type = text
                    break

            # Fallback job_type: tìm trong overview list
            if not job.job_type:
                for el in soup.select("li, .overview-item, .job-meta li"):
                    text = el.get_text(strip=True)
                    for keyword in ["Full-time", "Part-time", "Contract", "Freelance", "Internship"]:
                        if keyword.lower() in text.lower():
                            job.job_type = keyword
                            break
                    if job.job_type:
                        break

            # ── Experience Year ────────────────────────────────
            # Ưu tiên: tìm trong các item overview header (không phải body mô tả)
            # ITviec render overview dạng: icon + label text trong .preview-header-item
            EXP_SELECTORS = [
                ".preview-header-item",
                ".job-details__overview-item",
                ".job-overview li",
                ".itr-list li",
            ]
            EXP_PATTERN = re.compile(
                r"^(\d+[\+\-–]?\s*\d*\s*(năm|year|yrs?)|"
                r"(không yêu cầu|no experience required|fresher|entry.?level|"
                r"dưới \d+|less than \d+)).*$",
                re.IGNORECASE
            )
            for sel in EXP_SELECTORS:
                for el in soup.select(sel):
                    text = el.get_text(strip=True)
                    if EXP_PATTERN.match(text):
                        job.experience_year = text
                        break
                if job.experience_year:
                    break

            # Fallback: tìm thẻ chứa label "Years of Experience" rồi lấy giá trị kề bên
            if not job.experience_year:
                label = soup.find(
                    string=re.compile(r"Years?\s+of\s+Experience|Kinh nghiệm", re.IGNORECASE)
                )
                if label:
                    container = label.find_parent(["div", "li", "span", "td"])
                    if container:
                        # Tìm sibling hoặc con chứa số năm
                        value_el = container.find_next_sibling(["div", "span", "td", "p"])
                        if value_el:
                            val = value_el.get_text(strip=True)
                            # Chỉ lấy nếu có số năm, không phải câu dài
                            if re.search(r"\d+\s*(năm|year|yrs?)", val, re.IGNORECASE) and len(val) < 60:
                                job.experience_year = val

            # ── Education ──────────────────────────────────────
            # Tìm label "Education" trong overview, lấy giá trị kề bên
            edu_label = soup.find(
                string=re.compile(r"^(Education|Học vấn|Trình độ học vấn)$", re.IGNORECASE)
            )
            if edu_label:
                container = edu_label.find_parent(["div", "li", "span", "td"])
                if container:
                    value_el = container.find_next_sibling(["div", "span", "td", "p"])
                    if value_el:
                        val = value_el.get_text(strip=True)
                        # Chỉ lấy nếu là giá trị ngắn gọn (nhãn, không phải câu mô tả)
                        if len(val) < 80:
                            job.education = val

            # Fallback: tìm trong overview items với keyword học vấn, giới hạn độ dài
            EDU_KEYWORDS = [
                "Đại học", "Cao đẳng", "Trung cấp",
                "Bachelor", "Master", "PhD", "College", "University",
                "Không yêu cầu bằng cấp"
            ]
            if not job.education:
                for sel in [".preview-header-item", ".job-details__overview-item"]:
                    for el in soup.select(sel):
                        text = el.get_text(strip=True)
                        if any(kw.lower() in text.lower() for kw in EDU_KEYWORDS) and len(text) < 80:
                            job.education = text
                            break
                    if job.education:
                        break

            # ── Industry (Job Domain) ──────────────────────────
            domain_label = soup.find(
                string=re.compile(r"Job Domain:|Lĩnh vực:|Industry:", re.IGNORECASE)
            )
            if domain_label:
                parent = domain_label.find_parent(["div", "li", "span"])
                if parent:
                    sibling = parent.find_next_sibling(["div", "span", "p"])
                    if sibling:
                        job.industry = sibling.get_text(strip=True)
                    else:
                        # Đôi khi nằm cùng thẻ, bỏ phần label đi
                        raw = parent.get_text(strip=True)
                        job.industry = re.sub(
                            r"(Job Domain:|Lĩnh vực:|Industry:)\s*", "", raw, flags=re.IGNORECASE
                        ).strip()

            # ── Description + Requirements ─────────────────────
            desc_parts, req_parts = [], []

            sections = soup.select(".job-description, .job-experiences, .job-why-love-working, h2, h3")

            for section in sections:
                if section.name in ["h2", "h3"]:
                    header = section.get_text(strip=True).lower()
                    container = section.find_next_sibling(["div", "ul", "p"])
                else:
                    # div wrapper (like preview-job split view)
                    header_el = section.find(["h2", "h3"])
                    header = header_el.get_text(strip=True).lower() if header_el else ""
                    container = section.find("div", class_="paragraph") or section.find("ul")

                if not container:
                    continue

                content = container.get_text(separator="\n", strip=True)

                if any(k in header for k in [
                    "description", "mô tả", "trách nhiệm",
                    "phúc lợi", "benefit", "reason", "why you'll love"
                ]):
                    if content not in desc_parts:
                        desc_parts.append(content)
                elif any(k in header for k in [
                    "skills", "yêu cầu", "kỹ năng",
                    "experience", "requirement", "your skills"
                ]):
                    if content not in req_parts:
                        req_parts.append(content)

            if desc_parts:
                job.description = "\n---\n".join(desc_parts)
            if req_parts:
                job.requirements = "\n---\n".join(req_parts)

            # Fallback description
            if not job.description:
                for sel in [
                    ".job-details__paragraph",
                    ".job-details__content",
                    "div[class*='description']",
                    ".paragraph"
                ]:
                    els = soup.select(sel)
                    if els:
                        job.description = els[0].get_text(
                            separator="\n", strip=True
                        )
                        if len(els) > 1:
                            job.requirements = els[1].get_text(
                                separator="\n", strip=True
                            )
                        break

            # ── Deadline ───────────────────────────────────────
            deadline_label = soup.find(
                string=re.compile(r"Deadline|Hạn nộp|Application deadline", re.IGNORECASE)
            )
            if deadline_label:
                parent = deadline_label.find_parent(["div", "li", "span"])
                if parent:
                    sibling = parent.find_next_sibling(["div", "span", "p"])
                    if sibling:
                        job.deadline = self._parse_deadline(sibling.get_text(strip=True))

            # Fallback deadline: tìm bằng selector cụ thể
            if not job.deadline:
                for sel in [
                    ".job-details__deadline",
                    "span[class*='deadline']",
                    "div[class*='deadline']",
                ]:
                    el = soup.select_one(sel)
                    if el:
                        job.deadline = self._parse_deadline(el.get_text(strip=True))
                        break

            # ── Phone ──────────────────────────────────────────
            # ITviec thường ẩn phone nhưng vẫn thử extract nếu có
            phone_label = soup.find(
                string=re.compile(r"Phone|Điện thoại|Hotline|Tel:", re.IGNORECASE)
            )
            if phone_label:
                parent = phone_label.find_parent(["div", "li", "span"])
                if parent:
                    sibling = parent.find_next_sibling(["div", "span", "p"])
                    if sibling:
                        raw_phone = sibling.get_text(strip=True)
                        job.phone = self._extract_phone(raw_phone)

            # Fallback phone: tìm pattern số điện thoại VN trong toàn bộ HTML
            if not job.phone:
                all_text = soup.get_text(" ")
                phone_match = re.search(
                    r"(?<!\d)(0[3-9]\d{8}|\+84[3-9]\d{8}|84[3-9]\d{8})(?!\d)",
                    all_text
                )
                if phone_match:
                    job.phone = phone_match.group(1)

            # ── Posted Date ────────────────────────────────────
            # ITviec hiển thị dạng: "Posted 2 days ago", "Đăng 3 ngày trước"
            # Hoặc ngày cụ thể: "18/05/2026"
            date_selectors = [
                ".preview-job-header time",
                "time[datetime]",
                ".preview-job-overview time",
                ".itr-created-at",
                ".job-details__posted-date time",
                ".job-details__posted-date span",
                ".posted-date time",
                ".posted-date span",
                "span[class*='posted']",
                "span[class*='date']",
                "div[class*='posted-date']",
                ".created-at",
            ]
            for sel in date_selectors:
                el = soup.select_one(sel)
                if el:
                    # Ưu tiên lấy attribute datetime (ISO format chính xác nhất)
                    datetime_attr = el.get("datetime", "")
                    if datetime_attr:
                        job.posted_date = self._parse_iso_or_relative(datetime_attr)
                    else:
                        raw_text = el.get_text(strip=True)
                        if raw_text:
                            job.posted_date = self._parse_relative_date(raw_text)
                    if job.posted_date:
                        break

            # Fallback đọc text thủ công từ các thẻ con trong header/overview
            if not job.posted_date:
                for sel in [".preview-job-overview", ".job-details__header", ".preview-job-wrapper", ".job-details"]:
                    parent_el = soup.select_one(sel)
                    if parent_el:
                        for text_el in parent_el.find_all(["span", "div", "p", "time"]):
                            txt = text_el.get_text(strip=True).lower()
                            if "posted" in txt or "đăng" in txt or "ago" in txt or "trước" in txt or "hôm nay" in txt:
                                # Tránh các dòng quá dài không phải date
                                if len(txt) < 40 and not "việc làm" in txt and not "job" in txt:
                                    parsed = self._parse_relative_date(txt)
                                    if parsed:
                                        job.posted_date = parsed
                                        break
                        if job.posted_date:
                            break

            # Bổ sung thuật toán đọc free-text (cách dài hạn nhưng áp dụng ngay)
            self._fill_missing_fields_from_text(job)

        except Exception as e:
            logger.warning(f"   ⚠️ Extract error: {e}")

    def _fill_missing_fields_from_text(self, job: JobModel):
        """
        Smart Parser: Đọc toàn bộ nội dung requirements/description 
        để vét nốt các thông tin bị thiếu (NULL).
        """
        full_text = f"{job.requirements or ''} {job.description or ''}".lower()
        if not full_text.strip(): return

        # 1. Experience Year
        if not job.experience_year:
            # Bắt mẫu: "từ 2 đến 3 năm kinh nghiệm", "5+ years of experience", "ít nhất 1 năm"
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

    # ============================================================
    # VALIDATION
    # ============================================================

    def _is_valid_job(self, job: JobModel) -> bool:
        if not job.title or len(job.title) < 5:
            return False
        if "jobs in" in job.title.lower():
            return False
        if not job.company or len(job.company) < 2:
            return False
        if len(job.description) < 50:  # Giảm từ 100 → 50
            return False
        return True

    # ============================================================
    # HELPERS
    # ============================================================

    def human_sleep(self, min_s=1, max_s=3):
        import time, random
        time.sleep(random.uniform(min_s, max_s))

    def _parse_salary(self, salary_text: str) -> tuple[Optional[float], Optional[float]]:
        """
        Parse salary_min và salary_max từ chuỗi lương thô.
        Ví dụ:
          "15 - 25 triệu"       → (15.0, 25.0)
          "1,900 - 2,300 USD"   → (47.5, 57.5)  [triệu VND, tỷ giá 25,000]
          "800 - 1,000 USD"     → (20.0, 25.0)
          "Thỏa thuận"          → (None, None)
        """
        if not salary_text:
            return None, None

        text = salary_text.lower().strip()

        # Lương ẩn / thỏa thuận → trả None
        negotiable_keywords = [
            "thỏa thuận", "thương lượng", "negotiable",
            "love", "competitive", "attractive"
        ]
        if any(kw in text for kw in negotiable_keywords):
            return None, None

        is_usd = "$" in salary_text or "usd" in text or "dollar" in text

        # Regex bắt số nguyên có thể có dấu phẩy hàng nghìn: 1,900 / 2,300 / 25
        # Phải bắt toàn bộ "1,900" như một token, không tách thành "1" và "900"
        raw_numbers = re.findall(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?", text)
        if not raw_numbers:
            return None, None

        def to_float(s: str) -> float:
            # "1,900" → 1900.0  |  "25" → 25.0  |  "1.5" → 1.5
            return float(s.replace(",", ""))

        nums = [to_float(n) for n in raw_numbers]

        if is_usd:
            # Quy đổi USD → triệu VND (1 USD = 25,000 VND = 0.025 triệu)
            nums = [round(n * 0.025, 2) for n in nums]
        else:
            # VND: nếu số > 1000 thì đang là đơn vị nghìn VND → đổi sang triệu
            nums = [round(n / 1000, 2) if n >= 1000 else n for n in nums]

        if len(nums) == 1:
            return nums[0], nums[0]
        return min(nums[0], nums[1]), max(nums[0], nums[1])

    def _parse_deadline(self, text: str) -> Optional[str]:
        """
        Parse hạn nộp hồ sơ về định dạng YYYY-MM-DD.
        Hỗ trợ: "31/12/2025", "31-12-2025", "December 31, 2025"
        """
        if not text:
            return None
        text = text.strip()

        # dd/mm/yyyy hoặc dd-mm-yyyy
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
        if m:
            try:
                return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).strftime("%Y-%m-%d")
            except ValueError:
                pass

        # yyyy-mm-dd (ISO)
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            return m.group(0)

        # "Month DD, YYYY" (tiếng Anh)
        try:
            dt = datetime.strptime(text, "%B %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

        return text  # Trả về raw nếu không parse được

    def _extract_phone(self, text: str) -> Optional[str]:
        """Trích xuất số điện thoại VN từ chuỗi text."""
        if not text:
            return None
        match = re.search(
            r"(?<!\d)(0[3-9]\d{8}|\+84[3-9]\d{8}|84[3-9]\d{8})(?!\d)",
            text
        )
        return match.group(1) if match else None

    def _parse_iso_or_relative(self, text: str) -> str:
        """Parse ISO datetime string (datetime attribute) hoặc relative text."""
        if not text:
            return ""
        text = text.strip()
        # ISO 8601: 2026-05-18T10:30:00Z hoặc 2026-05-18
        m = re.match(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)
        return self._parse_relative_date(text)

    def _parse_relative_date(self, rel_text: str) -> str:
        now = datetime.now()
        if not rel_text:
            return ""
        try:
            text = rel_text.strip().lower()

            # Thử parse ngày cụ thể trước: dd/mm/yyyy, dd-mm-yyyy
            m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
            if m:
                return datetime(
                    int(m.group(3)), int(m.group(2)), int(m.group(1))
                ).strftime("%Y-%m-%d")

            # ISO 2026-05-18
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
            if m:
                return m.group(0)

            # Relative: tìm số
            num_match = re.search(r"(\d+)", text)
            num = int(num_match.group(1)) if num_match else 1

            # Tiếng Việt + tiếng Anh
            if any(w in text for w in ["giờ", "hour", "hr"]):
                date = now - timedelta(hours=num)
            elif any(w in text for w in ["ngày", "day"]):
                date = now - timedelta(days=num)
            elif any(w in text for w in ["tuần", "week"]):
                date = now - timedelta(weeks=num)
            elif any(w in text for w in ["tháng", "month"]):
                date = now - timedelta(days=num * 30)
            elif any(w in text for w in ["năm", "year"]):
                date = now - timedelta(days=num * 365)
            elif "hôm nay" in text or "today" in text or "just now" in text or "vừa" in text:
                date = now
            elif "hôm qua" in text or "yesterday" in text:
                date = now - timedelta(days=1)
            else:
                # Không xác định được thì trả về rỗng để tránh lưu sai
                return ""

            return date.strftime("%Y-%m-%d")
        except Exception:
            return ""
