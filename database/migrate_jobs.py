"""
database/migrate_jobs.py
Chạy 1 lần để thêm các cột mới vào bảng jobs.
Usage: python database/migrate_jobs.py
"""
import sys
import os
sys.stdout.reconfigure(encoding="utf-8")

# Đảm bảo import được từ root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.facebook_db import FacebookDB

MIGRATIONS = [
    ("normalized_title",   "ALTER TABLE jobs ADD normalized_title   NVARCHAR(500)"),
    ("normalized_location","ALTER TABLE jobs ADD normalized_location NVARCHAR(300)"),
    ("salary_min",         "ALTER TABLE jobs ADD salary_min         FLOAT"),
    ("salary_max",         "ALTER TABLE jobs ADD salary_max         FLOAT"),
    ("phone",              "ALTER TABLE jobs ADD phone              NVARCHAR(50)"),
    ("fingerprint_hash",   "ALTER TABLE jobs ADD fingerprint_hash   NVARCHAR(64)"),
    ("source_type",        "ALTER TABLE jobs ADD source_type        NVARCHAR(50)"),
    ("cross_dup_score",    "ALTER TABLE jobs ADD cross_dup_score    FLOAT"),
    ("cross_dup_of",       "ALTER TABLE jobs ADD cross_dup_of       NVARCHAR(200)"),
]

def run():
    with FacebookDB() as db:
        cursor = db.conn.cursor()
        print("🔧 Bắt đầu migration...")
        for col_name, sql in MIGRATIONS:
            check = f"""
                SELECT COUNT(*) FROM sys.columns
                WHERE object_id = OBJECT_ID('jobs')
                AND name = '{col_name}'
            """
            cursor.execute(check)
            exists = cursor.fetchone()[0]
            if exists:
                print(f"  ✅ Cột '{col_name}' đã tồn tại — bỏ qua")
            else:
                try:
                    cursor.execute(sql)
                    db.conn.commit()
                    print(f"  ➕ Đã thêm cột '{col_name}'")
                except Exception as e:
                    print(f"  ❌ Lỗi thêm '{col_name}': {e}")
        print("✅ Migration hoàn tất!")

if __name__ == "__main__":
    run()
