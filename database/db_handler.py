# database/db_handler.py
import pyodbc
import logging
import os
import re
import json
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class DBHandler:
    """
    Kết nối SQL Server và lưu jobs.
    Mapping từ JobModel → bảng jobs trong job_agent_db
    """

    def __init__(self):
        self.conn_str = os.getenv("ODBC_CONNECTION_STRING")
        if not self.conn_str:
            db_driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
            db_server = os.getenv("DB_SERVER", r"localhost\MVY_350")
            db_name = os.getenv("DB_NAME", "job_agent_db")
            db_user = os.getenv("DB_USER", "sa")
            db_password = os.getenv("DB_PASSWORD", "123456")
            self.conn_str = (
                f"DRIVER={{{db_driver}}};"
                f"SERVER={db_server};"
                f"DATABASE={db_name};"
                f"UID={db_user};"
                f"PWD={db_password};"
                f"TrustServerCertificate=yes;"
            )
        self.conn = None

    # ==================== KẾT NỐI ====================

    def connect(self):
        try:
            self.conn = pyodbc.connect(self.conn_str)
            logger.info("✅ Kết nối SQL Server thành công")
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối SQL Server: {e}")
            return False

    def disconnect(self):
        if self.conn:
            self.conn.close()
            logger.info("🔌 Đã đóng kết nối SQL Server")

    def close(self):
        self.disconnect()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    # ==================== INSERT ====================

    def _get_moderation_mode(self) -> str:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "bot_config.json"
        )
        default_mode = "manual"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            policy = config_data.get("moderation_policy") or {}
            mode = str(policy.get("mode", default_mode)).lower()
            return mode if mode in ("auto", "manual") else default_mode
        except Exception:
            return default_mode

    def insert_jobs(self, jobs_data: list[dict]) -> dict:
        """
        Insert list jobs vào bảng jobs.
        Bỏ qua nếu đã tồn tại (dựa vào source_name + external_id).
        Trả về: {"inserted": N, "skipped": N, "errors": N}
        """
        if not self.conn:
            logger.error("❌ Chưa kết nối DB")
            return {"inserted": 0, "skipped": 0, "errors": 0}

        cursor = self.conn.cursor()
        stats = {"inserted": 0, "skipped": 0, "errors": 0}
        moderation_mode = self._get_moderation_mode()

        sql = """
        INSERT INTO jobs (
            title, company,
            salary_raw, salary_min, salary_max,
            address_raw, address_clean,
            latitude, longitude, geocoding_confidence,
            skills, description, requirements,
            job_type, experience_year, education, industry,
            deadline, phone,
            source_url, source_name, external_id,
            posted_date,
            status, needs_review, scraped_at
        )
        SELECT
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?,
            ?, ?, GETUTCDATE()
        WHERE NOT EXISTS (
            SELECT 1 FROM jobs
            WHERE source_name = ? AND external_id = ?
        )
        """

        for job in jobs_data:
            try:
                # Null-safe: chuyển NaN/None/chuỗi rỗng thành None cho SQL
                import math

                def safe_float(v):
                    if v is None or str(v).strip() == "":
                        return None
                    try:
                        f = float(v)
                        return None if math.isnan(f) else f
                    except (ValueError, TypeError):
                        return None

                # Salary: ưu tiên dùng giá trị đã parse trong JobModel,
                # fallback parse lại từ salary_raw nếu cần
                salary_min = safe_float(job.get("salary_min"))
                salary_max = safe_float(job.get("salary_max"))
                if salary_min is None and salary_max is None:
                    parsed_min, parsed_max = self._parse_salary(job.get("salary", ""))
                    salary_min = safe_float(parsed_min)
                    salary_max = safe_float(parsed_max)

                # external_id từ URL
                external_id = self._extract_external_id(job.get("job_url", ""))

                # skills: list → JSON string
                skills = job.get("skills", [])
                if isinstance(skills, list):
                    skills_str = json.dumps(skills, ensure_ascii=False)
                else:
                    skills_str = str(skills)

                # Truncate các field có giới hạn độ dài
                def trunc(val, n):
                    return (str(val) if val is not None else "")[:n]

                # Tọa độ GPS từ geocoding
                latitude = safe_float(job.get("latitude"))
                longitude = safe_float(job.get("longitude"))
                geocoding_confidence = safe_float(job.get("geocoding_confidence"))

                # posted_date
                from datetime import datetime as _dt

                posted_date_val = job.get("posted_date") or None
                if posted_date_val:
                    s = str(posted_date_val).strip()
                    if s in ("", "nan", "None", "1900-01-01"):
                        posted_date_val = None
                    else:
                        # Thử parse datetime cho SQL Server
                        try:
                            posted_date_val = _dt.strptime(s[:10], "%Y-%m-%d")
                        except ValueError:
                            try:
                                posted_date_val = _dt.strptime(s[:10], "%d/%m/%Y")
                            except ValueError:
                                posted_date_val = None

                # deadline
                deadline_val = job.get("deadline") or None
                if deadline_val:
                    s = str(deadline_val).strip()
                    if s in ("", "nan", "None", "1900-01-01", "1900-01-01 00:00:00"):
                        deadline_val = None
                    else:
                        try:
                            deadline_val = _dt.strptime(s[:10], "%Y-%m-%d")
                        except ValueError:
                            try:
                                deadline_val = _dt.strptime(s[:10], "%d/%m/%Y")
                            except ValueError:
                                deadline_val = None

                source_name_lower = str(job.get("source", "")).strip().lower()
                if source_name_lower in ("topcv", "vietnamworks", "itviec"):
                    job_status = "approved"
                    needs_review = 0
                else:
                    job_status = "approved" if moderation_mode == "auto" else "pending"
                    needs_review = 1 if moderation_mode == "manual" else 0

                params = (
                    trunc(job.get("title"), 500),
                    trunc(job.get("company"), 300),
                    trunc(job.get("salary"), 200),  # salary_raw
                    salary_min,  # salary_min (float | None)
                    salary_max,  # salary_max (float | None)
                    trunc(job.get("location"), 500),  # address_raw
                    trunc(
                        job.get("address_clean") or job.get("location"), 500
                    ),  # address_clean
                    latitude,  # latitude
                    longitude,  # longitude
                    geocoding_confidence,  # geocoding_confidence
                    skills_str,  # skills (JSON)
                    job.get("description", ""),  # description
                    job.get("requirements", ""),  # requirements
                    trunc(job.get("job_type"), 100),
                    trunc(job.get("experience_year"), 200),
                    trunc(job.get("education"), 200),
                    trunc(job.get("industry"), 200),
                    deadline_val,
                    trunc(job.get("phone"), 50),
                    trunc(job.get("job_url"), 1000),  # source_url
                    trunc(job.get("source"), 100),  # source_name
                    external_id,
                    posted_date_val,  # posted_date
                    job_status,
                    needs_review,
                    # WHERE NOT EXISTS
                    trunc(job.get("source"), 100),
                    external_id,
                )

                cursor.execute(sql, params)

                if cursor.rowcount > 0:
                    stats["inserted"] += 1
                    logger.info(f"   💾 Inserted: {job.get('title', '')[:50]}")

                    # Cập nhật job_locations
                    all_locations = job.get("all_locations", [])
                    if all_locations:
                        # Lấy job_id vừa insert (vì không dùng OUTPUT INSERTED.id được do WHERE NOT EXISTS)
                        cursor.execute(
                            "SELECT id FROM jobs WHERE source_name = ? AND external_id = ?",
                            (trunc(job.get("source"), 100), external_id),
                        )
                        row = cursor.fetchone()
                        if row:
                            job_id = row[0]
                            # Insert vào job_locations
                            loc_sql = """
                            INSERT INTO job_locations (job_id, address_text, latitude, longitude, geocoding_confidence)
                            VALUES (?, ?, ?, ?, ?)
                            """
                            for loc in all_locations:
                                cursor.execute(
                                    loc_sql,
                                    (
                                        job_id,
                                        trunc(loc.get("address"), 500),
                                        loc.get("lat"),
                                        loc.get("lng"),
                                        loc.get("confidence", 0),
                                    ),
                                )
                else:
                    stats["skipped"] += 1
                    logger.info(f"   ⏭️  Skipped (exists): {job.get('title', '')[:50]}")

            except Exception as e:
                logger.error(f"❌ Lỗi insert job '{job.get('title', '')}': {e}")
                stats["errors"] += 1
                continue

        self.conn.commit()
        return stats

    # ==================== HELPERS ====================

    def _parse_salary(self, salary_text: str):
        """
        Parse salary text → (min, max) dạng số triệu VND.
        Dùng làm fallback khi JobModel chưa parse sẵn.
        """
        if not salary_text:
            return None, None

        lower = salary_text.lower()
        negotiable = [
            "thỏa thuận",
            "thoả thuận",
            "thương lượng",
            "negotiable",
            "competitive",
            "attractive",
        ]
        if any(kw in lower for kw in negotiable):
            return None, None

        # Bỏ dấu phẩy hàng nghìn đúng cách: "1,900" → "1900"
        clean = re.sub(r"(\d),(\d{3})", r"\1\2", salary_text)
        numbers = re.findall(r"\d+(?:\.\d+)?", clean)
        if not numbers:
            return None, None

        is_usd = "usd" in lower or "$" in salary_text

        def to_million(val: float) -> float:
            if is_usd:
                return round(val * 0.025, 2)  # 1 USD = 25,000 VND = 0.025 triệu
            return round(val / 1000, 2) if val >= 1000 else val

        nums = [to_million(float(n)) for n in numbers]
        if len(nums) >= 2:
            return min(nums[0], nums[1]), max(nums[0], nums[1])
        return nums[0], None

    def _extract_external_id(self, url: str) -> str:
        """Trích ID từ URL job. VD: .../2135451.html → '2135451'"""
        if not url:
            return ""
        # Thử tìm các chuỗi số từ 5 chữ số trở lên trong URL (lấy số cuối cùng thường là Job ID)
        matches = re.findall(r"\d{5,}", url)
        if matches:
            return matches[-1]
        return url[-50:]

    # ==================== QUERY ====================

    def count_jobs(self) -> int:
        if not self.conn:
            return 0
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs")
        return cursor.fetchone()[0]

    def get_jobs_by_source(self) -> dict:
        if not self.conn:
            return {}
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT source_name, COUNT(*) as total
            FROM jobs
            GROUP BY source_name
            ORDER BY total DESC
        """)
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_crawled_urls(self, source_name: str, max_age_days: int = 7) -> set:
        if not self.conn:
            return set()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT source_url FROM jobs
                WHERE source_name = ?
                  AND scraped_at >= DATEADD(day, ?, GETUTCDATE())
                  AND source_url IS NOT NULL AND source_url != ''
            """,
                (source_name, -abs(max_age_days)),
            )
            urls = {row[0].strip() for row in cursor.fetchall() if row[0]}
            logger.info(
                f"   📋 [{source_name}] {len(urls)} URLs đã crawl trong {max_age_days}d"
            )
            return urls
        except Exception as e:
            logger.warning(f"   ⚠️ get_crawled_urls failed: {e} — fallback crawl all")
            return set()

    def update_task_progress(
        self,
        source_name: str,
        status: str,
        total_scraped: int = 0,
        total_found: int = 0,
        total_errors: int = 0,
        error_log: str = None,
        max_pages: int = None,
    ) -> None:
        """Cập nhật tiến độ của task trong bảng scrape_tasks"""
        if not self.conn:
            return
        from datetime import datetime

        try:
            cursor = self.conn.cursor()
            # Kiểm tra xem task đã tồn tại chưa
            cursor.execute(
                "SELECT id FROM scrape_tasks WHERE source_name = ?", (source_name,)
            )
            row = cursor.fetchone()
            now = datetime.utcnow()
            if row:
                task_id = row[0]
                sql = """
                    UPDATE scrape_tasks 
                    SET status = ?, 
                        total_scraped = ?, 
                        total_found = ?, 
                        total_errors = ?, 
                        error_log = ?, 
                        updated_at = ?
                """
                params = [
                    status,
                    total_scraped,
                    total_found,
                    total_errors,
                    error_log,
                    now,
                ]
                if max_pages is not None:
                    sql += ", max_pages = ?"
                    params.append(max_pages)
                if status == "running":
                    sql += ", last_run_at = ?"
                    params.append(now)
                sql += " WHERE id = ?"
                params.append(task_id)
                cursor.execute(sql, params)
            else:
                # Tạo mới nếu chưa có
                sql = """
                    INSERT INTO scrape_tasks (name, source_name, seed_url, status, total_scraped, total_found, total_errors, error_log, last_run_at, created_at, updated_at, max_pages, is_scheduled, schedule_cron)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                name = f"{source_name.capitalize()} Crawler"
                seed_url = (
                    f"https://www.{source_name}.com"
                    if source_name != "facebook"
                    else "https://www.facebook.com"
                )
                last_run = now if status == "running" else None
                m_pages = max_pages if max_pages is not None else 1
                cursor.execute(
                    sql,
                    (
                        name,
                        source_name,
                        seed_url,
                        status,
                        total_scraped,
                        total_found,
                        total_errors,
                        error_log,
                        last_run,
                        now,
                        now,
                        m_pages,
                        False,
                        "Hàng ngày",
                    ),
                )
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Lỗi update_task_progress cho {source_name}: {e}")

    def get_task_max_pages(self, source_name: str, default_val: int = 2) -> int:
        """Lấy số trang cào tối đa được cấu hình trong bảng scrape_tasks"""
        if not self.conn:
            return default_val
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT max_pages FROM scrape_tasks WHERE source_name = ?",
                (source_name.lower(),),
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.warning(f"⚠️ get_task_max_pages failed for {source_name}: {e}")
        return default_val
