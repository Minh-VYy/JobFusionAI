"""
=============================================
Database Models - SQLAlchemy ORM
Lớp 4: Data Storage / Retrieval Layer
Database: Microsoft SQL Server (pyodbc)
=============================================
"""
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Boolean, Text, ForeignKey, event
)
from sqlalchemy.dialects.mssql import NVARCHAR, NTEXT
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
import enum
import config

# SQL Server không hỗ trợ JSON type native → dùng NVARCHAR(MAX) lưu JSON string
# Dùng helper để serialize/deserialize
import json as _json
from sqlalchemy.types import TypeDecorator, Text as SAText

class JSONType(TypeDecorator):
    """Lưu JSON dưới dạng NVARCHAR(MAX) trong SQL Server."""
    impl = NVARCHAR(None)  # NVARCHAR(MAX)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _json.loads(value)
        except (TypeError, ValueError):
            return value


# ── Base ──────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Enumerations ──────────────────────────────────────────────────────────────
class JobStatus(enum.Enum):
    PENDING   = "pending"     # Chờ kiểm duyệt (Reflection Agent)
    APPROVED  = "approved"    # Admin đã duyệt
    REJECTED  = "rejected"    # Bị từ chối
    EXPIRED   = "expired"     # Hết hạn


class ScrapeStatus(enum.Enum):
    IDLE      = "idle"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    PAUSED    = "paused"


# ── Job Model ─────────────────────────────────────────────────────────────────
class Job(Base):
    """Bảng lưu trữ thông tin việc làm đã cào và làm sạch."""
    __tablename__ = "jobs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    title           = Column(String(500), nullable=False)
    company         = Column(String(300))
    description     = Column(Text)
    requirements    = Column(Text)
    salary_min      = Column(Float, nullable=True)   # Lương tối thiểu (VND)
    salary_max      = Column(Float, nullable=True)   # Lương tối đa (VND)
    salary_raw      = Column(String(200))            # Lương dạng text gốc
    address_raw     = Column(String(500))            # Địa chỉ text gốc
    address_clean   = Column(String(500))            # Địa chỉ đã chuẩn hóa
    latitude        = Column(Float, nullable=True)   # Tọa độ GPS
    longitude       = Column(Float, nullable=True)
    geocoding_confidence = Column(Float, default=0.0) # Độ tin cậy geocoding 0-1

    source_url      = Column(String(1000))
    source_name     = Column(String(100))            # vietnamworks / topcv / itviec
    external_id     = Column(String(200))            # ID gốc trên site nguồn
    
    job_type        = Column(String(100))            # Full-time / Part-time / Remote
    experience_year = Column(String(100))
    education       = Column(String(200))
    skills          = Column(JSONType, default=list)  # Lưu JSON trong NVARCHAR(MAX)
    industry        = Column(String(200))

    # SQL Server: dùng String thay Enum (tránh lỗi type mapping)
    status          = Column(String(20), default=JobStatus.PENDING.value)
    is_geocoded     = Column(Boolean, default=False)
    needs_review    = Column(Boolean, default=False) # Phản ảnh từ Reflection Agent
    review_notes    = Column(Text)                   # Ghi chú của Reflection Agent

    posted_date     = Column(DateTime, nullable=True)
    deadline        = Column(DateTime, nullable=True)
    scraped_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Vector embedding (stored as NVARCHAR(MAX) JSON)
    embedding       = Column(JSONType, nullable=True)

    # Relationships
    user_interactions = relationship("UserInteraction", back_populates="job", cascade="all, delete-orphan")
    locations         = relationship("JobLocation", back_populates="job", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":           self.id,
            "title":        self.title,
            "company":      self.company,
            "salary_min":   self.salary_min,
            "salary_max":   self.salary_max,
            "salary_raw":   self.salary_raw,
            "address_clean": self.address_clean,
            "latitude":     self.latitude,
            "longitude":    self.longitude,
            "source_url":   self.source_url,
            "source_name":  self.source_name,
            "job_type":     self.job_type,
            "skills":       self.skills or [],
            "status":       self.status,  # Đã là string
            "needs_review": self.needs_review,
            "posted_date":  self.posted_date.isoformat() if self.posted_date else None,
            "scraped_at":   self.scraped_at.isoformat() if self.scraped_at else None,
            "geocoding_confidence": self.geocoding_confidence,
            "locations":    [
                {
                    "id": loc.id,
                    "address_text": loc.address_text,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "geocoding_confidence": loc.geocoding_confidence
                } for loc in self.locations
            ] if self.locations else []
        }


# ── Job Location Model ────────────────────────────────────────────────────────
class JobLocation(Base):
    """Bảng lưu trữ nhiều địa điểm làm việc chi tiết cho một job."""
    __tablename__ = "job_locations"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    job_id                  = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    address_text            = Column(NVARCHAR(500), nullable=False)
    latitude                = Column(Float, nullable=True)
    longitude               = Column(Float, nullable=True)
    geocoding_confidence    = Column(Float, default=0.0)

    # Relationships
    job = relationship("Job", back_populates="locations")


# ── Scrape Task Model ─────────────────────────────────────────────────────────
class ScrapeTask(Base):
    """Quản lý lịch trình và trạng thái các tác vụ cào dữ liệu."""
    __tablename__ = "scrape_tasks"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(200), nullable=False)
    source_name   = Column(String(100))
    seed_url      = Column(String(1000), nullable=False)
    max_pages     = Column(Integer, default=10)
    max_depth     = Column(Integer, default=3)          # Deep crawling depth
    
    status        = Column(String(20), default=ScrapeStatus.IDLE.value)  # String thay Enum
    schedule_cron = Column(String(100))                 # Cron expression, vd: "0 8 * * *"
    is_scheduled  = Column(Boolean, default=False)
    
    # Thống kê
    total_found   = Column(Integer, default=0)
    total_scraped = Column(Integer, default=0)
    total_errors  = Column(Integer, default=0)
    
    last_run_at   = Column(DateTime, nullable=True)
    next_run_at   = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    error_log     = Column(Text)

    def to_dict(self):
        return {
            "id":            self.id,
            "name":          self.name,
            "source_name":   self.source_name,
            "seed_url":      self.seed_url,
            "max_pages":     self.max_pages,
            "max_depth":     self.max_depth,
            "status":        self.status,  # Đã là string
            "schedule_cron": self.schedule_cron,
            "is_scheduled":  self.is_scheduled,
            "total_found":   self.total_found,
            "total_scraped": self.total_scraped,
            "total_errors":  self.total_errors,
            "last_run_at":   self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at":   self.next_run_at.isoformat() if self.next_run_at else None,
        }


# ── User Model ────────────────────────────────────────────────────────────────
class User(Base):
    """Người dùng cuối - tìm kiếm việc làm."""
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    username     = Column(String(100), unique=True, nullable=False)
    email        = Column(String(200), unique=True)
    password_hash= Column(String(300))
    full_name    = Column(String(200))
    
    # Vị trí người dùng
    latitude     = Column(Float, nullable=True)
    longitude    = Column(Float, nullable=True)
    address      = Column(String(500))
    
    # Tùy chọn tìm kiếm
    preferred_radius_km = Column(Float, default=5.0)
    preferred_skills    = Column(JSONType, default=list)  # NVARCHAR(MAX)
    preferred_salary_min= Column(Float, nullable=True)

    # CV vector embedding
    cv_text      = Column(NVARCHAR(None))    # NVARCHAR(MAX)
    cv_embedding = Column(JSONType, nullable=True)
    
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    last_login   = Column(DateTime, nullable=True)

    # Relationships
    interactions = relationship("UserInteraction", back_populates="user", cascade="all, delete-orphan")


# ── User Interaction (Feedback Loop) ─────────────────────────────────────────
class UserInteraction(Base):
    """Ghi nhận hành vi người dùng - Self-learning feedback loop."""
    __tablename__ = "user_interactions"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    job_id         = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    
    action         = Column(String(50))  # click / save / apply / dismiss / rate
    rating         = Column(Integer, nullable=True)  # 1-5
    search_query   = Column(String(500))
    user_lat       = Column(Float, nullable=True)
    user_lng       = Column(Float, nullable=True)
    session_id     = Column(String(100))
    
    created_at     = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="interactions")
    job  = relationship("Job", back_populates="user_interactions")


# ── Skill Node (Knowledge Graph) ─────────────────────────────────────────────
class SkillNode(Base):
    """Node trong Knowledge Graph - lưu kỹ năng."""
    __tablename__ = "skill_nodes"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    name     = Column(NVARCHAR(200), unique=True, nullable=False)
    category = Column(String(100))
    aliases  = Column(JSONType, default=list)  # NVARCHAR(MAX)
    weight   = Column(Float, default=1.0)  # Độ phổ biến


class SkillRelation(Base):
    """Cạnh trong Knowledge Graph - quan hệ giữa các kỹ năng."""
    __tablename__ = "skill_relations"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    skill_from   = Column(String(200), nullable=False)
    skill_to     = Column(String(200), nullable=False)
    relation_type= Column(String(100))   # "related_to", "requires", "part_of"
    weight       = Column(Float, default=1.0)


# ── Active Learning & Corrections ─────────────────────────────────────────────
class JobCorrection(Base):
    """Lưu trữ lịch sử chỉnh sửa dữ liệu của Admin để bot tự học."""
    __tablename__ = "job_corrections"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    job_id       = Column(Integer, nullable=False)
    field_name   = Column(String(100), nullable=False)  # 'title', 'company', 'salary_min', etc.
    old_value    = Column(Text, nullable=True)
    new_value    = Column(Text, nullable=True)
    corrected_at = Column(DateTime, default=datetime.utcnow)


class VerifiedEntity(Base):
    """Bộ nhớ thực thể động: SĐT/Địa chỉ đã xác thực thuộc về một Công ty."""
    __tablename__ = "verified_entities"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    entity_type    = Column(String(50), nullable=False)    # 'phone' hoặc 'address'
    entity_value   = Column(NVARCHAR(500), nullable=False)  # Giá trị SĐT hoặc Địa chỉ chuẩn hóa
    mapped_company = Column(NVARCHAR(300), nullable=False)  # Tên công ty chuẩn được gán
    verified_at    = Column(DateTime, default=datetime.utcnow)


# ── Database Engine (SQL Server Named Instance) ──────────────────────
def get_engine():
    """
    Tạo SQLAlchemy engine cho SQL Server.
    Hỗ trợ 2 phương thức kết nối:
      1. DATABASE_URL (chuẩn)
      2. ODBC_CONNECTION_STRING trực tiếp (cho Named Instance phức tạp)
    """
    import urllib

    if config.USE_ODBC_STRING and config.ODBC_CONN_STRING:
        # Phương thức 2: Dùng ODBC string trực tiếp
        # Ví dụ: DRIVER={ODBC Driver 17 for SQL Server};SERVER=CHAOOO\CHAUTRUONG;...
        params = urllib.parse.quote_plus(config.ODBC_CONN_STRING)
        conn_url = f"mssql+pyodbc:///?odbc_connect={params}"
    else:
        # Phương thức 1: Dùng DATABASE_URL tiêu chuẩn
        conn_url = config.DATABASE_URL

    engine = create_engine(
        conn_url,
        pool_pre_ping   = True,
        connect_args    = {"timeout": 30},
        fast_executemany= True,
    )
    return engine


def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return Session()


def init_db():
    """Khởi tạo toàn bộ schema trên SQL Server."""
    engine = get_engine()
    Base.metadata.create_all(engine, checkfirst=True)
    print("[DB] SQL Server schema initialized successfully")
    return engine
