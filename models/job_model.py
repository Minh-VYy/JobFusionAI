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
    title: str = ""  # Tên vị trí: "Python Developer"
    company: str = ""  # Tên công ty: "FPT Software"
    salary: str = ""  # Lương: "15-25 triệu" hoặc "Thỏa thuận"
    location: str = ""  # Địa điểm: "Hà Nội, TP.HCM"

    # === Thông tin chi tiết ===
    skills: list = field(default_factory=list)  # ["Python", "Django", "SQL"]
    description: str = ""  # Mô tả công việc đầy đủ
    requirements: str = ""  # Yêu cầu ứng viên

    # === Salary Details ===
    salary_min: Optional[float] = None  # Lương tối thiểu (triệu VND)
    salary_max: Optional[float] = None  # Lương tối đa (triệu VND)

    # === Job Requirements ===
    job_type: Optional[str] = None  # "Full-time", "Part-time", "Contract"
    experience_year: Optional[str] = None  # "2-3 năm" hoặc "Không yêu cầu"
    education: Optional[str] = None  # "Đại học", "Cao đẳng", "Trung cấp"
    industry: Optional[str] = None  # Ngành nghề / Job Domain

    # === Address Details ===
    address_raw: Optional[str] = None  # Địa chỉ thô từ website
    address_clean: Optional[str] = None  # Địa chỉ đã normalize

    # === Contact & Deadline ===
    deadline: Optional[str] = None  # Hạn nộp hồ sơ (YYYY-MM-DD)
    phone: Optional[str] = None  # Số điện thoại liên hệ (nếu có)

    # === Metadata ===
    job_url: str = ""  # Link job gốc
    source: str = ""  # "topcv" | "vietnamworks" | "itviec"
    posted_date: Optional[str] = None  # Ngày đăng
    crawled_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    def to_dict(self) -> dict:
        """Convert sang dict để lưu DB hoặc export CSV"""
        return {
            "title": self.title,
            "company": self.company,
            "salary": self.salary,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "location": self.location,
            "address_raw": self.address_raw,
            "address_clean": self.address_clean,
            "skills": ", ".join(self.skills) if self.skills else "",
            "description": self.description,
            "requirements": self.requirements,
            "job_type": self.job_type,
            "experience_year": self.experience_year,
            "education": self.education,
            "industry": self.industry,
            "deadline": self.deadline,
            "phone": self.phone,
            "job_url": self.job_url,
            "source": self.source,
            "posted_date": self.posted_date,
            "crawled_at": self.crawled_at,
        }
