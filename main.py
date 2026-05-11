# main.py
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
import requests
import schedule
from dotenv import load_dotenv

from crawler.topcv_crawler import TopCVCrawler
from crawler.itviec_crawler import ITviecCrawler
from crawler.vietnamworks_crawler import VietnamWorksCrawler
from cleaner.data_cleaner import DataCleaner
from cleaner.skill_extractor import SkillExtractor
from cleaner.geocoder import Geocoder
from database.db_handler import DBHandler
import pandas as pd

# 1. Tải cấu hình từ .env
load_dotenv()

# 2. Cấu hình Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")

# Đọc cấu hình từ .env hoặc lấy giá trị mặc định
HEADLESS = os.getenv("HEADLESS", "True").lower() in ("true", "1", "yes", "t")
PAGES = int(os.getenv("CRAWL_PAGES", "2"))
SCHEDULE_TIME = os.getenv("CRAWL_SCHEDULE_TIME", "00:00")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CRAWLERS = [
    {"name": "TopCV",  "class": TopCVCrawler,  "pages": PAGES},
    {"name": "ITviec", "class": ITviecCrawler, "pages": PAGES},
    {"name": "VietnamWorks", "class": VietnamWorksCrawler, "pages": PAGES},
]

def send_telegram_notification(text: str):
    """Gửi thông báo qua Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ Bỏ qua gửi Telegram do thiếu TOKEN hoặc CHAT_ID trong .env")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Đã gửi thông báo Telegram thành công.")
        else:
            logger.error(f"❌ Lỗi gửi Telegram: {response.text}")
    except Exception as e:
        logger.error(f"❌ Exception khi gửi Telegram: {e}")

def run_pipeline():
    logger.info("=" * 55)
    logger.info("🤖 FULL PIPELINE: CRAWL → NLP → GEO → DB")
    logger.info("=" * 55)

    all_jobs = []

    # ── 1. CRAWL ──────────────────────────────────────────
    for cfg in CRAWLERS:
        logger.info(f"\n🌐 Crawl: {cfg['name']}")
        try:
            crawler = cfg["class"](
                max_pages=cfg["pages"], headless=HEADLESS
            )
            jobs = crawler.crawl()
            all_jobs.extend(jobs)
            logger.info(f"   ✅ {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"   ❌ Lỗi: {e}")

    logger.info(f"\n📦 Raw: {len(all_jobs)} jobs")

    # Nếu không có job nào thì dừng
    if not all_jobs:
        logger.warning("⚠️ Không lấy được job nào! Bỏ qua các bước tiếp theo.")
        send_telegram_notification("⚠️ Pipeline hoàn tất nhưng *KHÔNG* thu thập được Job nào!")
        return

    # ── 2. CLEAN ──────────────────────────────────────────
    cleaner = DataCleaner()
    df = cleaner.clean([job.to_dict() for job in all_jobs])
    logger.info(f"🧹 Clean: {len(df)} jobs")

    # ── 3. NLP SKILLS ─────────────────────────────────────
    logger.info(f"\n🧠 NLP Processing...")
    extractor = SkillExtractor()
    df = extractor.process_dataframe(df)
    has_skills = df["skills_final"].apply(
        lambda x: bool(str(x).strip()) and str(x) != "nan"
    ).sum()
    logger.info(f"   ✅ {has_skills}/{len(df)} jobs có skills")

    # ── 4. GEOCODING ──────────────────────────────────────
    logger.info(f"\n🗺️  Geocoding locations...")
    geocoder = Geocoder(use_api=True)
    df = geocoder.geocode_dataframe(df)

    # Preview geocoding
    logger.info("\n📍 Preview tọa độ:")
    sample = df[["location", "latitude", "longitude",
                 "geocoding_confidence"]].drop_duplicates(
        subset=["location"]
    ).head(8)
    for _, row in sample.iterrows():
        conf_icon = "✅" if row["geocoding_confidence"] >= 0.8 else "⚠️"
        logger.info(f"   {conf_icon} {str(row['location']):<25} "
              f"→ ({row['latitude']:.4f}, {row['longitude']:.4f})")

    # ── 5. LƯU CSV ────────────────────────────────────────
    df.to_csv("jobs_final.csv", index=False, encoding="utf-8-sig")
    logger.info(f"\n💾 Đã lưu: jobs_final.csv")

    # ── 6. LƯU SQL SERVER ─────────────────────────────────
    logger.info(f"\n🗄️  Lưu vào SQL Server...")

    records = df.to_dict("records")
    for r in records:
        r["skills"] = r.get("skills_final", "")

    db_total = 0
    stats = {"inserted": 0, "skipped": 0, "errors": 0}
    try:
        with DBHandler() as db:
            stats = db.insert_jobs(records)
            db_total = db.count_jobs()
            logger.info(f"   ✅ Inserted : {stats['inserted']}")
            logger.info(f"   ⏭️  Skipped  : {stats['skipped']}")
            logger.info(f"   ❌ Errors   : {stats['errors']}")
            logger.info(f"\n📊 Tổng DB  : {db_total} jobs")
    except Exception as e:
        logger.error(f"Lỗi khi lưu Database: {e}")

    logger.info("\n" + "=" * 55)
    logger.info("✅ FULL PIPELINE HOÀN TẤT!")
    logger.info("=" * 55)

    # Gửi thông báo
    msg = (
        f"🤖 *Job Bot Report*\n\n"
        f"✅ *Pipeline Completed!*\n"
        f"📦 Cào được: {len(all_jobs)} jobs\n"
        f"🧹 Sau khi clean: {len(df)} jobs\n"
        f"🧠 Có kỹ năng (NLP): {has_skills} jobs\n\n"
        f"🗄️ *Database Stats:*\n"
        f"➕ Inserted: {stats.get('inserted', 0)}\n"
        f"⏭️ Skipped (Trùng): {stats.get('skipped', 0)}\n"
        f"❌ Errors: {stats.get('errors', 0)}\n"
        f"📊 Tổng trong DB: {db_total} jobs"
    )
    send_telegram_notification(msg)

def main():
    # Kiểm tra nếu người dùng truyền tham số 'now' thì chạy luôn 1 lần
    if len(sys.argv) > 1 and sys.argv[1] == "now":
        logger.info("▶️ Chạy lập tức theo lệnh thủ công (manual run)...")
        run_pipeline()
        return

    logger.info(f"⏳ Khởi động Scheduler. Bot sẽ tự động chạy vào lúc {SCHEDULE_TIME} mỗi ngày.")
    logger.info("💡 Mẹo: Chạy 'python main.py now' để bắt đầu ngay lập tức không cần đợi.")
    
    # Lên lịch chạy
    schedule.every().day.at(SCHEDULE_TIME).do(run_pipeline)

    # Vòng lặp chờ
    while True:
        schedule.run_pending()
        time.sleep(60) # Kiểm tra mỗi phút

if __name__ == "__main__":
    main()
    