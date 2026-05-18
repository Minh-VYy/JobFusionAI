import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cleaner.facebook_cleaner import FacebookCleaner
c = FacebookCleaner()

vi_content = """Văn Cảm
·
50 phút
·
☕ S’STORY COFFEE TUYỂN DỤNG ☕
1️⃣ Barista
🕘 Ca: 6:00 – 14:00 / 14:00 – 22:00
🕒 Hoặc: 6h-11h / 17h-22h
✅ Yêu cầu:
Nam/Nữ 18-25 tuổi
Có kinh nghiệm ở vị trí tương tự là lợi thế
Chủ động & có trách nhiệm trong công việc
Đam mê, thích học hỏi
Biết Art hình cơ bản
💰 Mức lương: (tùy năng lực & kinh nghiệm)
2️⃣ Phục vụ
🕘 Ca: 6:00 – 14:00 / 14:00 – 22:00
🕒 Hoặc: 6h-11h / 17h-22h
✅ Yêu cầu:
Nam/Nữ 18-25 tuổi
Chủ động & có trách nhiệm
Biết quan sát
💰 Mức lương:(tùy năng lực & kinh nghiệm)
📍 Địa chỉ: 119 Huỳnh Thúc Kháng – Hải Châu – Đà Nẵng
📞 Liên hệ: 0852161204 (Nam)"""

print('Title:', c.extract_title(vi_content))
print('Company:', c.extract_company(vi_content))
print('Salary:', c.extract_salary(vi_content))
print('Skills:', c.extract_skills(vi_content))
print('Location:', c.extract_location(vi_content))
print('Requirements:', repr(c.extract_requirements(vi_content)))
