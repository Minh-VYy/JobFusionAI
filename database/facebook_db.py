# database/facebook_db.py
import pyodbc
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class FacebookDB:
    """Lưu Facebook jobs + group trust score vào SQL Server"""

    def __init__(self):
        self.conn_str = (
            f"DRIVER={{{os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server')}}};"
            f"SERVER={os.getenv('DB_SERVER', r'THIEUQUANG')};"
            f"DATABASE={os.getenv('DB_NAME', 'findJob')};"
            f"UID={os.getenv('DB_USER', 'quang123')};"
            f"PWD={os.getenv('DB_PASSWORD', '123')};"
            f"TrustServerCertificate=yes;"
        )
        self.conn = None

    def connect(self):
        self.conn = pyodbc.connect(self.conn_str)
        logger.info("✅ FacebookDB connected")

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    # ============================================================
    # SETUP TABLES
    # ============================================================

    def create_tables(self):
        """Tạo bảng facebook_groups nếu chưa tồn tại.
        Các cột jobs đã được định nghĩa đầy đủ trong init_db.sql.
        """
        cursor = self.conn.cursor()

        cursor.execute("""
        IF NOT EXISTS (
            SELECT * FROM sysobjects
            WHERE name='facebook_groups' AND xtype='U'
        )
        CREATE TABLE facebook_groups (
            id              INT IDENTITY(1,1) PRIMARY KEY,
            group_id        NVARCHAR(100)  NOT NULL UNIQUE,
            group_name      NVARCHAR(300)  NULL,
            group_url       NVARCHAR(500)  NULL,
            trust_score     FLOAT          DEFAULT 0.5,
            spam_ratio      FLOAT          DEFAULT 0.0,
            duplicate_ratio FLOAT          DEFAULT 0.0,
            crawl_priority  NVARCHAR(20)   DEFAULT 'normal',
            total_crawled   INT            DEFAULT 0,
            total_spam      INT            DEFAULT 0,
            total_duplicate INT            DEFAULT 0,
            last_crawled    DATETIME       NULL,
            is_active       BIT            DEFAULT 1,
            created_at      DATETIME       DEFAULT GETUTCDATE()
        )
        """)
        self.conn.commit()
        logger.info("✅ Tables ready")


    # ============================================================
    # INSERT JOB
    # ============================================================

    def insert_facebook_job(self, job_data: dict) -> bool:
        """Insert job Facebook bằng câu SQL atomic (tránh race condition)."""
        cursor = self.conn.cursor()

        job_url = job_data.get("job_url", "")[:1000]
        post_id = job_data.get("post_id", "")[:200]
        fp_hash = job_data.get("fingerprint_hash", "")[:64]

        # Atomic INSERT ... WHERE NOT EXISTS (ngăn race condition)
        cursor.execute("""
            INSERT INTO jobs (
                title, company, description,
                salary_raw, address_raw, address_clean,
                skills, source_url, source_name,
                external_id, status,
                is_geocoded, latitude, longitude,
                normalized_title, normalized_location,
                salary_min, salary_max, phone,
                fingerprint_hash, source_type,
                job_type, requirements,
                posted_date, scraped_at
            )
            SELECT
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, 'facebook',
                ?, 'pending',
                0, 16.0, 108.2,
                ?, ?,
                ?, ?, ?,
                ?, 'facebook',
                ?, ?,
                ?, GETUTCDATE()
            WHERE NOT EXISTS (
                SELECT 1 FROM jobs
                WHERE source_url = ?
                   OR (external_id = ? AND source_name = 'facebook')
                   OR (fingerprint_hash = ? AND fingerprint_hash != '')
            )
        """, (
            job_data.get("title", "")[:500],
            job_data.get("company", "")[:300],
            job_data.get("description", ""),
            job_data.get("salary", "")[:200],
            job_data.get("location", "")[:500],
            job_data.get("location", "")[:500],
            job_data.get("skills", "")[:1000],
            job_url,
            post_id,
            job_data.get("normalized_title", "")[:500],
            job_data.get("normalized_location", "")[:300],
            job_data.get("salary_min", None),
            job_data.get("salary_max", None),
            job_data.get("phone", "")[:50],
            fp_hash,
            job_data.get("job_type", "")[:100],
            job_data.get("requirements", ""),
            job_data.get("posted_date", None) if job_data.get("posted_date") else None,
            # WHERE NOT EXISTS params
            job_url,
            post_id,
            fp_hash,
        ))

        self.conn.commit()
        return cursor.rowcount > 0

    
    # ============================================================
    # GROUP TRUST SCORE
    # ============================================================

    def upsert_group(self, group_data: dict):
        """Tạo hoặc cập nhật thông tin group"""
        cursor = self.conn.cursor()

        cursor.execute("""
        MERGE facebook_groups AS target
        USING (SELECT ? AS group_id) AS source
        ON target.group_id = source.group_id
        WHEN MATCHED THEN
            UPDATE SET
                trust_score     = ?,
                spam_ratio      = ?,
                duplicate_ratio = ?,
                crawl_priority  = ?,
                total_crawled   = total_crawled + ?,
                total_spam      = total_spam + ?,
                total_duplicate = total_duplicate + ?,
                last_crawled    = GETUTCDATE()
        WHEN NOT MATCHED THEN
            INSERT (group_id, group_name, group_url,
                    trust_score, crawl_priority, last_crawled)
            VALUES (?, ?, ?, ?, ?, GETUTCDATE());
        """,
        (
            group_data["group_id"],
            group_data.get("trust_score", 0.5),
            group_data.get("spam_ratio", 0.0),
            group_data.get("duplicate_ratio", 0.0),
            group_data.get("crawl_priority", "normal"),
            group_data.get("total_crawled", 0),
            group_data.get("total_spam", 0),
            group_data.get("total_duplicate", 0),
            group_data["group_id"],
            group_data.get("group_name", ""),
            group_data.get("group_url", ""),
            group_data.get("trust_score", 0.5),
            group_data.get("crawl_priority", "normal"),
        ))

        self.conn.commit()

    def get_all_fingerprints(self) -> list:
        """Load tất cả external_id từ DB để dùng làm persistent duplicate cache."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT external_id FROM jobs
                WHERE source_name = 'facebook'
                AND external_id IS NOT NULL
                AND external_id != ''
            """)
            rows = cursor.fetchall()
            return [row[0] for row in rows if row[0]]
        except Exception as e:
            logger.warning(f"get_all_fingerprints failed: {e}")
            return []

    def get_jobs_for_cross_detection(self, limit: int = 2000) -> list:
        """Load jobs gần nhất từ DB để làm baseline cho CrossSourceDetector."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT TOP (?) external_id, source_name,
                       title, company, address_raw, salary_raw,
                       phone, normalized_title, normalized_location,
                       salary_min, salary_max, fingerprint_hash
                FROM jobs
                WHERE external_id IS NOT NULL
                ORDER BY scraped_at DESC
            """, (limit,))
            rows = cursor.fetchall()
            cols = ["job_id", "source", "title", "company", "location",
                    "salary", "phone", "normalized_title", "normalized_location",
                    "salary_min", "salary_max", "fingerprint_hash"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            logger.warning(f"get_jobs_for_cross_detection failed: {e}")
            return []

    def get_verified_entities(self) -> dict:
        """Tải tất cả verified_entities để làm bộ nhớ thực thể động cho cleaner."""
        entities = {"phone": {}, "address": {}}
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                IF EXISTS (SELECT * FROM sysobjects WHERE name='verified_entities' AND xtype='U')
                BEGIN
                    SELECT entity_type, entity_value, mapped_company FROM verified_entities
                END
                ELSE
                BEGIN
                    SELECT 'phone' as entity_type, '0000000000' as entity_value, 'none' as mapped_company WHERE 1=0
                END
            """)
            rows = cursor.fetchall()
            for row in rows:
                ent_type, ent_val, company = row[0], row[1], row[2]
                if ent_type in entities and ent_val and company:
                    entities[ent_type][ent_val.strip()] = company.strip()
            return entities
        except Exception as e:
            logger.warning(f"get_verified_entities failed: {e}")
            return entities
