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


# ================================================================
# FAILOVER — Phát hiện bị chặn & tự động chuyển crawler
# ================================================================

class BlockSignal(Exception):
    """Raise khi phát hiện crawler bị chặn."""
    def __init__(self, source: str, reason: str):
        self.source = source
        self.reason = reason
        super().__init__(f"[{source}] Bị chặn: {reason}")


class BlockDetector:
    """Theo dõi dấu hiệu bị chặn: trang trống liên tiếp, timeout liên tiếp."""
    THRESHOLD = 3

    def __init__(self):
        self._empty: dict = {}
        self._timeout: dict = {}

    def check_empty_results(self, job_count: int, source: str):
        if job_count == 0:
            self._empty[source] = self._empty.get(source, 0) + 1
            if self._empty[source] >= self.THRESHOLD:
                raise BlockSignal(source, f"{self._empty[source]} trang liên tiếp không có job")
        else:
            self._empty[source] = 0

    def on_timeout(self, source: str):
        self._timeout[source] = self._timeout.get(source, 0) + 1
        if self._timeout[source] >= self.THRESHOLD:
            raise BlockSignal(source, f"{self._timeout[source]} timeout liên tiếp")


class FailoverManager:
    """Chạy từng crawler, tự động skip khi bị chặn và chuyển sang cái tiếp theo."""

    def __init__(self, crawlers: list):
        self.queue = list(crawlers)
        self.blocked: set = set()
        self.switch_events: list = []
        self.jobs_per_source: dict = {}

    def run(self, execute_fn) -> tuple:
        """
        Trả về (report_dict, all_jobs).
        execute_fn(cfg) -> list[JobModel], có thể raise BlockSignal hoặc Exception.
        """
        all_jobs = []
        for cfg in self.queue:
            source = cfg["name"].lower()
            if source in self.blocked:
                continue
            try:
                jobs = execute_fn(cfg) or []
                all_jobs.extend(jobs)
                self.jobs_per_source[source] = len(jobs)
            except BlockSignal as bs:
                self._block(source, bs.reason, self.jobs_per_source.get(source, 0))
            except Exception as e:
                self._block(source, f"{type(e).__name__}: {str(e)[:80]}", self.jobs_per_source.get(source, 0))

        report = {
            "blocked_sources": list(self.blocked),
            "switch_events": self.switch_events,
            "jobs_per_source": self.jobs_per_source,
            "total_jobs": len(all_jobs),
        }
        return report, all_jobs

    def _block(self, source: str, reason: str, jobs_so_far: int):
        self.blocked.add(source)
        self.jobs_per_source[source] = jobs_so_far
        self.switch_events.append({"source": source, "reason": reason, "jobs_before": jobs_so_far})
        logger.warning(
            f"🚫 [{source}] BỊ CHẶN: {reason} | "
            f"Jobs trước khi block: {jobs_so_far} | Chuyển sang crawler tiếp theo..."
        )


def _format_failover_msg(report: dict) -> str:
    if not report["blocked_sources"]:
        return ""
    blocked = report["blocked_sources"]
    total = len(report["jobs_per_source"])
    lines = [
        f"\n⚠️ *Failover:* {len(blocked)}/{total} nguồn bị chặn",
        f"🚫 Bị chặn: {', '.join(blocked)}",
    ]
    for ev in report["switch_events"]:
        lines.append(f"   • [{ev['source']}] {ev['reason']}")
    return "\n".join(lines)

# Đọc cấu hình từ .env hoặc lấy giá trị mặc định
HEADLESS = os.getenv("HEADLESS", "False").lower() in ("true", "1", "yes", "t")
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
        "topcv": {"enabled": True, "max_pages": 1, "max_jobs": 10, "headless": False},
        "itviec": {"enabled": True, "max_pages": 1, "max_jobs": 10, "headless": False},
        "vietnamworks": {"enabled": True, "max_pages": 1, "max_jobs": 10, "headless": False},
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


def jobs_to_records(jobs: list) -> list[dict]:
    records = []
    for job in jobs:
        if hasattr(job, "to_dict"):
            records.append(job.to_dict())
        elif hasattr(job, "dict"):
            records.append(job.dict())
        elif hasattr(job, "model_dump"):
            records.append(job.model_dump())
        else:
            records.append(vars(job))
    return records


def geocode_and_save_jobs(jobs: list, source_name: str) -> dict:
    """Luu du lieu theo flow test: JobModel -> dict -> geocode -> DB."""
    if not jobs:
        return {"inserted": 0, "skipped": 0, "errors": 0, "total": 0}

    records = jobs_to_records(jobs)
    logger.info(f"   Geocoding {len(records)} jobs ({source_name})...")
    df = pd.DataFrame(records)
    df = geocoder.geocode_dataframe(df)
    records_with_geo = df.to_dict("records")

    with DBHandler() as db:
        stats = db.insert_jobs(records_with_geo)
        stats["total"] = len(records_with_geo)
        logger.info(
            f"   DB {source_name}: inserted={stats['inserted']} | skipped={stats['skipped']} | errors={stats['errors']}"
        )
        return stats


def run_pipeline(target_bot=None, force_headless=False):
    logger.info("=" * 55)
    logger.info(
        f"🤖 FULL PIPELINE: CRAWL → NLP → GEO → DB | Target: {target_bot or 'ALL'} | Force Headless: {force_headless}"
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

            crawler = FacebookCrawler(
                max_posts_per_group=facebook_config.get("max_posts_per_group", 5),
                max_groups_per_session=facebook_config.get("max_groups_per_session", 3),
            )

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

    # ── 1. CRAWL với Failover tự động ─────────────────────
    active_crawlers = CRAWLERS
    if target_bot:
        active_crawlers = [
            c for c in CRAWLERS if c["name"].lower() == target_bot.lower()
        ]

    if not active_crawlers:
        logger.warning(f"⚠️ Không tìm thấy crawler cho target: {target_bot}")
        db_handler.close()
        return

    manager = FailoverManager(active_crawlers)

    def execute_crawler(cfg: dict) -> list:
        """Chạy một crawler, tích hợp BlockDetector để phát hiện bị chặn."""
        source_name = cfg["name"].lower()
        source_config = load_source_config(source_name)

        if source_config.get("enabled", True) is False:
            logger.info(f"   ⏭️  Bỏ qua {cfg['name']} vì đã bị tắt trong cấu hình riêng")
            return []

        max_pages = db_handler.get_task_max_pages(
            source_name, default_val=source_config.get("max_pages", cfg["pages"])
        )
        logger.info(f"   ⚙️ Configured max_pages: {max_pages}")
        db_handler.update_task_progress(source_name, "running", 0, 0, max_pages=max_pages)

        max_jobs = source_config.get("max_jobs", 10)
        logger.info(f"   ⚙️ Configured max_jobs: {max_jobs}")

        detector = BlockDetector()

        def make_progress_cb(src_name):
            def cb(current_page, total_pages, current_count):
                # Kiểm tra dấu hiệu bị chặn qua số job trên mỗi trang
                detector.check_empty_results(current_count, src_name)
                db_handler.update_task_progress(
                    src_name, "running", current_count, current_page, max_pages=total_pages,
                )
            return cb

        # Ép chạy ẩn danh nếu được yêu cầu từ tiến trình nền của Server
        headless_val = True if force_headless else source_config.get("headless", HEADLESS)
        logger.info(f"   ⚙️ Run mode headless: {headless_val}")

        crawler_obj = cfg["class"](
            max_pages=max_pages,
            headless=headless_val,
            max_jobs=max_jobs,
        )

        try:
            jobs = crawler_obj.crawl(progress_callback=make_progress_cb(source_name))
        except BlockSignal:
            raise  # FailoverManager sẽ xử lý
        except Exception as e:
            err_msg = str(e)
            # Timeout liên tiếp → coi là bị chặn
            if any(t in err_msg for t in ("Timeout", "timeout", "ERR_TIMED_OUT", "Navigation timeout")):
                detector.check_timeout_streak(source_name)
            raise  # FailoverManager treat as block

        stats = geocode_and_save_jobs(jobs, source_name)
        db_handler.update_task_progress(
            source_name, "completed",
            stats.get("inserted", 0), len(jobs),
            total_errors=stats.get("errors", 0), max_pages=max_pages,
        )
        return jobs

    # Chạy tất cả crawlers — tự động failover khi bị chặn
    report, all_jobs = manager.run(execute_crawler)

    # Cập nhật DB status "failed" cho các source bị chặn để tránh vi phạm CHECK constraint CHK_task_status
    for blocked_src in report["blocked_sources"]:
        try:
            db_handler.update_task_progress(blocked_src, "failed", 0, 0, total_errors=1, error_log="Blocked by anti-bot detection")
        except Exception:
            pass

    db_handler.close()

    logger.info(f"\n📦 Raw: {len(all_jobs)} jobs")

    # Gửi thông báo Telegram nếu có failover
    failover_msg = _format_failover_msg(report)
    if failover_msg:
        send_telegram_notification(
            f"🤖 *Crawler Pipeline ({target_bot or 'ALL'})*\n"
            f"📦 Tổng jobs: {report['total_jobs']}"
            + failover_msg
        )

    return

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
