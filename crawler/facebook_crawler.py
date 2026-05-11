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
FACEBOOK_GROUPS = [
    {"name": "VIỆC LÀM THỜI VỤ ĐÀ NẴNG GROUP",       "url": "https://www.facebook.com/groups/358744117181132", "trust_score": 0.85, "priority": "high"},
    {"name": "Tìm kiếm việc làm tại Đà Nẵng",          "url": "https://www.facebook.com/groups/422673553710542", "trust_score": 0.80, "priority": "high"},
    {"name": "VIỆC LÀM PHỤC VỤ PHA CHẾ ĐÀ NẴNG",     "url": "https://www.facebook.com/groups/363005460084694", "trust_score": 0.90, "priority": "high"},
    {"name": "Việc làm Đà Nẵng full/part-time SV",     "url": "https://www.facebook.com/groups/360683986995278", "trust_score": 0.80, "priority": "medium"},
    {"name": "Hội Tìm Việc Làm Thêm SV Đà Nẵng",      "url": "https://www.facebook.com/groups/360978689839999", "trust_score": 0.75, "priority": "medium"},
    {"name": "Hội Việc Làm Đà Nẵng - Viec Lam Da Nang","url": "https://www.facebook.com/groups/471999991646484", "trust_score": 0.85, "priority": "high"},
    {"name": "VIỆC LÀM - ĐÀ NẴNG",                    "url": "https://www.facebook.com/groups/444340500105671", "trust_score": 0.90, "priority": "high"},
    {"name": "Việc Làm Đà Nẵng",                       "url": "https://www.facebook.com/groups/sieuthiphuyen78",  "trust_score": 0.80, "priority": "high"},
    {"name": "Hội Tìm Việc Làm Thêm Cho SV Đà Nẵng",  "url": "https://www.facebook.com/groups/thichlamthemcom","trust_score": 0.80, "priority": "medium"},
]

# Selector fallback system — thử theo thứ tự
ARTICLE_SELECTORS = ["div[role='article']", "div[data-pagelet*='FeedUnit']", "div[data-ft]"]
CONTENT_SELECTORS = [
    "div[data-ad-comet-preview='message']",
    "div[dir='auto']",
    "div[data-ad-preview='message']",
    "div[role='article'] div[dir='auto']",
]
LINK_SELECTORS    = ["a[href*='permalink']", "a[href*='/posts/']", "a[role='link'][href*='groups']"]
TIME_SELECTORS    = ["abbr", "span[role='link']", "a[role='link'] span"]
AUTHOR_SELECTORS  = ["strong a", "a[role='link'] strong", "span[dir='auto'] a[role='link']"]
SEE_MORE_TEXTS    = ["Xem thêm", "See more", "Xem thêm nội dung"]

RECRUITMENT_KEYWORDS = [
    "tuyển", "tuyển dụng", "tuyển gấp", "cần tuyển", "cần người", "việc làm",
    "part-time", "full-time", "parttime", "fulltime", "lương", "thu nhập",
    "ca tối", "ca ngày", "phục vụ", "shipper", "bán hàng", "nhân viên",
    "thực tập sinh", "fresher", "cộng tác viên",
]
SPAM_KEYWORDS = [
    "thu nhập khủng", "việc nhẹ lương cao", "không cần kinh nghiệm, thu nhập",
    "đa cấp", "cọc tiền", "tuyển ctv online không cần làm việc", "kiếm tiền tại nhà",
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
                        logger.warning(f"[retry] {fn.__name__} failed after {max_attempts} attempts: {e}")
                        return None
                    logger.debug(f"[retry] {fn.__name__} attempt {attempt} failed: {e} — retrying...")
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
        max_posts_per_group: int = 5,
        max_groups_per_session: int = 3,
        hours_lookback: int = 24,
    ):
        self.max_posts  = max_posts_per_group
        self.max_groups = max_groups_per_session
        self.hours_lookback = hours_lookback

        self.cleaner      = FacebookCleaner()
        self.nlp          = FacebookNLP()
        self.detector     = DuplicateDetector(similarity_threshold=0.85)
        self.cross_det    = CrossSourceDetector(threshold=0.85)  # Cross-source
        self.state        = CrawlStateManager()
        self.jobs: List[JobModel] = []

        # Persistent caches
        self._load_fingerprints_from_db()
        self._load_cross_detector_baseline()

    # ============================================================
    # PERSISTENT DUPLICATE CACHE (Upgrade #6)
    # ============================================================

    def _load_fingerprints_from_db(self):
        """Load fingerprints từ DB để DuplicateDetector nhớ bài cũ sau restart."""
        try:
            with FacebookDB() as db:
                db.create_tables()
                fingerprints = db.get_all_fingerprints()
                if fingerprints:
                    self.detector.load_existing(fingerprints)
                    logger.info(f"[cache] Loaded {len(fingerprints)} fingerprints from DB")
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

    def crawl_and_save(self) -> dict:
        """Pipeline hoàn chỉnh: Crawl → NLP Spam → Duplicate → DB → Trust Score."""
        raw_jobs = self.crawl()
        if not raw_jobs:
            return {"total": 0, "spam": 0, "duplicate": 0, "skipped_db": 0, "inserted": 0, "errors": 0}

        stats = {
            "total": len(raw_jobs), "spam": 0, "duplicate": 0,
            "cross_dup": 0, "job_seeking": 0,
            "skipped_db": 0, "inserted": 0, "errors": 0, "groups": {},
        }

        with FacebookDB() as db:
            db.create_tables()

            for job in raw_jobs:
                group_id   = getattr(job, "group_id",   "unknown")
                group_name = getattr(job, "group_name", "unknown")

                if group_id not in stats["groups"]:
                    stats["groups"][group_id] = {"name": group_name, "total": 0, "spam": 0, "dup": 0, "inserted": 0}
                g = stats["groups"][group_id]
                g["total"] += 1

                desc = job.description or ""

                # 2a. Spam check
                is_spam, _, reason = self.nlp.is_spam(desc)
                if is_spam:
                    logger.debug(f"🚫 SPAM [{group_name}]: {reason[:60]}")
                    stats["spam"] += 1; g["spam"] += 1
                    continue

                # 2b. Post-type check: lọc bài TÌM VIỆC
                is_recruiting, type_reason = self.nlp.is_recruiting_post(desc)
                if not is_recruiting:
                    logger.debug(f"🔍 JOB_SEEKING [{group_name}]: {type_reason[:80]}")
                    stats["job_seeking"] += 1
                    g.setdefault("job_seeking", 0); g["job_seeking"] += 1
                    continue

                # 2c. Same-source duplicate check (fast hash/phone/cosine)
                phone = getattr(job, "contact_phone", "") or ""
                is_dup, method, sim = self.detector.is_duplicate(desc, phone)
                if is_dup:
                    logger.debug(f"♻️  DUP [{group_name}]: {method} sim={sim:.2f}")
                    stats["duplicate"] += 1; g["dup"] += 1
                    continue

                # 2d. Extract normalized features cho cross-source check
                job_dict = {
                    "job_id":      getattr(job, "external_id", ""),
                    "source":      "facebook",
                    "title":       getattr(job, "title", ""),
                    "company":     getattr(job, "company", ""),
                    "location":    getattr(job, "location", ""),
                    "salary":      getattr(job, "salary", ""),
                    "phone":       phone,
                    "description": desc,
                }
                features = self.cross_det.extract_features(job_dict)

                # 2e. Cross-source duplicate check
                is_cross_dup, cross_score, matched_id = self.cross_det.is_duplicate(job_dict)
                if is_cross_dup:
                    logger.debug(f"🔀 CROSS-DUP [{group_name}]: score={cross_score:.2f} vs {matched_id}")
                    stats["cross_dup"] += 1
                    g.setdefault("cross_dup", 0); g["cross_dup"] += 1
                    continue

                # 2f. Insert — enriched với normalized fields
                job_data = {
                    "title":              getattr(job, "title", ""),
                    "company":            getattr(job, "company", ""),
                    "description":        desc,
                    "salary":             getattr(job, "salary", ""),
                    "location":           getattr(job, "location", ""),
                    "skills":             ", ".join(getattr(job, "skills", []) or []),
                    "phone":              phone[:50],
                    "job_url":            getattr(job, "job_url", ""),
                    "post_id":            getattr(job, "external_id", ""),
                    "source_group":       group_name,
                    "quality_score":      self.nlp.quality_score(desc),
                    # Normalized fields for cross-source future queries
                    "normalized_title":   features.norm_title,
                    "normalized_location": features.norm_location,
                    "salary_min":         features.salary_min or None,
                    "salary_max":         features.salary_max or None,
                    "fingerprint_hash":   features.fingerprint,
                }
                try:
                    ok = db.insert_facebook_job(job_data)
                    if ok:
                        stats["inserted"] += 1; g["inserted"] += 1
                        logger.debug(f"✅ INSERT [{group_name}]: {job_data['title'][:50]}")
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
                dup_r  = g["dup"]  / g["total"]
                trust  = round(1.0 - spam_r * 0.5 - dup_r * 0.3, 2)
                pri    = "high" if trust > 0.7 else "normal" if trust > 0.4 else "low"
                try:
                    db.upsert_group({
                        "group_id": gid, "group_name": g["name"], "group_url": gid,
                        "trust_score": trust, "spam_ratio": round(spam_r, 3),
                        "duplicate_ratio": round(dup_r, 3), "crawl_priority": pri,
                        "total_crawled": g["total"], "total_spam": g["spam"], "total_duplicate": g["dup"],
                    })
                    logger.info(f"📈 [{g['name']}] trust={trust} | {pri}")
                except Exception as e:
                    logger.warning(f"⚠️  upsert_group failed: {e}")

        logger.info(
            f"\n✅ done: total={stats['total']} | spam={stats['spam']} | "
            f"dup={stats['duplicate']} | skip_db={stats['skipped_db']} | "
            f"inserted={stats['inserted']} | errors={stats['errors']}"
        )
        return stats

    def crawl(self) -> List[JobModel]:
        """Attach Chrome qua CDP, crawl các groups đã chọn."""
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.connect_over_cdp("http://localhost:9222")
                logger.info("✅ Connected to existing Chrome session")
            except Exception as e:
                logger.error(f"❌ Cannot connect to Chrome: {e}")
                logger.info("💡 Run: chrome.exe --remote-debugging-port=9222 --user-data-dir=...")
                return []

            context = browser.contexts[0]
            page    = context.new_page()
            self._setup_page(page)

            selected = self._select_groups()
            logger.info(f"📋 Session: {len(selected)} groups")

            for group in selected:
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
        seen_ids  = self.state.get_seen_ids(group_url)
        new_ids   = []

        logger.info(f"🌐 Group: {group['name']} | seen={len(seen_ids)} past IDs")

        # Navigate với retry
        if not self._safe_goto(page, group_url):
            return []

        # Human scroll — Upgrade #3: dùng locator thay page.content()
        logger.info("   ↓ Scrolling to load posts...")
        self._human_scroll(page)

        # Upgrade #1: Expand "Xem thêm" trước khi extract
        self._expand_see_more(page)
        self._human_delay(2, 4)

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

                content = post.get("content", "")

                # FIX: Bỏ bài vẫn còn chứa nút "Xem thêm" (chưa expand được)
                see_more_still_present = any(
                    kw in content.lower()
                    for kw in ["xem thêm", "see more", "xem thêm nội dung"]
                )
                if see_more_still_present:
                    logger.debug(f"   ⚠️ Article #{i}: vẫn còn 'Xem thêm', retry expand...")
                    self._expand_see_more_article(article)
                    post = self._parse_article_locator(article)
                    if not post:
                        continue
                    content = post.get("content", "")

                # Lọc bài quá ngắn hoặc vẫn còn từ khóa "Xem thêm"
                if len(content) > 40:
                    posts.append(post)
                else:
                    logger.debug(f"   ⏭ Article #{i}: content quá ngắn ({len(content)} chars), bỏ qua")

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
                loc = page.locator(selector)
                if loc.count() > 0:
                    logger.debug(f"   ✓ Article selector: '{selector}' → {loc.count()} found")
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

        try:
            # ── Chiến lược 1: JS evaluate → text_content (bypass CSS visibility) ──
            # text_content() đọc tất cả text trong DOM kể cả hidden elements
            full_text = article.evaluate("""el => {
                const divs = el.querySelectorAll("div[dir='auto']");
                let best = '';
                for (const d of divs) {
                    const t = (d.textContent || '').trim();
                    if (t.length > best.length) best = t;
                }
                return best;
            }""")
            if full_text and len(full_text.strip()) > 20:
                content = full_text.strip()
                logger.debug(f"   [tc] Got {len(content)} chars via textContent")
        except Exception as e:
            logger.debug(f"   [tc] JS evaluate failed: {e}")

        # ── Chiến lược 2: inner_text fallback (nếu JS thất bại) ──────────────
        if not content:
            try:
                els = article.locator("div[dir='auto']")
                if els.count() > 0:
                    texts = []
                    for i in range(min(els.count(), 10)):
                        try:
                            t = els.nth(i).inner_text(timeout=1500).strip()
                            if t:
                                texts.append(t)
                        except Exception:
                            pass
                    if texts:
                        content = max(texts, key=len)
            except Exception:
                pass

        # ── Chiến lược 3: CONTENT_SELECTORS fallback ─────────────────────────
        if not content:
            for sel in CONTENT_SELECTORS:
                try:
                    el = article.locator(sel).first
                    if el.count() > 0:
                        content = el.inner_text(timeout=2000).strip()
                        if content:
                            break
                except Exception:
                    continue

        if not content:
            return None


        # Post URL fallback
        post_url = ""
        post_id  = ""
        for sel in LINK_SELECTORS:
            try:
                el = article.locator(sel).first
                if el.count() > 0:
                    href = el.get_attribute("href", timeout=1000) or ""
                    if href:
                        if not href.startswith("http"):
                            href = "https://www.facebook.com" + href
                        post_url = href
                        post_id  = hashlib.md5(href.encode()).hexdigest()[:16]
                        break
            except Exception:
                continue

        # Author fallback
        author = ""
        for sel in AUTHOR_SELECTORS:
            try:
                el = article.locator(sel).first
                if el.count() > 0:
                    author = el.inner_text(timeout=1000).strip()
                    if author:
                        break
            except Exception:
                continue

        # Time fallback
        posted_time = ""
        for sel in TIME_SELECTORS:
            try:
                el = article.locator(sel).first
                if el.count() > 0:
                    posted_time = el.inner_text(timeout=1000).strip()
                    if posted_time:
                        break
            except Exception:
                continue

        return {
            "content":     content,
            "post_url":    post_url,
            "post_id":     post_id,
            "author":      author,
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
                count   = buttons.count()
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
        locator.click(timeout=3000, force=False)
        return True

    # ============================================================
    # HUMAN BEHAVIOR
    # ============================================================

    def _setup_page(self, page: Page):
        page.set_viewport_size({
            "width":  random.randint(1366, 1920),
            "height": random.randint(768, 1080)
        })
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
                    steps=random.randint(5, 12)
                )
            except Exception:
                pass

            # Cuộn — đôi khi cuộn ngược lên (25%)
            if random.random() < 0.25 and i > 1:
                scroll_px = -random.randint(80, 200)
            else:
                scroll_px = random.randint(400, 850)

            try:
                page.evaluate(f"window.scrollBy({{top: {scroll_px}, behavior: 'smooth'}})")
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
                    logger.debug(f"   Scroll {i+1}: {count} articles — stopping")
                    break
            except Exception:
                pass

    def _human_delay(self, min_s: float = 1.5, max_s: float = 4.0):
        """Sleep với Gaussian jitter — tự nhiên hơn uniform."""
        mid   = (min_s + max_s) / 2
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
        job.title         = self.cleaner.extract_title(content)
        job.description   = self.cleaner._clean_text(content)
        job.company       = self.cleaner.extract_company(content)
        job.salary        = self.cleaner.extract_salary(content)
        job.location      = self.cleaner.extract_location(content)
        job.skills        = self.cleaner.extract_skills(content)
        job.contact_phone = self.cleaner.extract_phone(content)
        job.job_url       = post.get("post_url", "")
        job.posted_date   = post.get("posted_time", "")
        job.external_id   = post.get("post_id", "") or self._make_id(post.get("post_url", ""))
        job.fingerprint   = self.cleaner.make_fingerprint(content)
        job.group_id      = group.get("url", "unknown")
        job.group_name    = group.get("name", "unknown")
        return job

    def _make_id(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()[:16] if url else ""

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
        high   = [g for g in FACEBOOK_GROUPS if g.get("priority") == "high"]
        medium = [g for g in FACEBOOK_GROUPS if g.get("priority") == "medium"]
        low    = [g for g in FACEBOOK_GROUPS if g.get("priority") not in ("high", "medium")]
        random.shuffle(high); random.shuffle(medium); random.shuffle(low)
        return (high + medium + low)[:self.max_groups]