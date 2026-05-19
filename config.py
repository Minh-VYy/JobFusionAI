"""
=============================================
Core Configuration & Settings
AI Agent Job Scraper System
=============================================
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Base Directories ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

# ── Database ──────────────────────────────────────────────────────────────────
# SQL Server - Named Instance
# Server: CHAOOO\CHAUTRUONG  |  User: chaut
# Lưu ý: dấu \ viết thành %5C trong URL, hoặc dùng ODBC_CONNECTION_STRING
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mssql+pyodbc://sa:123456@MVY_350/findJob"
    "?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes"
)

# --- Hoặc dùng ODBC connection string trực tiếp (linh hoạt hơn) ---
# Nếu DATABASE_URL không hoạt động, set biến này trong .env:
# USE_ODBC_STRING=true
# ODBC_CONNECTION_STRING=DRIVER={ODBC Driver 17 for SQL Server};SERVER=THIEUQUANG;DATABASE=findJob;UID=quang123;PWD=123;TrustServerCertificate=yes;
USE_ODBC_STRING    = os.getenv("USE_ODBC_STRING", "false").lower() == "true"
ODBC_CONN_STRING   = os.getenv("ODBC_CONNECTION_STRING", "")
REDIS_URL    = os.getenv("REDIS_URL",    "redis://localhost:6379/0")

# ── AI / LLM ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# ── Geocoding ─────────────────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
OPENCAGE_API_KEY = os.getenv(
    "OPENCAGE_API_KEY", ""
)  # Từ https://opencagedata.com (2,500 req/day miễn phí)
DEFAULT_CENTER_LAT = float(os.getenv("DEFAULT_CENTER_LAT", "16.0544"))  # Đà Nẵng
DEFAULT_CENTER_LNG = float(os.getenv("DEFAULT_CENTER_LNG", "108.2022"))
DEFAULT_RADIUS_KM = float(os.getenv("DEFAULT_RADIUS_KM", "5.0"))

# ── Scraping ──────────────────────────────────────────────────────────────────
SCRAPE_DELAY_MIN = float(os.getenv("SCRAPE_DELAY_MIN", "2.0"))
SCRAPE_DELAY_MAX = float(os.getenv("SCRAPE_DELAY_MAX", "5.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
USE_HEADLESS = os.getenv("USE_HEADLESS", "true").lower() == "true"

# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# ── App ───────────────────────────────────────────────────────────────────────
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Scraping Sources ──────────────────────────────────────────────────────────
SCRAPING_SOURCES = {
    "vietnamworks": {
        "base_url": "https://www.vietnamworks.com",
        "search_url": "https://www.vietnamworks.com/tim-viec-lam-tat-ca",
        "enabled": True,
        "priority": 1,
    },
    "topcv": {
        "base_url": "https://www.topcv.vn",
        "search_url": "https://www.topcv.vn/tim-viec-lam-tat-ca",
        "enabled": True,
        "priority": 2,
    },
    "itviec": {
        "base_url": "https://itviec.com",
        "search_url": "https://itviec.com/viec-lam-it",
        "enabled": True,
        "priority": 3,
    },
}

# ── Vector Store ──────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR = str(BASE_DIR / "data" / "chroma_db")
CHROMA_COLLECTION = "job_embeddings"

# ── Knowledge Graph ───────────────────────────────────────────────────────────
SKILL_CATEGORIES = {
    "programming": [
        "Python",
        "Java",
        "JavaScript",
        "TypeScript",
        "C++",
        "Go",
        "Rust",
        "PHP",
        "Ruby",
    ],
    "data_science": [
        "Machine Learning",
        "Deep Learning",
        "Data Science",
        "AI",
        "NLP",
        "Computer Vision",
    ],
    "web_frontend": ["React", "Vue", "Angular", "HTML", "CSS", "Next.js", "Svelte"],
    "web_backend": [
        "Django",
        "FastAPI",
        "Spring Boot",
        "Node.js",
        "Express",
        "Laravel",
    ],
    "database": ["PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "SQLite"],
    "devops": [
        "Docker",
        "Kubernetes",
        "CI/CD",
        "Jenkins",
        "GitHub Actions",
        "AWS",
        "Azure",
        "GCP",
    ],
    "mobile": ["React Native", "Flutter", "Swift", "Kotlin", "Android", "iOS"],
}
