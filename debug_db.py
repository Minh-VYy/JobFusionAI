# debug_db.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.facebook_db import FacebookDB

test_job = {
    "title": "Test Job Debug",
    "company": "Test Company",
    "description": "Test description",
    "salary": "6tr",
    "location": "Đà Nẵng",
    "skills": "phục vụ",
    "job_url": f"https://facebook.com/test_{os.urandom(4).hex()}",
    "post_id": f"test_{os.urandom(4).hex()}",
}

with FacebookDB() as db:
    db.create_tables()
    result = db.insert_facebook_job(test_job)
    print(f"Insert result: {result}")

    # Đếm jobs facebook
    cursor = db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE source_name = 'facebook'")
    count = cursor.fetchone()[0]
    print(f"Total facebook jobs in DB: {count}")