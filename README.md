# 🤖 Job Crawler & Analytics System (NLP Powered)

Hệ thống tự động thu thập, phân tích và lưu trữ dữ liệu việc làm từ các nền tảng tuyển dụng hàng đầu Việt Nam (TopCV, ITviec, VietnamWorks). Sử dụng công nghệ Playwright để vượt rào cản anti-bot và xử lý NLP để bóc tách kỹ năng chuyên sâu.

## 🌟 Tính năng nổi bật

- **🌐 Đa nền tảng**: Hỗ trợ crawl dữ liệu từ TopCV, ITviec và VietnamWorks.
- **🛡️ Anti-Bot**: Tự động thay đổi User-Agent, giả lập hành vi người dùng và ẩn danh tính automation để tránh bị chặn.
- **🧠 NLP Skill Extractor**: Tự động bóc tách các kỹ năng kỹ thuật (Python, Java, React, v.v.) từ mô tả công việc bằng thuật toán Dictionary + Pattern Matching.
- **📍 Geocoding**: Tự động chuyển đổi địa chỉ văn bản thành tọa độ (Latitude/Longitude) để hỗ trợ hiển thị bản đồ.
- **🗄️ Database Robust**: Tích hợp SQL Server với cơ chế chống trùng lặp dữ liệu thông minh dựa trên `external_id`.
- **⏰ Scheduler**: Tự động hóa việc quét dữ liệu theo lịch trình hàng ngày.
- **📢 Telegram Bot**: Gửi báo cáo kết quả (số lượng job mới, job trùng, lỗi) trực tiếp về điện thoại sau mỗi phiên làm việc.

## 🏗️ Kiến trúc hệ thống

```text
Crawl (Playwright) → Clean (Pandas) → NLP (Skills) → Geo (Coordinates) → Store (SQL Server)
```

**Cấu trúc thư mục:**
- `main.py`: Entry point điều khiển Scheduler và Pipeline chính.
- `crawler/`: Chứa các module Playwright chuyên biệt cho từng trang web.
- `cleaner/`: Xử lý làm sạch dữ liệu, trích xuất kỹ năng và Geocoding.
- `database/`: Quản lý kết nối SQL Server và xử lý truy vấn dữ liệu.
- `models/`: Định nghĩa cấu trúc dữ liệu Job đồng nhất.
- `.env`: Cấu hình hệ thống (DB, API Keys, Scheduler).

## 🚀 Hướng dẫn cài đặt

### 1. Cài đặt Python & Dependencies
Yêu cầu Python 3.9+.
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Cấu hình SQL Server
1. Tạo Database tên `job_agent_db`.
2. Chạy script trong `database/init_db.sql` để tạo bảng.
3. Đảm bảo đã enable giao thức **TCP/IP** trong SQL Server Configuration Manager.

### 3. Cấu hình môi trường (.env)
Tạo file `.env` từ mẫu và điền thông tin:
```env
DB_SERVER=localhost\SQLEXPRESS
DB_NAME=job_agent_db
DB_USER=sa
DB_PASSWORD=your_password
DB_DRIVER=ODBC Driver 17 for SQL Server

TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

CRAWL_PAGES=2
CRAWL_SCHEDULE_TIME=00:00
HEADLESS=True
```

## 🛠️ Cách sử dụng

### Chạy Pipeline ngay lập tức (Manual Run)
```bash
python main.py now
```

### Chạy ở chế độ Scheduler (Tự động hàng ngày)
```bash
python main.py
```

### Kiểm tra NLP độc lập
```bash
python test_nlp.py
```

## 📊 Kết quả đầu ra
- **Dữ liệu CSV**: Lưu tại `jobs_final.csv`.
- **Database**: Bảng `jobs` trong SQL Server với đầy đủ các trường đã chuẩn hóa.
- **Log**: Theo dõi tiến trình tại `app.log`.

---
*Dự án được phát triển cho mục đích học tập và nghiên cứu về Data Mining & AI Agents.*
# JobFusionAI
