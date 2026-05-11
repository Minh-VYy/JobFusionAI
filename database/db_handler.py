# database/db_handler.py
import pyodbc
import logging
import os
import re
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class DBHandler:
    """
    Kết nối SQL Server và lưu jobs.
    Mapping từ JobModel → bảng jobs trong job_agent_db
    """

    def __init__(self):
        db_driver = os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server')
        db_server = os.getenv('DB_SERVER', r'localhost\SQLEXPRESS')
        db_name = os.getenv('DB_NAME', 'job_agent_db')
        db_user = os.getenv('DB_USER', 'sa')
        db_password = os.getenv('DB_PASSWORD', '123456')

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
        """Mở kết nối tới SQL Server"""
        try:
            self.conn = pyodbc.connect(self.conn_str)
            logger.info("✅ Kết nối SQL Server thành công")
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối SQL Server: {e}")
            return False

    def disconnect(self):
        """Đóng kết nối"""
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
        Bỏ qua nếu đã tồn tại (dựa vào source_url).
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
            skills, description, requirements,
            source_url, source_name, external_id,
            status, scraped_at
        )
        SELECT
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            'pending', GETUTCDATE()
        WHERE NOT EXISTS (
            SELECT 1 FROM jobs
            WHERE source_name = ? AND external_id = ?
        )
        """

        for job in jobs_data:
            try:
                # Parse salary từ text → min/max số
                salary_min, salary_max = self._parse_salary(job.get("salary", ""))

                # Tạo external_id từ URL
                external_id = self._extract_external_id(job.get("job_url", ""))

                params = (
                    job.get("title", "")[:500],
                    job.get("company", "")[:300],

                    job.get("salary", "")[:200],   # salary_raw
                    salary_min,                     # salary_min
                    salary_max,                     # salary_max

                    job.get("location", "")[:500],  # address_raw
                    job.get("location", "")[:500],  # address_clean

                    job.get("skills", "")[:1000],   # skills
                    job.get("description", ""),     # description
                    job.get("requirements", ""),    # requirements

                    job.get("job_url", "")[:1000],  # source_url
                    job.get("source", "")[:100],    # source_name
                    external_id,                    # external_id

                    job.get("source", "")[:100],    # WHERE NOT EXISTS source_name check
                    external_id,                    # WHERE NOT EXISTS external_id check
                )

                cursor.execute(sql, params)

                if cursor.rowcount > 0:
                    stats["inserted"] += 1
                else:
                    stats["skipped"] += 1

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
        VD: "10 - 30 triệu" → (10.0, 30.0)
            "Thỏa thuận"    → (None, None)
        """
        if not salary_text or salary_text in ["Thỏa thuận", "Thoả thuận", ""]:
            return None, None

        # Tìm tất cả số trong string
        numbers = re.findall(r"\d+(?:\.\d+)?", salary_text.replace(",", "."))

        if len(numbers) >= 2:
            return float(numbers[0]), float(numbers[1])
        elif len(numbers) == 1:
            return float(numbers[0]), None

        return None, None

    def _extract_external_id(self, url: str) -> str:
        """
        Trích ID từ URL job.
        VD: topcv.vn/viec-lam/.../2135451.html → "2135451"
        """
        if not url:
            return ""
        # Tìm số ID ở cuối URL
        match = re.search(r"/(\d{5,})", url)
        return match.group(1) if match else url[-50:]

    # ==================== QUERY ====================

    def count_jobs(self) -> int:
        """Đếm tổng số jobs trong DB"""
        if not self.conn:
            return 0
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs")
        return cursor.fetchone()[0]

    def get_jobs_by_source(self) -> dict:
        """Thống kê jobs theo source"""
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