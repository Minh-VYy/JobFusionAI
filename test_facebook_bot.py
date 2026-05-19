# test_facebook_bot.py
import logging
import sys
import os
import socket
import time

# 1. Đảm bảo import được các module trong project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 2. Cấu hình encoding utf-8 cho console Windows để in tiếng Việt không lỗi
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from crawler.facebook_crawler import FacebookCrawler

# 3. Cấu hình Logging chuyên nghiệp
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("fb_test")

def is_chrome_running(port=9222):
    """Kiểm tra xem Chrome có đang mở ở port debugging không"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def run_test():
    print("\n" + "="*60)
    logger.info("🤖 BẮT ĐẦU KIỂM TRA BOT FACEBOOK (HUMAN-LIKE)")
    print("="*60)

    # Bước 1: Kiểm tra môi trường
    if not is_chrome_running(9222):
        logger.error("❌ KHÔNG TÌM THẤY CHROME!")
        logger.warning("Vui lòng chạy lệnh sau trong CMD trước khi test:")
        print(r'chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\ChromeProfile"')
        return

    logger.info("✅ Đã kết nối được với Chrome (Port 9222)")

    # Bước 2: Khởi tạo Crawler với thiết lập test nhanh
    crawler = FacebookCrawler(
        max_groups_per_session=2,
        max_posts_per_group=8  # Tăng lên 8 bài để test kỹ hơn
    )
    
    # 🎯 ÉP BOT CHẠY ĐÚNG LINK BẠN YÊU CẦU

    
    start_time = time.time()
    try:
        # Chạy toàn bộ quy trình: Human Scroll -> Click See More -> Parse -> NLP Spam -> Lưu DB
        stats = crawler.crawl_and_save()
        
        duration = round(time.time() - start_time, 2)
        
        print("\n" + "="*60)
        logger.info("📊 KẾT QUẢ PHIÊN CHẠY THỬ NGHIỆM")
        print("-" * 60)
        logger.info(f"⏱️  Thời gian chạy       : {duration} giây")
        logger.info(f"📦 Tổng bài thu thập     : {stats.get('total', 0)}")
        logger.info(f"✅ Đã lưu vào DB        : {stats.get('inserted', 0)}")
        logger.info(f"🚫 Bài bị lọc (Spam)    : {stats.get('spam', 0)}")
        logger.info(f"♻️  Bài trùng lặp (Dup)  : {stats.get('duplicate', 0)}")
        logger.info(f"🔀 Trùng nguồn khác     : {stats.get('cross_dup', 0)}")
        logger.info(f"❌ Lỗi hệ thống         : {stats.get('errors', 0)}")
        print("="*60)

        if stats.get('inserted', 0) > 0:
            logger.info("🎉 TEST THÀNH CÔNG! Bot đã hoạt động và lưu dữ liệu ổn định.")
        else:
            logger.warning("⚠️ Bot chạy xong nhưng không lưu được bài nào (có thể do bài trùng hoặc spam).")

    except Exception as e:
        logger.error(f"💥 Lỗi nghiêm trọng khi đang test: {e}")

if __name__ == "__main__":
    run_test()
