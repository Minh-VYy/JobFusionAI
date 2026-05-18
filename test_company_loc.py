# test_company_loc.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cleaner.facebook_cleaner import FacebookCleaner
c = FacebookCleaner()

cases = [
    ("ID7-beer garden", """Can tuyen PG kenh beer garden part time 2 thang tai Da Nang
Khu vuc trung tam thanh pho
Luong: 350k/ca"""),
    ("ID7-vi dau", """Cần tuyển PG kênh beer garden part time 2 tháng tại Đà Nẵng
Khu vực trung tâm thành phố
Lương: 350k/ca"""),
    ("ID9-BUDWEISER", """BUDWEISER TUYỂN PG PART-TIME
260.000Đ/CA (5 GIỜ)
Khu vực tuyển:
• Bình Dương: Thành phố Thủ Dầu Một
• Đà Nẵng: Quận Cẩm Lệ, Quận Hải Châu, Quận Ngũ Hành Sơn
• Hồ Chí Minh: Quận 7, Quận 10
Liên hệ: 0886.537.348 (Tâm)"""),
    ("ID10-QUAN AN", """QUÁN ĂN TUYỂN 05 PHỤ BẾP
Địa chỉ: 46 Phan Thanh, Đà Nẵng
Lương: 10 triệu/tháng"""),
    ("ID11-KHAI TRUONG", """KHAI TRƯƠNG THỊ TRƯỜNG TẠI ĐÀ NẴNG
Khu vực: Hải Châu & Liên Chiểu
Thu nhập : 6-8.000.000đ/tháng + thưởng"""),
    ("Oggy Salmon", "Oggy Salmon tuyển Phục vụ Part Time tại Đà Nẵng\nLương 4tr5"),
    ("Ta Tua Tea", "Tà Tưa Tea cần tìm đồng đội gấp:\n20 nhân viên pha chế"),
    ("Bán hoa 107", "tuyển nhân viên bán hoa tốt nghiệp tại 107 võ nguyên giáp ngày 23/3 8h -18h\nzalo 0332347515"),
]

print(f"{'Bài':<25} | {'Company':<25} | {'Location':<45}")
print("-" * 98)
for name, text in cases:
    co = c.extract_company(text)
    loc = c.extract_location(text)
    print(f"{name:<25} | {co:<25} | {loc:<45}")
