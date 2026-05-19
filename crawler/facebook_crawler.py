# crawler/facebook_crawler.py
"""
Production-stable Facebook Group Job Crawler.
Upgrades: See More, Incremental, Selector Fallback, Retry, Persistent Cache, Logging
"""

import time
import random
import logging
import logging.handlers
import hashlib
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# pyrefly: ignore [missing-import]
from playwright.sync_api import sync_playwright, Page, Locator

from models.job_model import JobModel
from cleaner.facebook_cleaner import FacebookCleaner
from cleaner.facebook_nlp import FacebookNLP
from cleaner.duplicate_detector import DuplicateDetector
from cleaner.cross_source_detector import CrossSourceDetector
from database.facebook_db import FacebookDB


# ================================================================
# LOGGING — File riêng + Console
# ================================================================
def _setup_logger() -> logging.Logger:
    log = logging.getLogger("facebook_crawler")
    if log.handlers:
        return log
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

    # Console handler (INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    # File handler (DEBUG) - xoay file 5MB, giữ 5 bản
    os.makedirs("logs", exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        "logs/facebook_crawler.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    log.addHandler(ch)
    log.addHandler(fh)
    return log


logger = _setup_logger()


# ================================================================
# CONFIG
# ================================================================
# Config from bot_config.json instead of hardcoded
def load_bot_config():
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "bot_config.json"
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
            config = (
                raw_config.get("facebook")
                if isinstance(raw_config.get("facebook"), dict)
                else raw_config
            )
            policy = config.get("moderation_policy") or {}
            mode = str(policy.get("mode", "manual")).lower()
            policy["mode"] = mode if mode in ("auto", "manual") else "manual"
            policy["learn_from_admin"] = bool(policy.get("learn_from_admin", True))
            config["moderation_policy"] = policy
            return config
    except Exception as e:
        logger.warning(f"Không thể đọc bot_config.json, sử dụng mặc định: {e}")
        return {
            "max_posts_per_group": 5,
            "max_groups_per_session": 1,
            "max_days_old": 3,
            "facebook_groups": [],
            "moderation_policy": {
                "mode": "manual",
                "learn_from_admin": True,
            },
        }


# Selector fallback system — thử theo thứ tự
ARTICLE_SELECTORS = [
    "div[role='article']",
    "div[data-pagelet*='FeedUnit']",
    "div[data-ft]",
    "div[role='feed'] > div",
]
CONTENT_SELECTORS = [
    "div[data-ad-comet-preview='message']",
    "div[dir='auto']",
    "div[data-ad-preview='message']",
    "div[role='article'] div[dir='auto']",
]
LINK_SELECTORS = [
    "a[href*='permalink']",
    "a[href*='/posts/']",
    "a[role='link'][href*='groups']",
]
TIME_SELECTORS = ["abbr", "span[role='link']", "a[role='link'] span"]
AUTHOR_SELECTORS = [
    "strong a",
    "a[role='link'] strong",
    "span[dir='auto'] a[role='link']",
]
SEE_MORE_TEXTS = ["Xem thêm", "See more", "Xem thêm nội dung"]

RECRUITMENT_KEYWORDS = [
    "tuyển",
    "tuyển dụng",
    "tuyển gấp",
    "cần tuyển",
    "cần người",
    "việc làm",
    "part-time",
    "full-time",
    "parttime",
    "fulltime",
    "lương",
    "thu nhập",
    "ca tối",
    "ca ngày",
    "phục vụ",
    "shipper",
    "bán hàng",
    "nhân viên",
    "thực tập sinh",
    "fresher",
    "cộng tác viên",
]
SPAM_KEYWORDS = [
    "thu nhập khủng",
    "việc nhẹ lương cao",
    "không cần kinh nghiệm, thu nhập",
    "đa cấp",
    "cọc tiền",
    "tuyển ctv online không cần làm việc",
    "kiếm tiền tại nhà",
]

# Incremental state file
STATE_FILE = "data/fb_crawl_state.json"


# ================================================================
# HELPER: RETRY DECORATOR
# ================================================================
def _retry(max_attempts: int = 3, delay: float = 1.5):
    """Decorator: retry một function nếu nó raise exception."""

    def decorator(fn):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts:
                        logger.warning(
                            f"[retry] {fn.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        return None
                    logger.debug(
                        f"[retry] {fn.__name__} attempt {attempt} failed: {e} — retrying..."
                    )
                    time.sleep(delay * attempt)

        return wrapper

    return decorator


# ================================================================
# INCREMENTAL STATE MANAGER
# ================================================================
class CrawlStateManager:
    """Lưu/load trạng thái crawl tránh recrawl bài cũ."""

    def __init__(self, path: str = STATE_FILE):
        self.path = path
        self._state: Dict = self._load()

    def _load(self) -> Dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    def get_seen_ids(self, group_url: str) -> set:
        return set(self._state.get(group_url, {}).get("seen_ids", []))

    def mark_seen(self, group_url: str, post_ids: List[str]):
        if group_url not in self._state:
            self._state[group_url] = {"seen_ids": [], "last_crawled": ""}
        existing = set(self._state[group_url]["seen_ids"])
        existing.update(post_ids)
        # Giới hạn 500 IDs mỗi group để tránh file phình to
        self._state[group_url]["seen_ids"] = list(existing)[-500:]
        self._state[group_url]["last_crawled"] = datetime.utcnow().isoformat()
        self.save()


# ================================================================
# FACEBOOK CRAWLER
# ================================================================
class FacebookCrawler:
    SOURCE_NAME = "facebook"

    def __init__(
        self,
        max_posts_per_group: int = None,
        max_groups_per_session: int = None,
        hours_lookback: int = 24,
    ):
        config = load_bot_config()
        self.max_posts = (
            max_posts_per_group
            if max_posts_per_group is not None
            else config.get("max_posts_per_group", 5)
        )
        self.max_groups = (
            max_groups_per_session
            if max_groups_per_session is not None
            else config.get("max_groups_per_session", 3)
        )
        self.hours_lookback = hours_lookback
        self.max_days_old = config.get("max_days_old", 3)
        self.facebook_groups = config.get("facebook_groups", [])

        self.cleaner = FacebookCleaner()
        self.nlp = FacebookNLP()
        self.detector = DuplicateDetector(similarity_threshold=0.85)
        self.cross_det = CrossSourceDetector(threshold=0.85)  # Cross-source
        self.state = CrawlStateManager()
        self.jobs: List[JobModel] = []

        # Persistent caches
        self._load_fingerprints_from_db()
        self._load_cross_detector_baseline()

    # ============================================================
    # PERSISTENT DUPLICATE CACHE (Upgrade #6)
    # ============================================================

    def _load_verified_entities(self):
        """Tải các thực thể đã xác thực từ cơ sở dữ liệu làm bộ nhớ cho cleaner."""
        self.verified_entities = {"phone": {}, "address": {}}
        try:
            with FacebookDB() as db:
                self.verified_entities = db.get_verified_entities()
                total_learned = len(self.verified_entities.get("phone", {})) + len(
                    self.verified_entities.get("address", {})
                )
                logger.info(
                    f"🧠 [Active-Learning] Loaded {total_learned} verified entities from DB loop."
                )
        except Exception as e:
            logger.warning(f"Failed to load verified entities: {e}")

    def _load_fingerprints_from_db(self):
        """Load fingerprints từ DB để DuplicateDetector nhớ bài cũ sau restart."""
        try:
            with FacebookDB() as db:
                db.create_tables()
                fingerprints = db.get_all_fingerprints()
                if fingerprints:
                    self.detector.load_existing(fingerprints)
                    logger.info(
                        f"[cache] Loaded {len(fingerprints)} fingerprints from DB"
                    )
        except Exception as e:
            logger.warning(f"[cache] Could not load fingerprints: {e}")

    def _load_cross_detector_baseline(self):
        """Load recent jobs từ DB để CrossSourceDetector nhận ra duplicate giữa các nguồn."""
        try:
            with FacebookDB() as db:
                db.create_tables()
                jobs = db.get_jobs_for_cross_detection(limit=2000)
                if jobs:
                    self.cross_det.load_from_db(jobs)
        except Exception as e:
            logger.warning(f"[cross_cache] Could not load baseline: {e}")

    # ============================================================
    # MAIN PIPELINE
    # ============================================================

    def crawl_and_save(self, progress_callback=None) -> dict:
        """Pipeline hoàn chỉnh: Crawl → NLP Spam → Duplicate → DB → Trust Score."""
        raw_jobs = self.crawl(progress_callback=progress_callback)
        if not raw_jobs:
            return {
                "total": 0,
                "spam": 0,
                "duplicate": 0,
                "skipped_db": 0,
                "inserted": 0,
                "errors": 0,
            }

        stats = {
            "total": len(raw_jobs),
            "spam": 0,
            "duplicate": 0,
            "cross_dup": 0,
            "job_seeking": 0,
            "skipped_db": 0,
            "inserted": 0,
            "errors": 0,
            "groups": {},
        }

        # Set lưu fingerprint trong session — chống lưu 2 lần cùng phiên
        session_fingerprints: set = set()

        with FacebookDB() as db:
            db.create_tables()

            for job in raw_jobs:
                group_id = getattr(job, "group_id", "unknown")
                group_name = getattr(job, "group_name", "unknown")

                if group_id not in stats["groups"]:
                    stats["groups"][group_id] = {
                        "name": group_name,
                        "total": 0,
                        "spam": 0,
                        "dup": 0,
                        "inserted": 0,
                    }
                g = stats["groups"][group_id]
                g["total"] += 1

                desc = job.description or ""

                # 2a. Spam check
                is_spam, _, reason = self.nlp.is_spam(desc)
                if is_spam:
                    logger.debug(f"🚫 SPAM [{group_name}]: {reason[:60]}")
                    stats["spam"] += 1
                    g["spam"] += 1
                    continue

                # 2b. Post-type check: lọc bài TÌM VIỆC
                is_recruiting, type_reason = self.nlp.is_recruiting_post(desc)
                if not is_recruiting:
                    logger.debug(f"🔍 JOB_SEEKING [{group_name}]: {type_reason[:80]}")
                    stats["job_seeking"] += 1
                    g.setdefault("job_seeking", 0)
                    g["job_seeking"] += 1
                    continue

                # 2c. Session-level dedup (cùng phiên, tránh lưu 2 lần trong 1 lần chạy)
                fp = getattr(job, "fingerprint", "") or ""
                if fp and fp in session_fingerprints:
                    logger.debug(
                        f"♻️  SESSION-DUP [{group_name}]: fingerprint đã có trong phiên"
                    )
                    stats["duplicate"] += 1
                    g["dup"] += 1
                    continue

                # 2d. Same-source duplicate check (fast hash/phone/cosine)
                phone = getattr(job, "contact_phone", "") or ""
                is_dup, method, sim = self.detector.is_duplicate(desc, phone)
                if is_dup:
                    logger.debug(f"♻️  DUP [{group_name}]: {method} sim={sim:.2f}")
                    stats["duplicate"] += 1
                    g["dup"] += 1
                    continue

                # 2d. Extract normalized features cho cross-source check
                job_dict = {
                    "job_id": getattr(job, "external_id", ""),
                    "source": "facebook",
                    "title": getattr(job, "title", ""),
                    "company": getattr(job, "company", ""),
                    "location": getattr(job, "location", ""),
                    "salary": getattr(job, "salary", ""),
                    "phone": phone,
                    "description": desc,
                }
                features = self.cross_det.extract_features(job_dict)

                # 2e. Cross-source duplicate check
                is_cross_dup, cross_score, matched_id = self.cross_det.is_duplicate(
                    job_dict
                )
                if is_cross_dup:
                    logger.debug(
                        f"🔀 CROSS-DUP [{group_name}]: score={cross_score:.2f} vs {matched_id}"
                    )
                    stats["cross_dup"] += 1
                    g.setdefault("cross_dup", 0)
                    g["cross_dup"] += 1
                    continue

                # 2f. Insert — enriched với normalized fields
                job_data = {
                    "title": getattr(job, "title", ""),
                    "company": getattr(job, "company", ""),
                    "description": desc,
                    "salary": getattr(job, "salary", ""),
                    "location": getattr(job, "location", ""),
                    "skills": ", ".join(getattr(job, "skills", []) or []),
                    "phone": phone[:50],
                    "job_type": getattr(job, "job_type", ""),
                    "requirements": getattr(job, "requirements", ""),
                    "job_url": getattr(job, "job_url", ""),
                    "post_id": getattr(job, "external_id", ""),
                    "posted_date": getattr(job, "posted_date", ""),
                    "source_group": group_name,
                    "quality_score": self.nlp.quality_score(desc),
                    # Normalized fields for cross-source future queries
                    "normalized_title": features.norm_title,
                    "normalized_location": features.norm_location,
                    "salary_min": features.salary_min or None,
                    "salary_max": features.salary_max or None,
                    "fingerprint_hash": features.fingerprint,
                }
                try:
                    ok = db.insert_facebook_job(job_data)
                    if ok:
                        stats["inserted"] += 1
                        g["inserted"] += 1
                        if fp:
                            session_fingerprints.add(fp)  # Đăng ký vào session cache
                        logger.debug(
                            f"✅ INSERT [{group_name}]: {job_data['title'][:50]}"
                        )
                    else:
                        stats["skipped_db"] += 1
                except Exception as e:
                    logger.error(f"❌ DB error [{group_name}]: {e}")
                    stats["errors"] += 1

            # 3. Trust Score
            for gid, g in stats["groups"].items():
                if g["total"] == 0:
                    continue
                spam_r = g["spam"] / g["total"]
                dup_r = g["dup"] / g["total"]
                trust = round(1.0 - spam_r * 0.5 - dup_r * 0.3, 2)
                pri = "high" if trust > 0.7 else "normal" if trust > 0.4 else "low"
                try:
                    db.upsert_group(
                        {
                            "group_id": gid,
                            "group_name": g["name"],
                            "group_url": gid,
                            "trust_score": trust,
                            "spam_ratio": round(spam_r, 3),
                            "duplicate_ratio": round(dup_r, 3),
                            "crawl_priority": pri,
                            "total_crawled": g["total"],
                            "total_spam": g["spam"],
                            "total_duplicate": g["dup"],
                        }
                    )
                    logger.info(f"📈 [{g['name']}] trust={trust} | {pri}")
                except Exception as e:
                    logger.warning(f"⚠️  upsert_group failed: {e}")

        logger.info(
            f"\n✅ done: total={stats['total']} | spam={stats['spam']} | "
            f"dup={stats['duplicate']} | skip_db={stats['skipped_db']} | "
            f"inserted={stats['inserted']} | errors={stats['errors']}"
        )
        return stats

    def _is_port_open(self, port=9222) -> bool:
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                return s.connect_ex(("127.0.0.1", port)) == 0
        except Exception:
            return False

    def _auto_launch_chrome(self) -> bool:
        if self._is_port_open(9222):
            logger.info("✅ Chrome is already running on port 9222")
            return True

        import os
        import subprocess
        import time

        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Google Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]

        chrome_path = None
        for path in chrome_paths:
            if os.path.exists(path):
                chrome_path = path
                break

        if not chrome_path:
            logger.error(
                "❌ Could not find Chrome executable automatically. Please open Chrome manually with port 9222."
            )
            return False

        logger.info(
            f"🚀 Launching Chrome at: {chrome_path} with debugging port 9222..."
        )
        user_data_dir = r"C:\ChromeProfile"
        os.makedirs(user_data_dir, exist_ok=True)

        cmd = [
            chrome_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}",
        ]

        try:
            # Chạy Chrome độc lập dưới dạng Popen
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Chờ 4 giây để Chrome khởi chạy và mở cổng
            for _ in range(8):
                time.sleep(0.5)
                if self._is_port_open(9222):
                    logger.info("✅ Chrome launched and listening on port 9222")
                    return True
            logger.warning("⚠️ Chrome launched but port 9222 is not responsive yet.")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to auto-launch Chrome: {e}")
            return False

    def crawl(self, progress_callback=None) -> List[JobModel]:
        """Attach Chrome qua CDP, crawl các groups đã chọn."""
        self._auto_launch_chrome()
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.connect_over_cdp("http://localhost:9222")
                logger.info("✅ Connected to existing Chrome session")
            except Exception as e:
                logger.error(f"❌ Cannot connect to Chrome: {e}")
                logger.info(
                    "💡 Run: chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\\ChromeProfile"
                )
                return []

            context = browser.contexts[0]
            page = context.new_page()
            self._setup_page(page)

            selected = self._select_groups()
            logger.info(f"📋 Session: {len(selected)} groups")

            for idx, group in enumerate(selected, 1):
                if progress_callback:
                    progress_callback(idx, len(selected), len(self.jobs))
                try:
                    group_jobs = self._crawl_single_group(page, group)
                    self.jobs.extend(group_jobs)
                    logger.info(f"✅ {group['name']}: +{len(group_jobs)} jobs")
                except Exception as e:
                    logger.error(f"❌ Error crawling {group['name']}: {e}")

                if group != selected[-1]:
                    self._human_delay(30, 75)

            # Long-run stability: clear state giữa session
            try:
                page.close()
            except Exception:
                pass

        logger.info(f"🏁 Crawl finished: {len(self.jobs)} total jobs")
        return self.jobs

    # ============================================================
    # CRAWL 1 GROUP
    # ============================================================

    def _crawl_single_group(self, page: Page, group: dict) -> List[JobModel]:
        jobs = []
        group_url = group["url"]
        seen_ids = self.state.get_seen_ids(group_url)
        new_ids = []

        logger.info(f"🌐 Group: {group['name']} | seen={len(seen_ids)} past IDs")

        # Navigate với retry
        if not self._safe_goto(page, group_url):
            return []

        # Human scroll — Upgrade #3: dùng locator thay page.content()
        logger.info("   ↓ Scrolling to load posts...")
        self._human_scroll(page)

        # (Đã loại bỏ _expand_see_more toàn trang để tránh click nhầm thanh sidebar)
        self._human_delay(1, 2)

        # Extract trực tiếp bằng locator (Upgrade #3)
        raw_posts = self._extract_posts_via_locator(page)
        logger.info(f"   → Found {len(raw_posts)} post containers")

        new_count = 0
        for post in raw_posts:
            if new_count >= self.max_posts:
                break

            post_id = post.get("post_id", "")

            # Incremental: skip bài đã thấy (Upgrade #2)
            if post_id and post_id in seen_ids:
                logger.debug(f"   ⏭ Skip seen: {post_id}")
                continue

            if not self._is_recruitment_post(post.get("content", "")):
                continue
            if self._is_spam_basic(post.get("content", "")):
                continue

            job = self._build_job_model(post, group)

            # --- Lọc bài đăng quá 3 ngày ---
            is_too_old = False
            if job.posted_date:
                try:
                    post_dt = datetime.strptime(job.posted_date, "%Y-%m-%d %H:%M:%S")
                    old_days = (datetime.now() - post_dt).days
                    if old_days > self.max_days_old:
                        logger.debug(f"   ⏭ Skip bài đăng cũ ({old_days} ngày trước)")
                        is_too_old = True
                except Exception:
                    pass

            if is_too_old:
                continue

            if job.title or job.description:
                jobs.append(job)
                new_count += 1
                if post_id:
                    new_ids.append(post_id)

            self._human_delay(0.8, 2.5)

        # Persist incremental state
        if new_ids:
            self.state.mark_seen(group_url, new_ids)

        return jobs

    # ============================================================
    # EXTRACT VIA LOCATOR — Upgrade #3
    # ============================================================

    def _extract_posts_via_locator(self, page: Page) -> List[Dict]:
        """Extract bài viết trực tiếp qua Playwright locator.
        FIX: Click 'Xem thêm' riêng cho từng bài trước khi đọc nội dung.
        """
        posts = []

        articles = self._find_articles(page)
        if articles is None:
            logger.warning("⚠️  No article selector worked for this page")
            try:
                os.makedirs("logs", exist_ok=True)
                page.screenshot(path="logs/error_no_articles.png")
                logger.warning(
                    "📸 Đã lưu ảnh màn hình lỗi tại logs/error_no_articles.png để kiểm tra"
                )
            except Exception as e:
                logger.debug(f"Could not take screenshot: {e}")
            return []

        count = articles.count()
        logger.debug(f"   → {count} articles found via locator")

        for i in range(count):
            try:
                article = articles.nth(i)

                # FIX: Click 'Xem thêm' ngay trong bài này trước khi đọc
                self._expand_see_more_article(article)

                post = self._parse_article_locator(article)
                if not post:
                    continue
                # Chống lỗi Facebook DOM tái tạo (Detached elements)
                try:
                    article.wait_for(state="attached", timeout=1500)
                except Exception:
                    logger.debug(
                        f"   ⚠️ Article #{i}: Element đã bị xóa/đổi bởi Facebook DOM, bỏ qua"
                    )
                    continue

                # FIX: Click 'Xem thêm' ngay trong bài này trước khi đọc
                self._expand_see_more_article(article)

                post = self._parse_article_locator(article)
                if not post:
                    logger.debug(f"   ⚠️ Article #{i}: Lấy từ Facebook bị Null/Empty!")
                    continue

                content = post.get("content", "")

                # FIX: Bỏ bài vẫn còn chứa nút "Xem thêm" (chưa expand được)
                see_more_still_present = any(
                    kw in content.lower()
                    for kw in ["xem thêm", "see more", "xem thêm nội dung"]
                )
                if see_more_still_present:
                    logger.debug(
                        f"   ⚠️ Article #{i}: vẫn còn 'Xem thêm', retry expand..."
                    )
                    self._expand_see_more_article(article)
                    post = self._parse_article_locator(article)
                    if not post:
                        continue
                    content = post.get("content", "")

                # Lọc bài quá ngắn hoặc vẫn còn từ khóa "Xem thêm"
                if len(content) >= 15:
                    posts.append(post)
                else:
                    logger.debug(
                        f"   ⏭ Article #{i}: content quá ngắn ({len(content)} chars), bỏ qua"
                    )

            except Exception as e:
                logger.debug(f"   Parse error article #{i}: {e}")

        return posts

    def _expand_see_more_article(self, article) -> int:
        """
        FIX CORE: Click nút 'Xem thêm' ngay bên trong một bài viết cụ thể.
        Tránh việc click toàn trang rồi bỏ sót bài load muộn.
        Trả về số nút đã click thành công.
        """
        expanded = 0
        for text in SEE_MORE_TEXTS:
            try:
                # Tìm nút Xem thêm trong phạm vi article này (không phải toàn trang)
                buttons = article.locator(f"text={text}")
                count = buttons.count()
                for i in range(min(count, 5)):
                    try:
                        btn = buttons.nth(i)
                        # Scroll bài vào viewport trước khi click
                        btn.scroll_into_view_if_needed(timeout=2000)
                        btn.click(timeout=2000, force=True)
                        expanded += 1
                        time.sleep(0.5)  # Chờ content expand
                    except Exception:
                        pass
            except Exception:
                pass
        return expanded

    def _find_articles(self, page: Page) -> Optional[Locator]:
        """Selector fallback: thử từng selector cho article container."""
        for selector in ARTICLE_SELECTORS:
            try:
                # Chờ tối đa 5 giây cho selector xuất hiện
                loc = page.locator(selector)
                try:
                    loc.first.wait_for(timeout=5000, state="attached")
                except Exception:
                    pass
                if loc.count() > 0:
                    logger.debug(
                        f"   ✓ Article selector: '{selector}' → {loc.count()} found"
                    )
                    return loc
                logger.debug(f"   ✗ Article selector failed: '{selector}'")
            except Exception as e:
                logger.debug(f"   ✗ Article selector error '{selector}': {e}")
        return None

    def _parse_article_locator(self, article: Locator) -> Optional[Dict]:
        """
        Parse 1 article qua locator.
        Dùng text_content() thay inner_text() để lấy TOÀN BỘ text kể cả phần
        bị ẩn bởi CSS 'Xem thêm' → giảm phụ thuộc vào việc click nút.
        """
        content = ""

        # ── Ưu tiên 1: Lấy bằng Selector chính xác ──────────────────────
        for sel in CONTENT_SELECTORS:
            try:
                el = article.locator(sel).first
                if el.count() > 0:
                    t = el.inner_text(timeout=1500).strip()
                    if t and len(t) > len(content):
                        content = t
            except Exception:
                continue

        # ── Ưu tiên 2: JS Evaluate (Nếu text vẫn quá ngắn) ──────────────
        if len(content) < 15:
            try:
                full_text = article.evaluate("""el => {
                    const divs = el.querySelectorAll("div[dir='auto']");
                    let best = '';
                    for (const d of divs) {
                        const t = (d.innerText || '').trim();
                        if (t.length > best.length) best = t;
                    }
                    return best;
                }""")
                if full_text and len(full_text.strip()) > len(content):
                    content = full_text.strip()
                    logger.debug(f"   [tc] Got {len(content)} chars via textContent")
            except Exception as e:
                logger.debug(f"   [tc] JS evaluate failed: {e}")

        # ── Ưu tiên 3: Fallback thủ công Playwright locator ──────────────
        if len(content) < 15:
            try:
                els = article.locator(
                    "div[dir='auto'], span[dir='auto'], div[data-ad-comet-preview='message']"
                )
                if els.count() > 0:
                    texts = []
                    for i in range(min(els.count(), 15)):
                        try:
                            t = els.nth(i).inner_text(timeout=1000).strip()
                            if t:
                                texts.append(t)
                        except Exception:
                            pass
                    if texts:
                        best_t = max(texts, key=len)
                        if len(best_t) > len(content):
                            content = best_t
            except Exception:
                pass

        # ── Ưu tiên 4: Cứu cánh cuối cùng - Lấy toàn bộ Text của Article ──
        if len(content) < 15:
            try:
                raw_all_text = article.inner_text(timeout=2000).strip()
                if len(raw_all_text) > len(content):
                    content = raw_all_text
                    logger.debug(
                        f"   [tc] Used raw article inner_text Fallback: {len(content)} chars"
                    )
            except Exception as e:
                logger.debug(f"   [tc] fallback 4 failed: {e}")
                pass

        if not content or len(content) < 15:
            logger.debug(
                f"   [tc] content empty or too short ({len(content)} chars), returning None"
            )
            return None

        # Post URL fallback
        post_url = ""
        post_id = ""
        for sel in LINK_SELECTORS:
            try:
                el = article.locator(sel).first
                if el.count() > 0:
                    href = el.get_attribute("href", timeout=1000) or ""
                    if href:
                        if not href.startswith("http"):
                            href = "https://www.facebook.com" + href
                        post_url = href
                        post_id = hashlib.md5(href.encode()).hexdigest()[:16]
                        break
            except Exception:
                continue

        # Author fallback - Lọc bỏ link nhóm hoặc bài viết để lấy đúng tên người đăng
        author = ""
        for sel in AUTHOR_SELECTORS:
            try:
                els = article.locator(sel)
                count = els.count()
                for j in range(count):
                    el = els.nth(j)
                    href = el.get_attribute("href") or ""
                    # Link của người đăng bài không bao giờ chứa "/groups/" hoặc "/permalink/"
                    if href and "/groups/" not in href and "/permalink/" not in href:
                        text = el.inner_text().strip()
                        if text and 2 < len(text) < 50:
                            author = text
                            break
                if author:
                    break
            except Exception:
                continue

        # Fallback cuối cùng nếu vẫn trống
        if not author:
            for sel in AUTHOR_SELECTORS:
                try:
                    el = article.locator(sel).first
                    if el.count() > 0:
                        text = el.inner_text().strip()
                        if text and len(text) < 50:
                            author = text
                            break
                except Exception:
                    continue

        # Time — ưu tiên lấy aria-label của <abbr> chứa thời gian thực
        posted_time = ""
        try:
            # Cách 1: abbr có aria-label (Facebook thường dùng cho timestamp)
            time_els = article.locator(
                "abbr[aria-label], abbr[data-utime], a[role='link'] abbr"
            )
            if time_els.count() > 0:
                aria = time_els.first.get_attribute("aria-label", timeout=1500) or ""
                data_utime = (
                    time_els.first.get_attribute("data-utime", timeout=500) or ""
                )
                if data_utime.isdigit():
                    # Unix timestamp → datetime
                    from datetime import timezone

                    posted_time = datetime.fromtimestamp(
                        int(data_utime), tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S")
                elif aria:
                    posted_time = aria  # vd: "17 May 2026 at 23:17"
                else:
                    posted_time = time_els.first.inner_text(timeout=1000).strip()
        except Exception:
            pass

        if not posted_time:
            for sel in TIME_SELECTORS:
                try:
                    el = article.locator(sel).first
                    if el.count() > 0:
                        aria = el.get_attribute("aria-label", timeout=500) or ""
                        posted_time = aria or el.inner_text(timeout=1000).strip()
                        if posted_time:
                            break
                except Exception:
                    continue

        # Cách 3: Quét trực tiếp nội dung văn bản thô ở phần đầu của article (Miễn dịch hoàn toàn với thay đổi DOM/SVG của Facebook)
        if not posted_time:
            try:
                import re

                raw_all_text = article.inner_text(timeout=1000).strip()
                if raw_all_text:
                    lines = [
                        line.strip()
                        for line in raw_all_text.split("\n")
                        if line.strip()
                    ]
                    time_patterns = [
                        r"^\d+\s*(?:phút|giờ|ngày|tuần|tháng|năm|h|m|d|w|y|giờ|giơ|gi\u1edd|ph\u00fat)(?:\s*trước)?$",
                        r"^(?:vừa\s*xong|hôm\s*qua|yesterday|just\s*now)$",
                        r"^\d{1,2}\s+tháng\s+\d{1,2}(?:\s+lúc\s+\d{1,2}:\d{2})?$",
                        r"^\d{1,2}\s+tháng\s+\d{1,2},\s+\d{4}(?:\s+lúc\s+\d{1,2}:\d{2})?$",
                        r"^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}(?:,\s*\d{4})?(?:\s+at\s+\d{1,2}:\d{2})?$",
                        r"^\d+\s*(?:h|m|d|g|ph)\b",
                    ]
                    # Quét 10 dòng đầu tiên vì thông tin thời gian luôn nằm ở tiêu đề bài viết
                    for line in lines[:10]:
                        if line in ["·", "•", "-", "–"]:
                            continue
                        matched = False
                        for pat in time_patterns:
                            if re.search(pat, line, re.IGNORECASE):
                                posted_time = line
                                logger.info(
                                    f"   [time] Tìm thấy thời gian đăng bài từ text thô: {posted_time!r}"
                                )
                                matched = True
                                break
                        if matched:
                            break
            except Exception as e:
                logger.debug(f"   [time] Quét text thô thất bại: {e}")

        return {
            "content": content,
            "post_url": post_url,
            "post_id": post_id,
            "author": author,
            "posted_time": posted_time,
        }

    # ============================================================
    # SEE MORE EXPANSION — Upgrade #1
    # ============================================================

    def _expand_see_more(self, page: Page):
        """Click tất cả nút 'Xem thêm' với retry và human-like delay."""
        expanded = 0
        for text in SEE_MORE_TEXTS:
            try:
                buttons = page.locator(f"text={text}")
                count = buttons.count()
                for i in range(min(count, 20)):
                    success = self._click_with_retry(buttons.nth(i))
                    if success:
                        expanded += 1
                        self._human_delay(0.6, 1.5)
            except Exception as e:
                logger.debug(f"   expand_see_more error '{text}': {e}")

        if expanded:
            logger.debug(f"   ↗ Expanded {expanded} 'See more' buttons")

    @_retry(max_attempts=3, delay=0.8)
    def _click_with_retry(self, locator) -> bool:
        """Click với retry — Upgrade #5."""
        locator.click(timeout=3000, force=True)
        return True

    # ============================================================
    # HUMAN BEHAVIOR
    # ============================================================

    def _setup_page(self, page: Page):
        page.set_viewport_size(
            {"width": random.randint(1366, 1920), "height": random.randint(768, 1080)}
        )
        page.evaluate("""() => {
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['vi-VN', 'vi']});
        }""")

    def _safe_goto(self, page: Page, url: str, retries: int = 3) -> bool:
        """Navigate với retry — Upgrade #5."""
        for attempt in range(1, retries + 1):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                self._human_delay(5, 9)
                return True
            except Exception as e:
                logger.warning(f"   goto attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(5 * attempt)
        return False

    def _human_scroll(self, page: Page, max_scrolls: int = 10):
        """Scroll chậm giả lập người thật với mouse movement."""
        count = 0
        for i in range(max_scrolls):
            # Di chuột ngẫu nhiên
            try:
                page.mouse.move(
                    random.randint(150, 900),
                    random.randint(100, 600),
                    steps=random.randint(5, 12),
                )
            except Exception:
                pass

            # Cuộn — đôi khi cuộn ngược lên (25%)
            if random.random() < 0.25 and i > 1:
                scroll_px = -random.randint(80, 200)
            else:
                scroll_px = random.randint(400, 850)

            try:
                page.evaluate(
                    f"window.scrollBy({{top: {scroll_px}, behavior: 'smooth'}})"
                )
                page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass

            self._human_delay(2.5, 5.0)

            # Đọc bài pause (30%)
            if random.random() < 0.30:
                self._human_delay(4.0, 9.0)

            # Check đủ article chưa
            try:
                count = page.evaluate(
                    f"() => document.querySelectorAll('div[role=\"article\"]').length"
                )
                if count >= 25:
                    logger.debug(f"   Scroll {i + 1}: {count} articles — stopping")
                    break
            except Exception:
                pass

    def _human_delay(self, min_s: float = 1.5, max_s: float = 4.0):
        """Sleep với Gaussian jitter — tự nhiên hơn uniform."""
        mid = (min_s + max_s) / 2
        sigma = (max_s - min_s) / 4
        t = random.gauss(mid, sigma)
        t = max(min_s, min(max_s, t))
        time.sleep(t)

    # ============================================================
    # BUILD JOB MODEL
    # ============================================================

    def _build_job_model(self, post: Dict, group: dict) -> JobModel:
        content = post.get("content", "")

        job = JobModel(source=self.SOURCE_NAME)
        job.title = self.cleaner.extract_title(content)
        job.description = self.cleaner._clean_text(content)
        job.contact_phone = self.cleaner.extract_phone(content)

        author = post.get("author", "").strip()
        extracted_company = self.cleaner.extract_company(
            content, getattr(self, "verified_entities", None)
        )
        if author:
            if extracted_company:
                job.company = f"{author} ({extracted_company})"
            else:
                job.company = author
        else:
            job.company = extracted_company or "Facebook Recruiter"
        job.salary = self.cleaner.extract_salary(content)
        job.location = self.cleaner.extract_location(content)
        job.skills = self.cleaner.extract_skills(content)
        job.job_type = self.cleaner.extract_job_type(content)
        job.requirements = self.cleaner.extract_requirements(content)
        job.job_url = post.get("post_url", "")
        raw_time = post.get("posted_time", "")
        job.posted_date = self._parse_posted_time(raw_time)
        job.external_id = post.get("post_id", "") or self._make_id(
            post.get("post_url", "")
        )
        job.fingerprint = self.cleaner.make_fingerprint(content)
        job.group_id = group.get("url", "unknown")
        job.group_name = group.get("name", "unknown")
        return job

    def _make_id(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()[:16] if url else ""

    def _parse_posted_time(self, raw: str) -> str:
        """
        Chuyển các dạng thời gian Facebook về 'YYYY-MM-DD HH:MM:SS'.
        - "17 May 2026 at 23:17" → chuẩn hoá
        - "17 phút", "44 phút", "1 giờ" → tính ngược từ now()
        - "Đã chia sẻ 17 phút trước" → tương tự
        """
        import re
        from datetime import timezone, timedelta

        if not raw:
            return ""

        now = datetime.now()
        raw_clean = raw.strip()

        # 0. Dạng: "Vừa xong" / "just now"
        if re.search(r"(?:vừa\s*xong|just\s*now)", raw_clean, re.IGNORECASE):
            return now.strftime("%Y-%m-%d %H:%M:%S")

        # 0b. Dạng: "Hôm qua lúc 14:30" / "Hôm qua" / "Yesterday"
        m_yest = re.search(
            r"(?:hôm\s*qua|yesterday)(?:\s+l[u\xfa]c\s+(\d{1,2})[h:](\d{2}))?",
            raw_clean,
            re.IGNORECASE,
        )
        if m_yest:
            dt = now - timedelta(days=1)
            hour = int(m_yest.group(1)) if m_yest.group(1) else 12
            minute = int(m_yest.group(2)) if m_yest.group(2) else 0
            dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        # 0c. Dạng: "19 tháng 5 lúc 12:00" hoặc "19 tháng 5"
        m_vn = re.search(
            r"(\d{1,2})\s+th[áa]ng\s+(\d{1,2})(?:\s+l[u\xfa]c\s+(\d{1,2})[h:](\d{2}))?",
            raw_clean,
            re.IGNORECASE,
        )
        if m_vn:
            day = int(m_vn.group(1))
            month = int(m_vn.group(2))
            year = now.year
            if month > now.month or (month == now.month and day > now.day):
                year -= 1
            hour = int(m_vn.group(3)) if m_vn.group(3) else 12
            minute = int(m_vn.group(4)) if m_vn.group(4) else 0
            try:
                dt = datetime(year, month, day, hour, minute)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        # Dạng: "X phút" / "X phút trước" / "X m" / "Xm"
        m = re.search(r"(\d+)\s*(?:ph[u\xfa]t|m\b|min\b)", raw, re.IGNORECASE)
        if m:
            dt = now - timedelta(minutes=int(m.group(1)))
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        # Dạng: "X giờ" / "X giờ trước" / "X h" / "Xh" / "Xg"
        m = re.search(r"(\d+)\s*(?:gi[o\u1edd]|h\b|g\b)", raw, re.IGNORECASE)
        if m:
            dt = now - timedelta(hours=int(m.group(1)))
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        # Dạng: "X ngày" / "X ngày trước" / "X d" / "Xd" / "X day"
        m = re.search(r"(\d+)\s*(?:ng[a\xE0]y|d\b|day\b)", raw, re.IGNORECASE)
        if m:
            dt = now - timedelta(days=int(m.group(1)))
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        # Dạng: "May 17, 2026 at 11:41 PM" hoặc "17 May 2026 at 23:17"
        # Regex extract linh hoạt hơn strptime
        m = re.search(
            r"(\w+\s+\d{1,2},?\s+\d{4})\s+at\s+(\d{1,2}:\d{2}(?:\s*[AP]M)?)",
            raw,
            re.IGNORECASE,
        )
        if m:
            date_part = m.group(1).replace(",", "").strip()
            time_part = m.group(2).strip().upper()
            for fmt in [
                "%B %d %Y %I:%M %p",
                "%B %d %Y %H:%M",
                "%d %B %Y %I:%M %p",
                "%d %B %Y %H:%M",
            ]:
                try:
                    return datetime.strptime(f"{date_part} {time_part}", fmt).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError:
                    continue

        # Dạng: "17 May 2026 at 23:17" (ngày trước, tháng sau — regex trên có thể miss)
        m2 = re.search(
            r"(\d{1,2}\s+\w+\s+\d{4})\s+at\s+(\d{1,2}:\d{2}(?:\s*[AP]M)?)",
            raw,
            re.IGNORECASE,
        )
        if m2:
            date_part = m2.group(1).strip()
            time_part = m2.group(2).strip().upper()
            for fmt in ["%d %B %Y %I:%M %p", "%d %B %Y %H:%M"]:
                try:
                    return datetime.strptime(f"{date_part} {time_part}", fmt).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError:
                    continue

        # Dạng: "17 May 2026" hoặc "May 17, 2026" (không có giờ)
        for fmt in ["%d %B %Y", "%B %d %Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(raw.strip().replace(",", ""), fmt).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                continue

        # Giữ nguyên nếu không parse được -> Sẽ gây lỗi SQL Server "Conversion failed" nếu đẩy text thô vào DATETIME
        # Thay vì trả về raw, ta trả về "" để db_handler chuyển thành NULL an toàn.
        logger.debug(f"   [time] Không thể parse thời gian nội bộ Facebook: {raw!r}")
        return ""

    # ============================================================
    # FILTER
    # ============================================================

    def _is_recruitment_post(self, content: str) -> bool:
        if not content:
            return False
        text = content.lower()
        return any(kw in text for kw in RECRUITMENT_KEYWORDS)

    def _is_spam_basic(self, content: str) -> bool:
        """Keyword-based pre-filter (nhanh). NLP spam check đầy đủ hơn trong crawl_and_save."""
        if not content:
            return True
        text = content.lower()
        return sum(1 for kw in SPAM_KEYWORDS if kw in text) >= 2

    def _select_groups(self) -> List[dict]:
        """Chọn groups theo priority, shuffle trong từng mức."""
        high = [g for g in self.facebook_groups if g.get("priority") == "high"]
        medium = [g for g in self.facebook_groups if g.get("priority") == "medium"]
        low = [
            g
            for g in self.facebook_groups
            if g.get("priority") not in ("high", "medium")
        ]
        random.shuffle(high)
        random.shuffle(medium)
        random.shuffle(low)
        return (high + medium + low)[: self.max_groups]
