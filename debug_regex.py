import re

lines = [
    "1\ufe0f\u20e3 Barista",
    "2\ufe0f\u20e3 Phuc vu",
    "1️⃣ Barista",
    "2️⃣ Phuc vu",
    "2️⃣ Phục vụ"
]

numbered_pos_re = re.compile(
    r'^(?:[1-9]️⃣|[\u2460-\u2473]|[1-9][\.\)]|[1-9]\s)\s*'
    r'((?:barista|phục vụ|nhân viên|thu ngân|đầu bếp|phụ bếp|pha chế|'
    r'bartender|bảo vệ|tài xế|shipper|kế toán|lập trình|kỹ thuật|'
    r'thiết kế|marketing|sale|sales|tư vấn|quản lý|pha chế|cửa hàng|'
    r'trưởng|giám sát|chuyên viên|trợ lý|thực tập)[^\n]{0,50})',
    re.IGNORECASE
)

for line in lines:
    m = numbered_pos_re.match(line)
    # clean string to print safely
    safe_line = line.encode('ascii', errors='replace').decode('ascii')
    print(safe_line, "->", repr(m.group(1).encode('ascii', errors='replace').decode('ascii')) if m else "no match")
