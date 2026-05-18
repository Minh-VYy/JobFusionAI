# 🤖 JobAgent Đà Nẵng - AI Powered Job Crawler & Active Learning System

Hệ thống tự động thu thập, phân tích, lập bản đồ và kiểm duyệt tin tuyển dụng thông minh tại Đà Nẵng (hỗ trợ TopCV, ITviec, VietnamWorks và Facebook Groups). Dự án tích hợp công nghệ Playwright vượt rào cản, xử lý ngôn ngữ tự nhiên (NLP) tiếng Việt, và cơ chế **Human-in-the-Loop (Con người trong vòng lặp)** giúp AI liên tục học hỏi từ các hiệu chỉnh của quản trị viên để ngày càng thông minh hơn.

---

## 🏗️ Kiến trúc Tổng quan hệ thống

Dự án được xây dựng theo mô hình pipeline khép kín kết hợp vòng lặp phản hồi chủ động (Feedback Loop):

```text
                                  ┌────────────────────────┐
                                  │   Crawler (Playwright) │
                                  └───────────┬────────────┘
                                              │
                                              ▼
                                  ┌────────────────────────┐
                                  │ NLP & Cleaner Pipeline │
                                  └───────────┬────────────┘
                                              │
                                              ▼
                                  ┌────────────────────────┐
                                  │ SQL Server Database    │◀────────────────┐
                                  └───────────┬────────────┘                 │
                                              │                              │
                                              ▼                              │
┌────────────────────────┐        ┌────────────────────────┐                 │
│ Dynamic Memory Cache   │◄───────┤ FastAPI API Server     ├────────┐        │
│ (SĐT, Địa chỉ, Cty...) │        └───────────┬────────────┘        │        │
└───────────┬────────────┘                    │                     │        │
            │                                 ▼                     │        │ (Feedback
            │                     ┌────────────────────────┐        │ (Save) │  Loop)
            │                     │ Admin UI Dashboard     │        │        │
            │                     │ (Duyệt & Chỉnh Sửa)    │        │        │
            │                     └───────────┬────────────┘        │        │
            │                                 │                     │        │
            │                                 ▼                     │        │
            │                     ┌────────────────────────┐        │        │
            └────────────────────►│ AI Model / Rule Update ├────────┼────────┘
             (Auto Apply)         └────────────────────────┘        │
                                                                    ▼
                                                       ┌────────────────────────┐
                                                       │ Training Dataset (CSV) │
                                                       │   (Dữ liệu chuẩn hóa)  │
                                                       └────────────────────────┘
```

---

## 🌟 Tính năng nổi bật

- **🌐 Crawl đa kênh linh hoạt**: Playwright vượt rào cản anti-bot (TopCV, ITviec, VietnamWorks) và cào tự động Facebook Groups không cần Token/API.
- **🧠 Hybrid NLP Engine**: Kết hợp Dictionary, Regex cải tiến và Heuristics để bóc tách Kỹ năng chuyên sâu, Khoảng lương, Số điện thoại và Địa điểm.
- **📍 Geocoding & Mapping**: Tự động trích xuất địa chỉ thực tế và ánh xạ tọa độ GPS (Latitude/Longitude) độ chính xác cao.
- **🔎 Admin Dashboard (Kiểm duyệt thông minh)**: Giao diện quản trị hiện đại hỗ trợ:
  - Giám sát Real-time các Agent đang cào bằng Websocket.
  - Phân tích biểu đồ kỹ năng, địa điểm, mức lương tuyển dụng.
  - **Duyệt và Chỉnh sửa trực tiếp** các tin tuyển dụng bị lỗi thông tin.
- **🔄 Active Learning (AI Tự Học)**:
  - **Lưu vết hiệu chỉnh**: Hệ thống ghi lại dữ liệu cũ (bot cào) và dữ liệu mới (admin sửa) vào bảng `job_corrections`.
  - **Bộ nhớ thực thể động (Dynamic Entity Whitelist)**: Tự động ghi nhớ SĐT, địa chỉ đã xác thực của Công ty. Ở các phiên cào sau, bot sẽ áp dụng ngay thông tin chuẩn này mà không cần tính toán lại.
  - **Tạo Dataset Vàng (Gold Dataset)**: Xuất dữ liệu đã duyệt ra file CSV để làm tài liệu huấn luyện mô hình Machine Learning chuyên biệt sau này.

---

## 📂 Cấu trúc thư mục

```text
├── crawler/                  # Các Scraper Agents chuyên biệt (Playwright)
│   ├── facebook_crawler.py   # Cào bài viết từ các Group Facebook tuyển dụng
│   ├── topcv_crawler.py      # Cào TopCV
│   └── ...
├── cleaner/                  # Pipeline làm sạch và xử lý NLP
│   ├── facebook_cleaner.py   # Chuẩn hóa & trích xuất dữ liệu từ text Facebook
│   ├── facebook_nlp.py       # Chấm điểm bài đăng chất lượng / tin rác
│   ├── skill_extractor.py    # Trích xuất kỹ năng công nghệ
│   └── geocoder.py           # Địa chỉ -> Tọa độ GPS
├── database/                 # Kết nối & xử lý Database SQL Server
│   ├── db_handler.py         # Thao tác INSERT/SELECT/UPDATE jobs
│   ├── facebook_db.py        # Thao tác riêng cho kênh Facebook
│   └── init_db.sql           # Schema SQL Server chính thức
├── static/                   # Giao diện Frontend Admin Panel (HTML, CSS, JS)
│   ├── admin.html            # Trang quản trị chính
│   ├── admin.js              # Xử lý gọi API, vẽ biểu đồ, WebSocket
│   └── index.html            # Giao diện tra cứu việc làm public cho người dùng
├── config.py                 # File cấu hình hệ thống toàn cục (.env)
├── main.py                   # Lập lịch Scheduler chạy Crawler tự động hàng ngày
├── server.py                 # Máy chủ FastAPI Backend (Cung cấp API cho Admin UI)
├── requirements.txt          # Danh sách thư viện cần thiết
└── README.md                 # Hướng dẫn dự án này
```

---

## 🚀 Hướng dẫn cài đặt & Khởi chạy

### 1. Cài đặt môi trường
Yêu cầu Python 3.9+ và SQL Server.
```bash
# Tạo môi trường ảo
python -m venv venv
venv\Scripts\activate

# Cài đặt thư viện
pip install -r requirements.txt

# Cài đặt Playwright
playwright install chromium
```

### 2. Cấu hình cơ sở dữ liệu (.env)
Tạo file `.env` từ `.env.example` và điền cấu hình SQL Server:
```env
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=LOCALHOST\SQLEXPRESS
DB_NAME=job_agent_db
DB_USER=sa
DB_PASSWORD=your_password

# Đọc cấu hình bảo mật cho FastAPI
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_admin_password
SECRET_KEY=generate_a_secure_random_key
```

Chạy script tạo bảng trong SQL Server bằng file [init_db.sql](file:///e:/CD_NgonNguLapTrinh/HeThongHoTroTimViec/CDNNLT/database/init_db.sql).

### 3. Khởi chạy hệ thống

- **Chạy Web Server API & Giao diện Admin**:
  ```bash
  python server.py
  ```
  Truy cập giao diện quản trị tại: `http://localhost:8000/static/admin.html`

- **Chạy Pipeline cào dữ liệu ngay lập tức**:
  ```bash
  python main.py now
  ```

---

## 🛠️ Lộ trình triển khai Cơ chế Tự học (Active Learning Pipeline)

1. [x] **Bước 1**: Thỏa thuận thiết kế & cập nhật tài liệu kiến trúc hệ thống (`README.md`).
2. [ ] **Bước 2**: Xây dựng máy chủ **FastAPI Backend (`server.py`)** để kết nối hoàn chỉnh Dashboard Kiểm duyệt (`admin.html`) với SQL Server Database.
3. [ ] **Bước 3**: Triển khai API `/api/admin/jobs/{id}/review` cho phép cập nhật dữ liệu sửa đổi của Quản trị viên và tự động lưu lịch sử sửa đổi vào bảng `job_corrections`.
4. [ ] **Bước 4**: Tích hợp **Dynamic Memory Cache**: Khi duyệt tin, hệ thống tự động lưu cặp `(Phone, Company)` hoặc `(Address, Company)` hợp lệ. Crawler lần sau sẽ đối chiếu trước để tối ưu độ chính xác lên 100% cho các công ty quen thuộc.
5. [ ] **Bước 5**: Viết Evaluation Script để tự động đánh giá độ chính xác (Accuracy, Precision, Recall) của bot dựa trên bộ dữ liệu đã được con người chuẩn hóa.

---
*Dự án thuộc Hệ thống Hỗ trợ Tìm việc làm Đà Nẵng - Minh-VYy/JobFusionAI*
