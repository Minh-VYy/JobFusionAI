# models/job_model.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class JobModel:
    """
    Schema chuẩn cho 1 job record.
    Tất cả crawler đều phải trả về object này.
    """
    # === Thông tin cơ bản ===
    title: str = ""              # Tên vị trí: "Python Developer"
    company: str = ""            # Tên công ty: "FPT Software"
    salary: str = ""             # Lương: "15-25 triệu" hoặc "Thỏa thuận"
    location: str = ""           # Địa điểm: "Hà Nội, TP.HCM"
    
    # === Thông tin chi tiết ===
    skills: list = field(default_factory=list)   # ["Python", "Django", "SQL"]
    description: str = ""        # Mô tả công việc đầy đủ
    requirements: str = ""       # Yêu cầu ứng viên
    
    # === Metadata ===
    job_url: str = ""            # Link job gốc
    source: str = ""             # "topcv" | "vietnamworks" | "itviec"
    posted_date: Optional[str] = None   # Ngày đăng
    crawled_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    
    def to_dict(self) -> dict:
        """Convert sang dict để lưu DB hoặc export CSV"""
        return {
            "title": self.title,
            "company": self.company,
            "salary": self.salary,
            "location": self.location,
            "skills": ", ".join(self.skills) if self.skills else "",
            "description": self.description,
            "requirements": self.requirements,
            "job_url": self.job_url,
            "source": self.source,
            "posted_date": self.posted_date,
            "crawled_at": self.crawled_at,
        }
