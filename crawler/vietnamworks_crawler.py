# crawler/vietnamworks_crawler.py
from bs4 import BeautifulSoup
from crawler.base_crawler import BaseCrawler, logger
from models.job_model import JobModel
import re


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
                logger.info(
                    f"📄 VietnamWorks - Crawl trang {page_num}/{self.max_pages}"
                )

                # ✅ Thử URL dạng mới (ngành IT g=21)
                url = f"https://www.vietnamworks.com/viec-lam?g=21&ignoreLocation=true&page={page_num}"

                try:
                    logger.info(f"🌐 Đang truy cập: {url}")
                    self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"⚠️  Lỗi goto: {e}")

                self.human_sleep(4, 5)

                # Chờ job card — thử nhiều selector
                job_appeared = False
                for selector in [
                    "div.new-job-card",
                    "div[class*='job-card']",
                    "div[class*='card']",
                ]:
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
                    with open(
                        f"debug_vw_page{page_num}.html", "w", encoding="utf-8"
                    ) as f:
                        f.write(html)
                    logger.info(f"   → Đã lưu debug_vw_page{page_num}.html")
                    continue

                self.scroll_to_bottom()
                self.human_sleep(2, 3)

                html = self.get_html()
                page_jobs = self.parse_job_list_with_details(html)
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

    def parse_job_list_with_details(self, html: str) -> list[JobModel]:
        """Parse danh sách + click vào từng job để lấy chi tiết"""
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        # ✅ Selector đúng từ debug
        job_cards = soup.select("div.new-job-card")

        if not job_cards:
            logger.warning("⚠️  VietnamWorks: Không tìm thấy job card")
            return []

        logger.info(f"   → Parse {len(job_cards)} cards với click chi tiết...")

        for idx, card in enumerate(job_cards[:5]):  # Chỉ lấy 5 job để test
            try:
                job = self.parse_single_job(card)
                if job.title and job.job_url:
                    # Click vào job để lấy chi tiết
                    self._extract_job_details(job)
                    jobs.append(job)
                    logger.info(f"   ✅ Job {idx + 1}: {job.title[:40]}")
            except Exception as e:
                logger.error(f"❌ Lỗi parse VietnamWorks: {e}")
                continue

        return jobs

    def _extract_job_details(self, job: JobModel):
        """Click vào job URL và lấy description, requirements, skills từ detail page"""
        try:
            logger.info(f"   🔗 Lấy chi tiết từ: {job.job_url}")
            self.page.goto(job.job_url, wait_until="domcontentloaded", timeout=30000)
            self.human_sleep(1, 2)

            detail_html = self.get_html()
            soup = BeautifulSoup(detail_html, "lxml")

            # --- Description & Requirements ---
            desc_parts = []
            req_parts = []
            
            for header in soup.find_all(["h2", "h3", "strong"]):
                text = header.get_text(strip=True).lower()
                parent = header.find_parent(["div", "section"])
                if parent:
                    content = parent.get_text(separator="\n", strip=True)
                    if "mô tả" in text or "phúc lợi" in text or "quyền lợi" in text:
                        if content not in desc_parts:
                            desc_parts.append(content)
                    elif "yêu cầu" in text or "kinh nghiệm" in text:
                        if content not in req_parts:
                            req_parts.append(content)

            if desc_parts:
                job.description = "\n---\n".join(desc_parts)
            if req_parts:
                job.requirements = "\n---\n".join(req_parts)

            # Fallback
            if not job.description:
                desc_el = soup.select_one("div[class*='description'], div[class*='job-description']")
                if desc_el:
                    job.description = desc_el.get_text(separator="\n", strip=True)
            if not job.requirements:
                req_el = soup.select_one("div[class*='requirement']")
                if req_el:
                    job.requirements = req_el.get_text(separator="\n", strip=True)

            # --- Ngành nghề (Industry) ---
            for label in soup.find_all(string=re.compile(r"Ngành nghề|Lĩnh vực", re.IGNORECASE)):
                text = label.get_text(strip=True).lower()
                if len(text) > 20 or "top" in text or "tìm" in text or "việc làm" in text or "khác" in text:
                    continue
                parent = label.find_parent(["div", "li", "span", "td"])
                if parent:
                    sib = parent.find_next_sibling(["div", "p", "a", "span", "ul"]) or parent.select_one("a, span:not([class*='title'])")
                    if sib:
                        job.industry = sib.get_text(separator=", ", strip=True)
                        break

            # --- Kỹ năng (Skills) ---
            if job.skills is None:
                job.skills = []
            skill_els = soup.select("span[class*='skill'], a[class*='skill'], span[class*='tag']")
            for s in skill_els:
                st = s.get_text(strip=True)
                if st and len(st) > 1 and not any(st.lower() == us.lower() for us in job.skills):
                    job.skills.append(st)

            # --- Địa điểm làm việc (Location) ---
            loc_label = soup.find(string=re.compile(r"Địa điểm làm việc|Địa điểm|Location|Work location", re.IGNORECASE))
            if loc_label:
                parent = loc_label.find_parent(["div", "h3", "h2", "strong"])
                if parent:
                    loc_container = parent.find_next_sibling("div") or parent.parent
                    if loc_container:
                        loc_text = loc_container.get_text(separator=", ", strip=True)
                        if loc_text and len(loc_text) > 5 and len(loc_text) < 500 and "location" not in loc_text.lower():
                            job.location = re.sub(r"^\-\s*", "", loc_text.strip())

            # Fallback cho Location dùng CSS Selector nếu label không ăn
            if not job.location or "₫" in job.location or "tr/tháng" in job.location:
                loc_el = soup.select_one(".company-location, .job-location, .location, .address")
                if loc_el:
                    ltext = loc_el.get_text(separator=", ", strip=True)
                    if ltext and len(ltext) > 5 and "₫" not in ltext and "tháng" not in ltext:
                        job.location = ltext

            # Smart Parser: Đọc free-text để điền các ô còn trống
            self._fill_missing_fields_from_text(job)

        except Exception as e:
            logger.warning(f"   ⚠️  Không lấy được chi tiết: {e}")

    def _fill_missing_fields_from_text(self, job: JobModel):
        """Smart Parser: Đọc free-text để vét thông tin bị thiếu."""
        full_text = f"{job.title or ''} {job.requirements or ''} {job.description or ''}".lower()
        if not full_text.strip(): return

        # 1. Experience Year
        if not job.experience_year or "kinh nghiệm" in job.experience_year.lower():
            job.experience_year = ""
            exp_match = re.search(r"(từ\s*\d+\s*(?:-|đến|to)\s*\d+\s*(?:năm|year)|(?:ít nhất|at least)?\s*\d+\+?\s*(?:năm|year)s?\s*(?:of\s*)?(?:kinh nghiệm|experience))", full_text)
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

        # 4. Skills
        if not job.skills:
            job.skills = []
        common_skills = ["python", "java", "javascript", "react", "node.js", "c#", ".net", "sql", "aws", "docker", "php", "vue", "angular"]
        for skill in common_skills:
            if re.search(r"\b" + re.escape(skill) + r"\b", full_text):
                if not any(skill.lower() == s.lower() for s in job.skills):
                    job.skills.append(skill.upper() if len(skill) <= 3 else skill.title())
                    
        # 5. Industry
        if not job.industry:
            job.industry = "IT / Software"

        # 6. Salary
        if not job.salary or job.salary.lower() in ["thỏa thuận", "thoả thuận", "thương lượng", "negotiable", "thương lượng (thỏa thuận)"]:
            sal_patterns = [
                r"(\$[\d,\.]+\s*(?:-|to|đến|~)\s*\$[\d,\.]+)",
                r"([\d,\.]+\s*(?:-|to|đến|~)\s*[\d,\.]+\s*(?:usd|triệu|tr|vnđ|vnd|k))",
                r"((?:up to|lên đến|tới|maximum|max)\s*\$?\s*[\d,\.]+\s*(?:usd|triệu|tr|k)?)",
                r"((?:mức lương|thu nhập|salary|lương).{0,15}?\$?\s*[\d,\.]+\s*(?:usd|triệu|tr|k))",
            ]
            for p in sal_patterns:
                sal_match = re.search(p, full_text)
                if sal_match:
                    job.salary = sal_match.group(1).title()
                    break

    def parse_single_job(self, card) -> JobModel:
        job = JobModel(source=self.SOURCE_NAME)

        # --- Title ---
        # <h2><a ...>Tên Job</a></h2>
        title_el = card.select_one("h2 a")
        job.title = title_el.get_text(strip=True) if title_el else ""

        # Strip "Mới" prefix nếu có
        if job.title.startswith("Mới"):
            job.title = job.title.replace("Mới", "", 1).strip()

        # --- URL ---
        if title_el:
            href = title_el.get("href", "")
            if href:
                # Chỉ lấy phần path, không cộng thêm parameter thừa
                if href.startswith("http"):
                    job.job_url = href
                else:
                    # Loại bỏ query string nếu có, chỉ lấy path
                    path = href.split("?")[0] if "?" in href else href
                    job.job_url = f"https://www.vietnamworks.com{path}"

        # --- Company ---
        # Selector cụ thể hơn cho company name
        company_el = card.select_one(
            "div[class*='company'] a, a[href*='nha-tuyen-dung']"
        )
        if not company_el:
            # Fallback: div class có chứa "employer" hoặc "company"
            company_el = card.select_one("div[class*='employer'] a")
        if not company_el:
            company_el = card.select_one("h3")
        job.company = company_el.get_text(strip=True) if company_el else ""

        # --- Salary ---
        # Tìm selector cụ thể cho salary
        salary_el = card.select_one("span[class*='salary']")
        if not salary_el:
            salary_el = card.select_one("div[class*='salary']")

        if salary_el:
            job.salary = salary_el.get_text(strip=True)
        else:
            # Fallback: tìm text ngắn có từ khóa salary
            job.salary = "Thỏa thuận"
            for el in card.find_all(["span", "div"], limit=20):
                text = el.get_text(strip=True)
                if (
                    any(kw in text for kw in ["triệu", "$", "Thỏa thuận"])
                    and 20 < len(text) < 60
                ):
                    job.salary = text
                    break

        # --- Location ---
        # Tìm selector cụ thể cho location - không lấy generic
        location_el = card.select_one("span[class*='location'], div[class*='location']")
        if location_el:
            loc_text = location_el.get_text(strip=True)
            # Chỉ lấy nếu chứa tên thành phố
            if (
                any(
                    city in loc_text
                    for city in [
                        "Hà Nội",
                        "Hồ Chí Minh",
                        "Đà Nẵng",
                        "Cần Thơ",
                        "Bình Dương",
                        "Đồng Nai",
                        "Hải Phòng",
                        "Remote",
                        "Toàn quốc",
                    ]
                )
                and len(loc_text) < 100
            ):
                job.location = loc_text
            else:
                job.location = ""
        else:
            # Fallback: tìm từng element có tên thành phố
            job.location = ""
            for el in card.find_all(["span", "div"], limit=15):
                text = el.get_text(strip=True)
                if (
                    any(
                        city in text
                        for city in [
                            "Hà Nội",
                            "Hồ Chí Minh",
                            "Đà Nẵng",
                            "Cần Thơ",
                            "Bình Dương",
                            "Đồng Nai",
                            "Hải Phòng",
                            "Remote",
                            "Toàn quốc",
                        ]
                    )
                    and 3 < len(text) < 100
                ):
                    job.location = text
                    break

        # Parse salary để tách min/max
        job.salary = self._parse_salary(job.salary)

        # --- Description (tóm tắt từ card nếu có) ---
        desc_el = card.select_one("div[class*='description'], p[class*='desc']")
        if desc_el:
            job.description = desc_el.get_text(strip=True)[:500]  # Cắt ngắn

        # --- Skills ---
        skill_els = card.select("a[class*='tag'], span[class*='skill-tag']")
        job.skills = [
            s.get_text(strip=True)
            for s in skill_els
            if s.get_text(strip=True) and len(s.get_text(strip=True)) > 1
        ][:10]  # Giới hạn max 10 skills

        # --- Posted Date ---
        date_el = card.select_one("span[class*='date'], span[class*='time']")
        if date_el:
            job.posted_date = date_el.get_text(strip=True)

        return job

    def _parse_salary(self, salary_text: str) -> str:
        """Parse salary text, loại bỏ location nếu nối sai, tách min-max"""
        if not salary_text:
            return "Thỏa thuận"

        # Loại bỏ tên thành phố ở cuối nếu nối sai
        cities = [
            "Hà Nội",
            "Hồ Chí Minh",
            "Đà Nẵng",
            "Cần Thơ",
            "Hải Phòng",
            "Bình Dương",
            "Đồng Nai",
        ]
        for city in cities:
            salary_text = salary_text.replace(city, "").strip()

        # Clean up
        salary_text = re.sub(
            r"\s+/thángth|/thán.*$", "", salary_text
        )  # Remove "/tháng" suffix
        salary_text = re.sub(r"\s+", " ", salary_text).strip()

        if not salary_text or salary_text == "":
            return "Thỏa thuận"

        return salary_text
