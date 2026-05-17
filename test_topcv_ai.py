# test_topcv_ai.py
import logging
import sys
import io
from crawler.topcv_crawler import TopCVCrawler
from database.db_handler import DBHandler

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Cấu hình logging để hiển thị đúng format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def test_topcv_crawler():
    print("🚀 Bắt đầu test TopCV crawler...")
    crawler = TopCVCrawler(max_pages=1, headless=False)
    jobs = crawler.crawl()

    # CHỈ LẤY 5 DỮ LIỆU ĐỂ TEST THEO YÊU CẦU CỦA USER
    jobs = jobs[:5]
    print(f"\n✅ Đã cào được {len(jobs)} công việc từ TopCV để test.\n")

    if jobs:
        print("--- KẾT QUẢ (5 CỘT DỮ LIỆU) ---")
        print(
            f"{'TITLE':<40} | {'COMPANY':<25} | {'SALARY':<20} | {'LOCATION':<25} | {'SKILLS'}"
        )
        print("-" * 150)
        for j in jobs:
            title = (j.title[:37] + "...") if len(j.title) > 40 else j.title
            company = (j.company[:22] + "...") if len(j.company) > 25 else j.company
            salary = (j.salary[:17] + "...") if len(j.salary) > 20 else j.salary
            location = (j.location[:22] + "...") if len(j.location) > 25 else j.location
            skills = (
                ", ".join(j.skills[:3]) if j.skills else "N/A"
            )  # Hiển thị 3 kỹ năng đầu tiên
            print(
                f"{title:<40} | {company:<25} | {salary:<20} | {location:<25} | {skills}"
            )

        print(f"\n📊 Tổng số job: {len(jobs)}")
        print(
            f"📝 Trung bình mô tả: {sum(len(j.description) for j in jobs) // len(jobs)} ký tự"
        )

        # Tuỳ chọn lưu vào database
        save_to_db = input(
            "\n💾 Bạn có muốn lưu dữ liệu vào database không? (y/n): "
        ).lower()
        if save_to_db == "y":
            print("⏳ Đang lưu dữ liệu vào cơ sở dữ liệu SQL Server...")
            jobs_data = []
            for j in jobs:
                if hasattr(j, "to_dict"):
                    jobs_data.append(j.to_dict())
                elif hasattr(j, "dict"):
                    jobs_data.append(j.dict())
                elif hasattr(j, "model_dump"):
                    jobs_data.append(j.model_dump())
                else:
                    jobs_data.append(vars(j))

            db = DBHandler()
            if db.connect():
                stats = db.insert_jobs(jobs_data)
                print(
                    f"✨ Kết quả lưu DB: Inserted: {stats['inserted']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}"
                )
            else:
                print("❌ Không thể kết nối database")
    else:
        print("⚠️  Không tìm thấy công việc nào trên TopCV")


if __name__ == "__main__":
    test_topcv_crawler()
