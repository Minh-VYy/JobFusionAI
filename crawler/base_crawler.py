# crawler/base_crawler.py
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
import time
import random
import logging
import math

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ================================================================
# USER AGENTS — Desktop Chrome / Firefox, giả lập thực tế
# ================================================================
DESKTOP_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

VIEWPORT_SIZES = [
    {"width": 1920, "height": 1080},
    {"width": 1600, "height": 900},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
]


class BaseCrawler:
    """
    Base class cho tất cả crawler.
    Tích hợp:
    - Anti-detection nâng cao (stealth mode)
    - Human-like random sleep (Gaussian jitter)
    - Human scroll reusable
    - Context manager support
    """

    def __init__(
        self,
        headless: bool = True,
        max_pages: int = 5,
        use_cdp: bool = True,
        cdp_url: str = "http://localhost:9222",
    ):
        self.headless = headless
        self.max_pages = max_pages
        self.use_cdp = use_cdp
        self.cdp_url = cdp_url
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None

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
        if self.headless:
            cmd.append("--headless=new")

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    # ================================================================
    # KHỞI TẠO & DỪNG (Context Manager)
    # ================================================================

    def _setup_popup_blocker(self):
        """Tự động phát hiện và đóng lập tức tất cả các tab phụ/popup tự động mở ra"""
        if not hasattr(self, "context") or not self.context:
            return

        def handle_new_page(new_page):
            try:
                # Đóng ngay lập tức nếu tab được mở không phải tab chính của bot hiện tại
                if hasattr(self, "page") and self.page and new_page != self.page:
                    new_page.close()
            except:
                pass

        self.context.on("page", handle_new_page)

    def start(self):
        """Khởi động Playwright + stealth browser context"""
        logger.info("🚀 Khởi động browser...")
        self.playwright = sync_playwright().start()

        ua = random.choice(DESKTOP_USER_AGENTS)
        vp = random.choice(VIEWPORT_SIZES)
        context_options = {
            "user_agent": ua,
            "viewport": vp,
            "locale": "vi-VN",
            "timezone_id": "Asia/Ho_Chi_Minh",
            "java_script_enabled": True,
            "permissions": ["geolocation"],
            "extra_http_headers": {
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        }

        if self.use_cdp:
            self._auto_launch_chrome()
            try:
                logger.info(f"🔗 Đang thử kết nối CDP: {self.cdp_url}...")
                self.browser = self.playwright.chromium.connect_over_cdp(
                    self.cdp_url, timeout=10000
                )
                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                else:
                    self.context = self.browser.new_context(**context_options)

                # LUÔN TẠO TAB MỚI ĐỂ TRÁNH ĐÈ LÊN BOT KHÁC
                logger.info("Mở tab mới trên trình duyệt hiện tại...")
                self.page = self.context.new_page()

                # Bật popup blocker tự động đóng các tab phụ
                self._setup_popup_blocker()
                self._inject_stealth_scripts()

                logger.info(
                    "✅ Đã kết nối thành công tới trình duyệt có sẵn (Tab mới)!"
                )
                return
            except Exception as e:
                logger.warning(
                    f"⚠️ Không kết nối được trình duyệt thật ({e}). Mở trình duyệt ảo..."
                )
                self.use_cdp = False

        logger.info("🚀 Khởi động trình duyệt ảo (stealth mode)...")
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=TranslateUI",
                "--disable-web-security",
                "--lang=vi-VN",
            ],
        )

        self.context = self.browser.new_context(**context_options)

        self.page = self.context.new_page()
        self._inject_stealth_scripts()

        # Bật popup blocker tự động đóng các tab phụ
        self._setup_popup_blocker()

        logger.info(
            f"✅ Browser ảo sẵn sàng | UA: {ua[:60]}... | VP: {vp['width']}x{vp['height']}"
        )

    def _recreate_page(self):
        """Tạo lại tab mới khi page hiện tại bị detach/đóng."""
        if not self.context or self.context.is_closed():
            return False
        try:
            self.page = self.context.new_page()
            self._inject_stealth_scripts()
            self._setup_popup_blocker()
            return True
        except Exception as e:
            logger.warning(f"⚠️ Không thể tạo tab mới: {e}")
            return False

    def _clean_chrome_cache(self):
        """Dọn dẹp các thư mục cache của ChromeProfile mà không làm mất trạng thái đăng nhập"""
        import os

        profile_dir = r"C:\ChromeProfile"
        if not os.path.exists(profile_dir):
            return

        cache_targets = [
            r"Default\Cache",
            r"Default\Code Cache",
            r"Default\GPUCache",
            r"Default\Service Worker\CacheStorage",
            r"Default\Service Worker\ScriptCache",
            r"Default\Storage\ext",
            r"Crashpad",
            r"ShaderCache",
        ]

        logger.info(
            "🧹 Đang tự động dọn dẹp bộ nhớ đệm Chrome để giảm dung lượng ổ đĩa..."
        )
        freed = 0
        for target in cache_targets:
            target_path = os.path.join(profile_dir, target)
            if os.path.exists(target_path):
                # Duyệt qua các tệp tin để xóa các file không bị lock
                for root, dirs, files in os.walk(target_path, topdown=False):
                    for file in files:
                        fp = os.path.join(root, file)
                        try:
                            sz = os.path.getsize(fp)
                            os.remove(fp)
                            freed += sz
                        except Exception:
                            # File bị lock bởi Chrome đang hoạt động, bỏ qua an toàn
                            pass
                    for d in dirs:
                        dp = os.path.join(root, d)
                        try:
                            os.rmdir(dp)
                        except Exception:
                            pass
        if freed > 0:
            logger.info(
                f"✅ Tự động dọn dẹp Chrome hoàn tất! Đã giải phóng: {freed / (1024 * 1024):.2f} MB"
            )

    def stop(self):
        """Đóng/Ngắt kết nối browser, giải phóng memory"""
        # Luôn đóng tab hiện tại để tránh lưu rác/nhiều tab mở
        if getattr(self, "page", None) and not self.page.is_closed():
            try:
                self.page.close()
                logger.info("🛑 Đã đóng tab của crawler hiện tại")
            except:
                pass

        if self.context:
            try:
                self.context.close()
            except:
                pass

        if (
            getattr(self, "use_cdp", False)
            and hasattr(self, "browser")
            and self.browser
            and self.browser.is_connected()
        ):
            logger.info("🛑 Ngắt kết nối khỏi trình duyệt thật (giữ Chrome luôn mở)...")
            # KHÔNG gọi self.browser.close() vì sẽ tắt luôn cả ứng dụng Chrome của người dùng!
            # Playwright sẽ tự động ngắt kết nối an toàn khi gọi playwright.stop()
        else:
            if self.browser:
                self.browser.close()

        if self.playwright:
            self.playwright.stop()
        logger.info("🛑 Playwright cleanup hoàn tất")

        # Tự động dọn dẹp cache của Chrome sau khi đóng tab
        if getattr(self, "use_cdp", False):
            try:
                self._clean_chrome_cache()
            except Exception as e:
                logger.warning(f"⚠️ Không thể tự động dọn dẹp cache Chrome: {e}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    # ================================================================
    # STEALTH — ẨN DẤU HIỆU BOT
    # ================================================================

    def _inject_stealth_scripts(self):
        """Inject các script ẩn dấu hiệu automation vào mọi trang"""
        self.page.add_init_script("""
            // 1. Ẩn cờ webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // 2. Giả lập plugins của trình duyệt thật
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // 3. Giả lập ngôn ngữ
            Object.defineProperty(navigator, 'languages', {
                get: () => ['vi-VN', 'vi', 'en-US', 'en']
            });

            // 4. Ẩn chrome automation flag
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // 5. Ẩn permission automation
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);

            // 6. Giả lập hardware concurrency thực tế
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        """)

    # ================================================================
    # ĐIỀU HƯỚNG
    # ================================================================

    def _refresh_or_recreate_page(self, reason: str = ""):
        """Refresh tab hien tai; neu tab hong thi tao tab moi."""
        try:
            if self.page and not self.page.is_closed():
                logger.warning(f"Refresh page vi trang co dau hieu bi dung: {reason}")
                self.page.reload(timeout=15000, wait_until="domcontentloaded")
                return
        except Exception as e:
            logger.warning(f"Refresh page that bai, tao lai tab moi: {e}")
        self._recreate_page()

    def goto(self, url: str, wait_after: float = 2.5) -> bool:
        """Truy cập URL + sleep ngẫu nhiên tự nhiên sau khi load"""
        last_error = None
        for attempt in range(1, 4):
            try:
                if not self.page or self.page.is_closed():
                    self._recreate_page()

                logger.info(f"🌐 Navigating to: {url}")
                self.page.goto(url, timeout=45000, wait_until="domcontentloaded")
                self.human_sleep(wait_after, wait_after + 2)
                return True
            except Exception as e:
                last_error = e
                message = str(e)
                retryable = any(
                    token in message
                    for token in (
                        "Timeout",
                        "Navigation timeout",
                        "ERR_ABORTED",
                        "ERR_TIMED_OUT",
                        "frame was detached",
                        "Execution context was destroyed",
                        "Target page, context or browser has been closed",
                    )
                )
                if attempt < 3 and retryable:
                    logger.warning(f"⚠️ Lỗi điều hướng (thử lại {attempt}/3): {e}")
                    self._refresh_or_recreate_page(str(e))
                    self.human_sleep(0.5, 1.0)
                    continue
                logger.error(f"❌ Lỗi truy cập {url}: {e}")
                return False

        logger.error(f"❌ Lỗi truy cập {url}: {last_error}")
        return False

    def get_html(self) -> str:
        """Lấy toàn bộ HTML của trang hiện tại"""
        return self.page.content()

    # ================================================================
    # HUMAN-LIKE SLEEP — Gaussian jitter (tự nhiên hơn uniform)
    # ================================================================

    def human_sleep(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """
        Sleep ngẫu nhiên theo phân phối Gaussian (tự nhiên hơn uniform).
        Phân phối hình chuông: tập trung ở giữa khoảng, hiếm khi ở 2 đầu.
        """
        mid = (min_sec + max_sec) / 2
        sigma = (max_sec - min_sec) / 4
        sleep_time = random.gauss(mid, sigma)
        sleep_time = max(min_sec, min(max_sec, sleep_time))
        time.sleep(sleep_time)

    def micro_pause(self):
        """Dừng cực ngắn 50-300ms — giống thao tác giữa các click"""
        time.sleep(random.uniform(0.05, 0.3))

    def reading_pause(self):
        """Dừng dài 4-10s — giả lập đang đọc nội dung trên trang"""
        duration = random.uniform(4.0, 10.0)
        logger.debug(f"   📖 Reading pause {duration:.1f}s...")
        time.sleep(duration)

    # ================================================================
    # HUMAN SCROLL — Reusable cho toàn bộ crawler
    # ================================================================

    def human_scroll(
        self,
        page: Page = None,
        scrolls: int = 8,
        stop_at_count: int = None,
        count_selector: str = None,
    ) -> int:
        """
        Cuộn trang giống con người: từng bước, di chuột ngẫu nhiên,
        thỉnh thoảng dừng lại 'đọc bài'.

        Args:
            page:           Page để cuộn. Mặc định dùng self.page.
            scrolls:        Số lần cuộn tối đa.
            stop_at_count:  Dừng sớm nếu số phần tử >= ngưỡng này.
            count_selector: CSS selector để đếm phần tử (dùng với stop_at_count).

        Returns:
            int: Số phần tử tìm thấy (nếu count_selector được truyền vào).
        """
        p = page or self.page
        element_count = 0

        for i in range(scrolls):
            # 1. Di chuyển chuột nhẹ trước khi scroll — giống người thật
            p.mouse.move(
                random.randint(150, 900),
                random.randint(100, 650),
                steps=random.randint(5, 12),
            )
            self.micro_pause()

            # 2. Cuộn với khoảng cách ngẫu nhiên
            # Thỉnh thoảng cuộn lên 1 chút (25%) — hành vi rất tự nhiên
            if random.random() < 0.25 and i > 0:
                scroll_px = -random.randint(80, 200)
                logger.debug(f"   ↑ Scroll up {abs(scroll_px)}px")
            else:
                scroll_px = random.randint(400, 900)

            p.evaluate(f"window.scrollBy({{top: {scroll_px}, behavior: 'smooth'}})")

            # 3. Chờ network sau scroll
            try:
                p.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass

            # 4. Sleep tự nhiên giữa các scroll
            self.human_sleep(2.0, 4.5)

            # 5. Thỉnh thoảng dừng dài "đọc bài" (30%)
            if random.random() < 0.30:
                self.reading_pause()

            # 6. Kiểm tra stop_at_count
            if count_selector and stop_at_count:
                element_count = p.evaluate(
                    f"() => document.querySelectorAll('{count_selector}').length"
                )
                logger.debug(f"   [{i + 1}/{scrolls}] Found {element_count} elements")
                if element_count >= stop_at_count:
                    logger.info(
                        f"   ✅ Reached {element_count} elements, stopping scroll"
                    )
                    break

        return element_count

    def scroll_to_bottom(self):
        """Scroll xuống cuối trang nhanh (dùng cho trang phân trang cứng)"""
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.human_sleep(1.0, 2.5)

    # ================================================================
    # INCREMENTAL CRAWLING — Bỏ qua URLs đã crawl gần đây
    # ================================================================

    def _filter_new_urls(
        self,
        urls: list,
        source_name: str,
        max_age_days: int = 7,
    ) -> list:
        """
        Lọc bỏ URLs đã crawl gần đây (< max_age_days ngày).
        URLs cũ hơn max_age_days → cho phép crawl lại (dữ liệu có thể stale).
        Nếu DB lỗi → fallback crawl tất cả.
        """
        if not urls:
            return []
        try:
            from database.db_handler import DBHandler

            with DBHandler() as db:
                known_urls = db.get_crawled_urls(
                    source_name=source_name,
                    max_age_days=max_age_days,
                )
            new_urls = [u for u in urls if u not in known_urls]
            skipped = len(urls) - len(new_urls)
            if skipped:
                logger.info(
                    f"   ⏭️ Incremental: skip {skipped} URLs đã crawl — "
                    f"{len(new_urls)} URL mới cần fetch"
                )
            else:
                logger.info(f"   ✅ Tất cả {len(new_urls)} URLs là mới")
            return new_urls
        except Exception as e:
            logger.warning(f"   ⚠️ _filter_new_urls error: {e} — crawl all")
            return urls  # fallback an toàn

    # ================================================================
    # MOUSE INTERACTION — Tự nhiên hơn
    # ================================================================

    def human_click(self, selector: str):
        """Click vào phần tử với di chuột chậm trước khi click"""
        try:
            el = self.page.locator(selector).first
            box = el.bounding_box()
            if box:
                # Di chuột từ từ đến gần phần tử
                target_x = box["x"] + box["width"] / 2 + random.randint(-5, 5)
                target_y = box["y"] + box["height"] / 2 + random.randint(-3, 3)
                self.page.mouse.move(target_x, target_y, steps=random.randint(8, 15))
                self.micro_pause()
                el.click()
                self.human_sleep(0.5, 1.5)
        except Exception as e:
            logger.warning(f"⚠️  human_click failed for '{selector}': {e}")

    # ================================================================
    # OVERRIDE
    # ================================================================

    def crawl(self) -> list:
        """Override method này trong từng crawler cụ thể. Trả về list[JobModel]"""
        raise NotImplementedError("Subclass phải implement method crawl()")
