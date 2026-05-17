# test_itviec_ai.py
import logging
import sys
import io
from crawler.itviec_crawler import ITviecCrawler
from database.db_handler import DBHandler

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)


def test_itviec():
    print("🚀 Bắt đầu test ITviec (Deep Scrape - Detail Page)...")
    crawler = ITviecCrawler(max_pages=1, headless=False)
    jobs = crawler.crawl()

    print(f"\n✅ Đã cào được {len(jobs)} công việc.")

    if not jobs:
        print("❌ Không có job nào, kiểm tra lại crawler.")
        return

    # ── Hiển thị kết quả đầy đủ ───────────────────────────────────
    print("\n" + "=" * 120)
    print("KẾT QUẢ CHI TIẾT")
    print("=" * 120)

    for i, j in enumerate(jobs, 1):
        print(f"\n[JOB {i}]")
        print(f"  Title        : {j.title}")
        print(f"  Company      : {j.company}")
        print(f"  Salary       : {j.salary}  (min={j.salary_min}, max={j.salary_max})")
        print(f"  Location     : {j.location}")
        print(f"  Job Type     : {j.job_type}")
        print(f"  Experience   : {j.experience_year}")
        print(f"  Education    : {j.education}")
        print(f"  Industry     : {j.industry}")
        print(f"  Deadline     : {j.deadline}")
        print(f"  Phone        : {j.phone}")
        print(f"  Skills       : {', '.join(j.skills[:8])}{'...' if len(j.skills) > 8 else ''}")
        print(f"  Description  : {len(j.description)} ký tự")
        print(f"  Requirements : {len(j.requirements)} ký tự")
        print(f"  URL          : {j.job_url}")
        print(f"  Posted       : {j.posted_date}")

    # ── Lưu DB ────────────────────────────────────────────────────
    print("\n" + "=" * 120)
    print("⏳ Đang lưu vào SQL Server...")

    # Dùng to_dict() — chuẩn của JobModel
    jobs_data = [j.to_dict() for j in jobs]

    db = DBHandler()
    if db.connect():
        stats = db.insert_jobs(jobs_data)
        print(f"\n💾 Kết quả DB: Inserted={stats['inserted']} | Skipped={stats['skipped']} | Errors={stats['errors']}")
        db.disconnect()
    else:
        print("❌ Không thể kết nối DB!")


if __name__ == "__main__":
    test_itviec()
