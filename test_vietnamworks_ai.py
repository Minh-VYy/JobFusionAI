# test_vietnamworks_ai.py
import logging
import sys
import io
from crawler.vietnamworks_crawler import VietnamWorksCrawler
from database.db_handler import DBHandler
from geocoding import geocoder
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Cấu hình logging để hiển thị đúng format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def test_vietnamworks_crawler():
    print("🚀 Bắt đầu test VietnamWorks crawler...")
    # Chỉ crawl 1 trang để lấy khoảng 5-10 job
    crawler = VietnamWorksCrawler(max_pages=1, headless=False)
    jobs = crawler.crawl()

    # Chỉ lấy 5 job đầu tiên để kiểm tra
    test_jobs = jobs[:5] if len(jobs) > 5 else jobs

    print(
        f"\n✅ Đã cào được {len(jobs)} công việc, kiểm tra {len(test_jobs)} job đầu tiên.\n"
    )

    if test_jobs:
        print("--- KẾT QUẢ (5 CỘT DỮ LIỆU) ---")
        print(
            f"{'TITLE':<40} | {'COMPANY':<25} | {'SALARY':<20} | {'LOCATION':<25} | {'SKILLS'}"
        )
        print("-" * 150)
        for j in test_jobs:
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

        print(f"\n📊 Chi tiết từng job:")
        for idx, j in enumerate(test_jobs, 1):
            print(f"\n📌 Job {idx}:")
            print(f"   - URL: {j.job_url}")
            print(f"   - Ngày đăng: {j.posted_date if j.posted_date else 'N/A'}")
            print(f"   - Độ dài mô tả: {len(j.description)} ký tự")
            print(
                f"   - Số kỹ năng: {len(j.skills)} ({', '.join(j.skills) if j.skills else 'N/A'})"
            )

        # Tuỳ chọn lưu vào database
        save_to_db = input(
            "\n💾 Bạn có muốn lưu 5 job này vào database không? (y/n): "
        ).lower()
        if save_to_db == "y":
            print("⏳ Đang lưu dữ liệu vào cơ sở dữ liệu SQL Server...")
            jobs_data = []
            for j in test_jobs:
                if hasattr(j, "to_dict"):
                    jobs_data.append(j.to_dict())
                elif hasattr(j, "dict"):
                    jobs_data.append(j.dict())
                elif hasattr(j, "model_dump"):
                    jobs_data.append(j.model_dump())
                else:
                    jobs_data.append(vars(j))

            # Chạy Geocoding để lấy tọa độ trước khi lưu
            print("🌍 Đang chạy Geocoding (Lấy tọa độ)...")
            df = pd.DataFrame(jobs_data)
            df = geocoder.geocode_dataframe(df)
            jobs_data_with_geo = df.to_dict("records")

            db = DBHandler()
            if db.connect():
                stats = db.insert_jobs(jobs_data_with_geo)
                print(
                    f"✨ Kết quả lưu DB: Inserted: {stats['inserted']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}"
                )
            else:
                print("❌ Không thể kết nối database")
    else:
        print("⚠️  Không tìm thấy công việc nào trên VietnamWorks")


if __name__ == "__main__":
    test_vietnamworks_crawler()
