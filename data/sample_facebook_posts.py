# data/sample_facebook_posts.py
"""
Dữ liệu giả lập Facebook posts để test pipeline.
Bao gồm đầy đủ các loại:
- Job hợp lệ
- Spam/Scam
- Duplicate
- Near-duplicate
- Thiếu thông tin
"""

SAMPLE_POSTS = [

    # ════════════════════════════════
    # ✅ NHÓM 1: JOB HỢP LỆ (8 posts)
    # ════════════════════════════════

    {
        "id": "post_001",
        "content": """TUYỂN DỤNG GẤP 💼
Nhà hàng Hải Sản Biển Đông cần tuyển:
- 3 Phục vụ nam/nữ
- 2 Nhân viên bếp phụ
Lương: 6.5 triệu + ăn ca + tip
Ca làm: 10h-22h (nghỉ trưa 1 tiếng)
Địa chỉ: 123 Trần Phú, Đà Nẵng
LH: 0905123456 - Chị Lan""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/001",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "2 giờ trước",
        "expected": "valid",
    },

    {
        "id": "post_002",
        "content": """Quán Cà Phê The Coffee House - Chi nhánh Đà Nẵng
TUYỂN: Nhân viên pha chế part-time
⏰ Ca tối: 17h00 - 22h00
💰 Lương: 25.000đ/giờ + thưởng doanh thu
📍 Nguyễn Văn Linh, Đà Nẵng
📞 0901234567
Yêu cầu: Ngoại hình dễ nhìn, nhanh nhẹn""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/002",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "3 giờ trước",
        "expected": "valid",
    },

    {
        "id": "post_003",
        "content": """[TUYỂN GẤP - ĐÀ NẴNG]
Cần tuyển Shipper giao hàng khu vực Hải Châu, Thanh Khê
- Có xe máy, bằng lái
- Thành thạo đường Đà Nẵng
Thu nhập: 8-12 triệu/tháng (lương cứng + hoa hồng)
Thời gian: Full-time hoặc Part-time
SĐT: 0933445566""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/003",
        "group_name": "Hội Việc Làm Đà Nẵng",
        "group_id": "group_002",
        "posted_time": "5 giờ trước",
        "expected": "valid",
    },

    {
        "id": "post_004",
        "content": """TUYỂN NHÂN VIÊN KHO
Công ty TNHH Logistics Miền Trung cần tuyển:
5 nhân viên bốc xếp kho hàng
Lương: 7 triệu/tháng + phụ cấp chuyên cần 500k
Ca: 7h-16h hoặc 14h-22h
Địa điểm: KCN Hòa Khánh, Đà Nẵng
Liên hệ: Anh Minh - 0977888999
Ưu tiên có kinh nghiệm kho bãi""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/004",
        "group_name": "Việc Làm Thời Vụ Đà Nẵng",
        "group_id": "group_003",
        "posted_time": "6 giờ trước",
        "expected": "valid",
    },

    {
        "id": "post_005",
        "content": """Nhà hàng Madame Lân tuyển dụng
Vị trí: Thu ngân + Lễ tân
Số lượng: 2 người
Mức lương: 7.5 triệu + thưởng KPI
Giờ làm: Full-time 8h-17h
Yêu cầu: Tốt nghiệp THPT, ngoại hình ưa nhìn
Kỹ năng: Word, Excel cơ bản
Địa chỉ: 4 Bạch Đằng, Hải Châu, Đà Nẵng
Contact: HR - 0888123456""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/005",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "8 giờ trước",
        "expected": "valid",
    },

    {
        "id": "post_006",
        "content": """Tuyển sinh viên làm thêm - Phát tờ rơi + Telesale
Thời gian: Linh hoạt theo lịch học
Thu nhập: 30.000đ/giờ
Khu vực: Ngũ Hành Sơn, Đà Nẵng
Phù hợp sinh viên ĐH Duy Tân, FPT
LH: 0911222333 - Ms Hoa""",
        "post_url": "https://facebook.com/groups/sinhvien_danang/posts/006",
        "group_name": "Việc Làm Sinh Viên Đà Nẵng",
        "group_id": "group_004",
        "posted_time": "10 giờ trước",
        "expected": "valid",
    },

    {
        "id": "post_007",
        "content": """RESORT DANANG BEACH TUYỂN DỤNG
- Nhân viên phục vụ bàn: 5 người
- Nhân viên buồng phòng: 3 người
- Bảo vệ ca đêm: 2 người
Lương từ 6 đến 8 triệu tùy vị trí
Bao ăn ở hoặc phụ cấp 1 triệu/tháng
Địa chỉ: Võ Nguyên Giáp, Đà Nẵng
Gọi ngay: 0922334455""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/007",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "12 giờ trước",
        "expected": "valid",
    },

    {
        "id": "post_008",
        "content": """Cần gấp nhân viên bán hàng online
Shop thời trang nữ Đà Nẵng tuyển:
1 bạn nữ chụp ảnh + đăng bài Facebook/TikTok
Biết dùng Canva, chụp ảnh đẹp là lợi thế
Lương cứng 5tr + % doanh thu
Làm tại nhà hoặc tại shop (Sơn Trà, Đà Nẵng)
Inbox hoặc gọi 0944556677""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/008",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "15 giờ trước",
        "expected": "valid",
    },

    # ════════════════════════════════
    # 🚫 NHÓM 2: SPAM / SCAM (5 posts)
    # ════════════════════════════════

    {
        "id": "post_spam_001",
        "content": """💰 THU NHẬP KHỦNG 30-50 TRIỆU/THÁNG 💰
Không cần kinh nghiệm, không cần bằng cấp
Làm việc tại nhà, thời gian tự do
Chỉ cần điện thoại + internet
Inbox ngay để biết thêm chi tiết!!!
Đã có hàng trăm người thành công""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/spam_001",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "1 giờ trước",
        "expected": "spam",
    },

    {
        "id": "post_spam_002",
        "content": """TUYỂN CTV ONLINE toàn quốc
Việc nhẹ lương cao, làm tại nhà
Thu nhập 500k - 2 triệu/ngày
Không cần kinh nghiệm
Chỉ cần bỏ ra 200k phí tài liệu để bắt đầu
Liên hệ Zalo: 0999000111""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/spam_002",
        "group_name": "Hội Việc Làm Đà Nẵng",
        "group_id": "group_002",
        "posted_time": "2 giờ trước",
        "expected": "spam",
    },

    {
        "id": "post_spam_003",
        "content": """Cơ hội kiếm tiền thụ động cùng hệ thống
Chỉ cần giới thiệu người thân bạn bè
Hoa hồng lên đến 40%
Đầu tư ban đầu chỉ 500k
Thu nhập không giới hạn
Đây không phải đa cấp nhé các bạn ơi 😊""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/spam_003",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "3 giờ trước",
        "expected": "spam",
    },

    {
        "id": "post_spam_004",
        "content": """TUYỂN DỤNG GẤP - THU NHẬP KHỦNG
Ngồi nhà kiếm tiền 20-30 triệu/tháng
Không cần đi làm, không cần kinh nghiệm
Chỉ cần có thời gian rảnh
Cọc 300k lấy tài khoản làm việc
Hoàn cọc sau 3 ngày làm việc""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/spam_004",
        "group_name": "Hội Việc Làm Đà Nẵng",
        "group_id": "group_002",
        "posted_time": "4 giờ trước",
        "expected": "spam",
    },

    {
        "id": "post_spam_005",
        "content": """Việc làm online uy tín - Không lừa đảo
Kiếm 500k-1 triệu mỗi ngày
Làm tại nhà hoàn toàn
Không cần kinh nghiệm gì cả
Thu nhập khủng, ổn định lâu dài
Inbox mình để được hướng dẫn miễn phí""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/spam_005",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "5 giờ trước",
        "expected": "spam",
    },

    # ══════════════════════════════════
    # ♻️  NHÓM 3: DUPLICATE (3 posts)
    # ══════════════════════════════════

    # Exact duplicate của post_001
    {
        "id": "post_dup_001",
        "content": """TUYỂN DỤNG GẤP 💼
Nhà hàng Hải Sản Biển Đông cần tuyển:
- 3 Phục vụ nam/nữ
- 2 Nhân viên bếp phụ
Lương: 6.5 triệu + ăn ca + tip
Ca làm: 10h-22h (nghỉ trưa 1 tiếng)
Địa chỉ: 123 Trần Phú, Đà Nẵng
LH: 0905123456 - Chị Lan""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/dup_001",
        "group_name": "Hội Việc Làm Đà Nẵng",
        "group_id": "group_002",
        "posted_time": "1 giờ trước",
        "expected": "duplicate",
    },

    # Near-duplicate của post_001 (thay đổi nhỏ)
    {
        "id": "post_dup_002",
        "content": """TUYỂN DỤNG GẤP
Nhà hàng Hải Sản Biển Đông cần tuyển gấp:
- 3 bạn Phục vụ nam/nữ
- 2 bạn phụ bếp
Lương: 6.5 triệu + ăn ca + tip
Giờ làm: 10h-22h nghỉ trưa 1 tiếng
Địa chỉ: 123 Trần Phú Đà Nẵng
LH: 0905123456 Chị Lan""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/dup_002",
        "group_name": "Việc Làm Thời Vụ Đà Nẵng",
        "group_id": "group_003",
        "posted_time": "30 phút trước",
        "expected": "near_duplicate",
    },

    # Same phone number → duplicate
    {
        "id": "post_dup_003",
        "content": """Tìm người làm phục vụ nhà hàng hải sản
Khu vực Trần Phú Đà Nẵng
Lương thỏa thuận, có ăn ca
Liên hệ: 0905123456""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/dup_003",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "20 phút trước",
        "expected": "phone_duplicate",
    },

    # ══════════════════════════════════════
    # ⚠️  NHÓM 4: THIẾU THÔNG TIN (2 posts)
    # ══════════════════════════════════════

    {
        "id": "post_missing_001",
        "content": "Tuyển gấp phục vụ. Inbox để biết thêm.",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/missing_001",
        "group_name": "Việc Làm Đà Nẵng",
        "group_id": "group_001",
        "posted_time": "1 giờ trước",
        "expected": "low_quality",
    },

    {
        "id": "post_missing_002",
        "content": """Cần tuyển gấp nhiều vị trí
Lương cao, môi trường tốt
Liên hệ ngay kẻo hết chỗ""",
        "post_url": "https://facebook.com/groups/vieclam_danang/posts/missing_002",
        "group_name": "Hội Việc Làm Đà Nẵng",
        "group_id": "group_002",
        "posted_time": "2 giờ trước",
        "expected": "low_quality",
    },
]

# Thống kê dataset
DATASET_STATS = {
    "total": len(SAMPLE_POSTS),
    "valid": len([p for p in SAMPLE_POSTS if p["expected"] == "valid"]),
    "spam": len([p for p in SAMPLE_POSTS if p["expected"] == "spam"]),
    "duplicate": len([p for p in SAMPLE_POSTS
                      if "duplicate" in p["expected"]]),
    "low_quality": len([p for p in SAMPLE_POSTS
                        if p["expected"] == "low_quality"]),
}