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

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    # ==================== INSERT ====================

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
            status, scraped_at
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
            'approved', GETUTCDATE()
        WHERE NOT EXISTS (
            SELECT 1 FROM jobs
            WHERE source_name = ? AND external_id = ?
        )
        """

        for job in jobs_data:
            try:
                # Salary: ưu tiên dùng giá trị đã parse trong JobModel,
                # fallback parse lại từ salary_raw nếu cần
                salary_min = job.get("salary_min")
                salary_max = job.get("salary_max")
                if salary_min is None and salary_max is None:
                    salary_min, salary_max = self._parse_salary(job.get("salary", ""))

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
                latitude = job.get("latitude")
                longitude = job.get("longitude")
                geocoding_confidence = job.get("geocoding_confidence", 0)

                # Null-safe: chuyển NaN/None thành None cho SQL
                import math
                def safe_float(v):
                    if v is None: return None
                    try:
                        f = float(v)
                        return None if math.isnan(f) else f
                    except (ValueError, TypeError):
                        return None

                latitude = safe_float(latitude)
                longitude = safe_float(longitude)
                geocoding_confidence = safe_float(geocoding_confidence) or 0

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
                    latitude,           # latitude
                    longitude,          # longitude
                    geocoding_confidence,  # geocoding_confidence
                    skills_str,         # skills (JSON)
                    job.get("description", ""),   # description
                    job.get("requirements", ""),  # requirements
                    trunc(job.get("job_type"), 100),
                    trunc(job.get("experience_year"), 200),
                    trunc(job.get("education"), 200),
                    trunc(job.get("industry"), 200),
                    deadline_val,
                    trunc(job.get("phone"), 50),
                    trunc(job.get("job_url"), 1000),  # source_url
                    trunc(job.get("source"), 100),    # source_name
                    external_id,
                    posted_date_val,  # posted_date
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
                            (trunc(job.get("source"), 100), external_id)
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
                                cursor.execute(loc_sql, (
                                    job_id,
                                    trunc(loc.get("address"), 500),
                                    loc.get("lat"),
                                    loc.get("lng"),
                                    loc.get("confidence", 0)
                                ))
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
        match = re.search(r"/(\d{5,})", url)
        return match.group(1) if match else url[-50:]

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
