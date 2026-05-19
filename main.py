# main.py
import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
import requests
import schedule
import json
from dotenv import load_dotenv

from crawler.topcv_crawler import TopCVCrawler
from crawler.itviec_crawler import ITviecCrawler
from crawler.vietnamworks_crawler import VietnamWorksCrawler
from cleaner.data_cleaner import DataCleaner
from cleaner.skill_extractor import SkillExtractor
from geocoding import geocoder
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
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

# Đọc cấu hình từ .env hoặc lấy giá trị mặc định
HEADLESS = os.getenv("HEADLESS", "True").lower() in ("true", "1", "yes", "t")
PAGES = int(os.getenv("CRAWL_PAGES", "2"))
SCHEDULE_TIME = os.getenv("CRAWL_SCHEDULE_TIME", "00:00")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CRAWLERS = [
    {"name": "TopCV", "class": TopCVCrawler, "pages": PAGES},
    {"name": "ITviec", "class": ITviecCrawler, "pages": PAGES},
    {"name": "VietnamWorks", "class": VietnamWorksCrawler, "pages": PAGES},
]

BOT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "bot_config.json"
)


def load_source_config(source_name: str) -> dict:
    defaults = {
        "facebook": {
            "enabled": True,
            "max_posts_per_group": 5,
            "max_groups_per_session": 3,
            "max_days_old": 3,
        },
        "topcv": {"enabled": True, "max_pages": PAGES, "headless": True},
        "itviec": {"enabled": True, "max_pages": 1, "headless": True},
        "vietnamworks": {"enabled": True, "max_pages": PAGES, "headless": True},
    }

    try:
        with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}

    source_key = source_name.lower()
    source_config = (
        raw.get(source_key, {}) if isinstance(raw.get(source_key), dict) else {}
    )
    return {**defaults.get(source_key, {}), **source_config}


def send_telegram_notification(text: str):
    """Gửi thông báo qua Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ Bỏ qua gửi Telegram do thiếu TOKEN hoặc CHAT_ID trong .env")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Đã gửi thông báo Telegram thành công.")
        else:
            logger.error(f"❌ Lỗi gửi Telegram: {response.text}")
    except Exception as e:
        logger.error(f"❌ Exception khi gửi Telegram: {e}")


def run_pipeline(target_bot=None):
    logger.info("=" * 55)
    logger.info(
        f"🤖 FULL PIPELINE: CRAWL → NLP → GEO → DB | Target: {target_bot or 'ALL'}"
    )
    logger.info("=" * 55)

    db_handler = DBHandler()
    db_handler.connect()

    if target_bot and target_bot.lower() == "facebook":
        facebook_config = load_source_config("facebook")
        if facebook_config.get("enabled", True) is False:
            logger.warning("⚠️ Facebook crawler đang bị tắt trong cấu hình riêng.")
            db_handler.close()
            return

        logger.info("\n🌐 Running Facebook Crawler...")
        db_handler.update_task_progress("facebook", "running", 0, 0, max_pages=1)
        try:
            from crawler.facebook_crawler import FacebookCrawler

            crawler = FacebookCrawler()

            def fb_progress_cb(current_group, total_groups, current_count):
                db_handler.update_task_progress(
                    "facebook",
                    "running",
                    current_count,
                    current_group,
                    max_pages=total_groups,
                )

            stats = crawler.crawl_and_save(progress_callback=fb_progress_cb)
            logger.info(f"   ✅ Facebook Crawler finished. Stats: {stats}")
            # Ghi nhận hoàn thành thành công
            db_handler.update_task_progress(
                "facebook", "completed", stats.get("inserted", 0), stats.get("total", 0)
            )
            # Send notification
            msg = (
                f"🤖 *Facebook Bot Report*\n\n"
                f"✅ *Crawl Completed!*\n"
                f"📦 Cào được: {stats.get('total', 0)} posts\n"
                f"🚫 Bài bị lọc (Spam): {stats.get('spam', 0)}\n"
                f"♻️ Bài trùng (Dup): {stats.get('duplicate', 0)}\n"
                f"🔀 Trùng nguồn khác (Cross-dup): {stats.get('cross_dup', 0)}\n"
                f"➕ Đã lưu mới: {stats.get('inserted', 0)} jobs"
            )
            send_telegram_notification(msg)
        except Exception as e:
            logger.error(f"❌ Facebook Crawler error: {e}")
            db_handler.update_task_progress(
                "facebook", "error", 0, 0, total_errors=1, error_log=str(e)
            )
        finally:
            db_handler.close()
        return

    all_jobs = []

    # ── 1. CRAWL ──────────────────────────────────────────
    active_crawlers = CRAWLERS
    if target_bot:
        active_crawlers = [
            c for c in CRAWLERS if c["name"].lower() == target_bot.lower()
        ]

    if not active_crawlers:
        logger.warning(f"⚠️ Không tìm thấy crawler cho target: {target_bot}")
        db_handler.close()
        return

    for cfg in active_crawlers:
        source_name = cfg["name"].lower()
        logger.info(f"\n🌐 Crawl: {cfg['name']}")
        source_config = load_source_config(source_name)
        if source_config.get("enabled", True) is False:
            logger.info(f"   ⏭️  Bỏ qua {cfg['name']} vì đã bị tắt trong cấu hình riêng")
            continue

        # Lấy max_pages cấu hình động từ database (nếu có), mặc định sử dụng cấu hình từ env (cfg["pages"])
        max_pages = db_handler.get_task_max_pages(
            source_name, default_val=source_config.get("max_pages", cfg["pages"])
        )
        logger.info(f"   ⚙️ Configured max_pages: {max_pages}")

        db_handler.update_task_progress(
            source_name, "running", 0, 0, max_pages=max_pages
        )
        try:
            crawler = cfg["class"](
                max_pages=max_pages, headless=source_config.get("headless", HEADLESS)
            )

            def make_progress_cb(src_name):
                def cb(current_page, total_pages, current_count):
                    db_handler.update_task_progress(
                        src_name,
                        "running",
                        current_count,
                        current_page,
                        max_pages=total_pages,
                    )

                return cb

            jobs = crawler.crawl(progress_callback=make_progress_cb(source_name))
            all_jobs.extend(jobs)
            logger.info(f"   ✅ {len(jobs)} jobs")
            db_handler.update_task_progress(
                source_name, "completed", len(jobs), max_pages
            )
        except Exception as e:
            logger.error(f"   ❌ Lỗi: {e}")
            db_handler.update_task_progress(
                source_name, "error", 0, 0, total_errors=1, error_log=str(e)
            )

    db_handler.close()

    logger.info(f"\n📦 Raw: {len(all_jobs)} jobs")

    # Nếu không có job nào thì dừng
    if not all_jobs:
        logger.warning("⚠️ Không lấy được job nào! Bỏ qua các bước tiếp theo.")
        send_telegram_notification(
            f"⚠️ Pipeline hoàn tất nhưng *KHÔNG* thu thập được Job nào cho {target_bot or 'ALL'}!"
        )
        return

    # ── 2. CLEAN ──────────────────────────────────────────
    cleaner = DataCleaner()
    df = cleaner.clean([job.to_dict() for job in all_jobs])
    logger.info(f"🧹 Clean: {len(df)} jobs")

    # ── 3. NLP SKILLS ─────────────────────────────────────
    logger.info(f"\n🧠 NLP Processing...")
    extractor = SkillExtractor()
    df = extractor.process_dataframe(df)
    has_skills = (
        df["skills_final"]
        .apply(lambda x: bool(str(x).strip()) and str(x) != "nan")
        .sum()
    )
    logger.info(f"   ✅ {has_skills}/{len(df)} jobs có skills")

    # ── 4. GEOCODING ──────────────────────────────────────
    logger.info(f"\n🗺️  Geocoding locations...")
    df = geocoder.geocode_dataframe(df)

    # Preview geocoding
    logger.info("\n📍 Preview tọa độ:")
    sample = (
        df[["location", "latitude", "longitude", "geocoding_confidence"]]
        .drop_duplicates(subset=["location"])
        .head(8)
    )
    for _, row in sample.iterrows():
        conf_icon = "✅" if row["geocoding_confidence"] >= 0.8 else "⚠️"
        logger.info(
            f"   {conf_icon} {str(row['location']):<25} "
            f"→ ({row['latitude']:.4f}, {row['longitude']:.4f})"
        )

    # ── 5. LƯU CSV ────────────────────────────────────────
    df.to_csv("jobs_final.csv", index=False, encoding="utf-8-sig")
    logger.info(f"\n💾 Đã lưu: jobs_final.csv")

    # ── 6. LƯU SQL SERVER ─────────────────────────────────
    logger.info(f"\n🗄️  Lưu vào SQL Server...")

    records = df.to_dict("records")
    for r in records:
        r["skills"] = r.get("skills_final", "")
        # Đảm bảo posted_date được truyền đúng (không phải NaN)
        pd_val = r.get("posted_date")
        if pd_val is not None:
            import math

            try:
                if isinstance(pd_val, float) and math.isnan(pd_val):
                    r["posted_date"] = None
            except TypeError:
                pass

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
        f"🤖 *Job Bot Report ({target_bot or 'ALL'})*\n\n"
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
        target = sys.argv[2] if len(sys.argv) > 2 else None
        logger.info(
            f"▶️ Chạy lập tức theo lệnh thủ công (manual run) cho target: {target or 'ALL'}..."
        )
        run_pipeline(target)
        return

    logger.info(
        f"⏳ Khởi động Scheduler. Bot sẽ tự động chạy vào lúc {SCHEDULE_TIME} mỗi ngày."
    )
    logger.info(
        "💡 Mẹo: Chạy 'python main.py now' để bắt đầu ngay lập tức không cần đợi."
    )

    # Lên lịch chạy
    schedule.every().day.at(SCHEDULE_TIME).do(run_pipeline)

    # Vòng lặp chờ
    while True:
        schedule.run_pending()
        time.sleep(60)  # Kiểm tra mỗi phút


if __name__ == "__main__":
    main()
