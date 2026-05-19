# server.py
from pydantic._internal import _forward_ref
import sys
import os
import time
import json
import logging
import subprocess
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Form, WebSocket, WebSocketDisconnect, Body
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import jwt

import config
import db_models as models
from db_models import Job, ScrapeTask, User, UserInteraction, SkillNode, SkillRelation, JobCorrection, VerifiedEntity

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("server")

# --- Khởi tạo database schema ---
try:
    models.init_db()
    logger.info("✅ SQL Server database schema synchronized successfully.")
except Exception as e:
    logger.error(f"❌ Error during database schema initialization: {e}")

# --- FastAPI App ---
app = FastAPI(
    title="JobAgent API Server",
    description="Backend API phục vụ Admin Dashboard & Public Client",
    version="1.0.0"
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WebSocket Clients Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# --- Auth Helper (JWT) ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(lambda x=None: None)):
    # Đọc token từ header Authorization
    # Để đơn giản và tương thích với admin.js
    pass

# --- API Đăng nhập (Auth) ---
@app.post("/api/auth/login")
def login(username: str = Form(...), password: str = Form(...)):
    # 1. Kiểm tra Admin (Cấu hình trong config.py hoặc .env)
    if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
        token = create_access_token({"sub": username, "role": "admin"})
        return {
            "access_token": token,
            "token_type": "bearer",
            "role": "admin",
            "username": username
        }
    
    # 2. Kiểm tra tài khoản thành viên thông thường từ Database
    session = models.get_session()
    try:
        user = session.query(User).filter(User.username == username).first()
        # Ở đây giả định so sánh password đơn giản hoặc bạn có thể hash password
        if user and user.password_hash == password:  # Có thể đổi sang hash verify sau
            token = create_access_token({"sub": username, "role": "job_seeker"})
            return {
                "access_token": token,
                "token_type": "bearer",
                "role": "job_seeker",
                "username": username
            }
    finally:
        session.close()
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Tên đăng nhập hoặc mật khẩu không chính xác"
    )

# --- API Admin: Thống Kê Tổng Quan (Stats) ---
@app.get("/api/admin/stats")
def get_admin_stats():
    session = models.get_session()
    try:
        total_jobs = session.query(Job).count()
        geocoded_jobs = session.query(Job).filter((Job.is_geocoded == True) | (Job.latitude.isnot(None))).count()
        pending_review = session.query(Job).filter(Job.status == "pending").count()
        running_tasks = session.query(ScrapeTask).filter(ScrapeTask.status == "running").count()
        total_tasks = session.query(ScrapeTask).count()

        geocoding_rate = round((geocoded_jobs / total_jobs * 100), 1) if total_jobs > 0 else 0.0

        # Lấy lịch trình tự động
        tasks_scheduled = session.query(ScrapeTask).filter(ScrapeTask.is_scheduled == True).all()
        scheduled_list = []
        for t in tasks_scheduled:
            scheduled_list.append({
                "name": t.name,
                "trigger": t.schedule_cron or "Hàng ngày",
                "next_run": (datetime.utcnow() + timedelta(days=1)).isoformat() # Tạm thời mock thời gian lần tới
            })

        return {
            "system": {
                "total_jobs": total_jobs,
                "geocoded_jobs": geocoded_jobs,
                "geocoding_rate": geocoding_rate,
                "pending_review": pending_review,
                "running_tasks": running_tasks,
                "total_tasks": total_tasks
            },
            "scheduled_jobs": scheduled_list
        }
    finally:
        session.close()

# --- API Admin: Bot Config ---
BOT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "bot_config.json")

@app.get("/api/admin/bot-config")
def get_bot_config():
    if not os.path.exists(BOT_CONFIG_PATH):
        return {
            "max_posts_per_group": 5,
            "max_groups_per_session": 3,
            "max_days_old": 3,
            "facebook_groups": []
        }
    with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@app.post("/api/admin/bot-config")
def update_bot_config(config: dict = Body(...)):
    os.makedirs(os.path.dirname(BOT_CONFIG_PATH), exist_ok=True)
    with open(BOT_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return {"message": "Cập nhật cấu hình thành công"}

# --- API Admin: Quản Lý Scraping Tasks ---
class TaskCreate(BaseModel):
    name: str
    source_name: str
    seed_url: str
    max_pages: int = 10
    is_scheduled: bool = False
    schedule_cron: Optional[str] = None

@app.get("/api/admin/tasks")
def list_tasks():
    session = models.get_session()
    try:
        tasks = session.query(ScrapeTask).all()
        return [t.to_dict() for t in tasks]
    finally:
        session.close()

@app.post("/api/admin/tasks")
def create_task(task_in: TaskCreate):
    session = models.get_session()
    try:
        t = ScrapeTask(
            name=task_in.name,
            source_name=task_in.source_name,
            seed_url=task_in.seed_url,
            max_pages=task_in.max_pages,
            is_scheduled=task_in.is_scheduled,
            schedule_cron=task_in.schedule_cron,
            status="idle"
        )
        session.add(t)
        session.commit()
        session.refresh(t)
        return t.to_dict()
    finally:
        session.close()

@app.post("/api/admin/tasks/{task_id}/run")
def run_task(task_id: int):
    session = models.get_session()
    try:
        task = session.query(ScrapeTask).filter(ScrapeTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task không tồn tại")
        
        task.status = "running"
        task.last_run_at = datetime.utcnow()
        session.commit()

        # Khởi động crawler pipeline bất đồng bộ bằng Subprocess
        # Chạy 'python main.py now [source_name]' ở chế độ background
        try:
            args = [sys.executable, "main.py", "now"]
            if task.source_name:
                args.append(task.source_name)
            subprocess.Popen(args, close_fds=True if os.name != 'nt' else False)
            logger.info(f"🚀 Triggered Crawler Pipeline for Task #{task_id} ({task.source_name or 'all'}) in background.")
        except Exception as e:
            logger.error(f"Error launching background crawl subprocess: {e}")

        return {"message": "Task started in background", "task_id": task_id}
    finally:
        session.close()

@app.post("/api/admin/tasks/by-source/{source_name}/run")
def run_task_by_source(source_name: str):
    session = models.get_session()
    try:
        task = session.query(ScrapeTask).filter(ScrapeTask.source_name == source_name).first()
        if not task:
            # Tạo task mặc định nếu chưa tồn tại
            task = ScrapeTask(
                name=f"{source_name.capitalize()} Crawler",
                source_name=source_name,
                seed_url=f"https://www.{source_name}.com" if source_name != "facebook" else "https://www.facebook.com",
                status="idle"
            )
            session.add(task)
            session.commit()
            session.refresh(task)
        
        task.status = "running"
        task.last_run_at = datetime.utcnow()
        session.commit()

        try:
            args = [sys.executable, "main.py", "now"]
            args.append(source_name)
            subprocess.Popen(args, close_fds=True if os.name != 'nt' else False)
            logger.info(f"🚀 Triggered Crawler Pipeline for {source_name} in background.")
        except Exception as e:
            logger.error(f"Error launching background crawl subprocess: {e}")

        return {"message": "Task started in background", "source_name": source_name}
    finally:
        session.close()

# --- API Admin: Cập nhật Lịch Trình Tự Động ---
class ScheduleUpdate(BaseModel):
    is_scheduled: bool
    schedule_cron: str

@app.post("/api/admin/tasks/by-source/{source_name}/schedule")
def update_task_schedule_by_source(source_name: str, data: ScheduleUpdate):
    session = models.get_session()
    try:
        task = session.query(ScrapeTask).filter(ScrapeTask.source_name == source_name).first()
        if not task:
            # Tạo task mặc định nếu chưa tồn tại
            task = ScrapeTask(
                name=f"{source_name.capitalize()} Crawler",
                source_name=source_name,
                seed_url=f"https://www.{source_name}.com" if source_name != "facebook" else "https://www.facebook.com",
                status="idle"
            )
            session.add(task)
            session.commit()
            session.refresh(task)
        
        task.is_scheduled = data.is_scheduled
        task.schedule_cron = data.schedule_cron
        session.commit()
        return {"message": "Cập nhật lịch chạy thành công", "task": task.to_dict()}
    finally:
        session.close()

@app.post("/api/admin/tasks/{task_id}/schedule")
def update_task_schedule(task_id: int, data: ScheduleUpdate):
    session = models.get_session()
    try:
        task = session.query(ScrapeTask).filter(ScrapeTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task không tồn tại")
        
        task.is_scheduled = data.is_scheduled
        task.schedule_cron = data.schedule_cron
        session.commit()
        return {"message": "Cập nhật lịch chạy thành công", "task": task.to_dict()}
    finally:
        session.close()

@app.post("/api/admin/tasks/{task_id}/cancel")
def cancel_task(task_id: int):
    session = models.get_session()
    try:
        task = session.query(ScrapeTask).filter(ScrapeTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task không tồn tại")
        task.status = "idle"
        session.commit()
        return {"message": "Task cancelled", "task_id": task_id}
    finally:
        session.close()

@app.delete("/api/admin/tasks/{task_id}")
def delete_task(task_id: int):
    session = models.get_session()
    try:
        task = session.query(ScrapeTask).filter(ScrapeTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task không tồn tại")
        session.delete(task)
        session.commit()
        return {"message": "Task deleted", "task_id": task_id}
    finally:
        session.close()

# --- API Admin: Kiểm Duyệt Việc Làm (Review / Active Learning) ---
@app.get("/api/admin/jobs/review")
def get_review_jobs(limit: int = 50):
    session = models.get_session()
    try:
        jobs = session.query(Job).filter(Job.status == "pending").order_by(Job.scraped_at.desc()).limit(limit).all()
        return {"jobs": [j.to_dict() for j in jobs]}
    finally:
        session.close()

class ReviewAction(BaseModel):
    action: str  # 'approve' hoặc 'reject'
    # Các trường mở rộng hỗ trợ Chỉnh Sửa để Bot Tự Học
    title: Optional[str] = None
    company: Optional[str] = None
    salary_raw: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    address_clean: Optional[str] = None
    skills: Optional[List[str]] = None

@app.post("/api/admin/jobs/{job_id}/review")
def review_job(job_id: int, data: ReviewAction):
    session = models.get_session()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Việc làm không tồn tại")

        if data.action == "reject":
            job.status = "rejected"
            session.commit()
            return {"message": "Job rejected"}

        # ── ACTIVE LEARNING feedback loop: Chỉnh sửa và lưu lịch sử ──
        # So sánh các giá trị Admin chỉnh sửa với giá trị gốc bot cào về
        corrections = []

        def track_change(field: str, old_val, new_val):
            if new_val is not None and str(old_val).strip() != str(new_val).strip():
                # Lưu log lịch sử chỉnh sửa
                log = JobCorrection(
                    job_id=job.id,
                    field_name=field,
                    old_value=str(old_val) if old_val is not None else "",
                    new_value=str(new_val),
                    corrected_at=datetime.utcnow()
                )
                session.add(log)
                corrections.append(field)
                return True
            return False

        # Thực hiện so sánh & cập nhật các trường được chỉnh sửa từ Admin UI
        if data.title:
            track_change("title", job.title, data.title)
            job.title = data.title
        
        if data.company:
            track_change("company", job.company, data.company)
            job.company = data.company

            # ── BỘ NHỚ THỰC THỂ ĐỘNG (Dynamic Entity Cache) ──
            # Nếu admin sửa tên công ty và bài đăng có Số điện thoại hoặc Địa chỉ sạch:
            # Ghi nhận SĐT/Địa chỉ này thuộc về Công ty chuẩn vừa được cập nhật
            if job.phone:
                # Kiểm tra xem thực thể SĐT này đã lưu chưa
                existing = session.query(VerifiedEntity).filter(
                    VerifiedEntity.entity_type == "phone",
                    VerifiedEntity.entity_value == job.phone
                ).first()
                if not existing:
                    entity = VerifiedEntity(
                        entity_type="phone",
                        entity_value=job.phone,
                        mapped_company=data.company
                    )
                    session.add(entity)
                    logger.info(f"🧠 [Auto-Learning] Saved Phone {job.phone} -> Company '{data.company}'")
            
            if job.address_clean:
                existing_addr = session.query(VerifiedEntity).filter(
                    VerifiedEntity.entity_type == "address",
                    VerifiedEntity.entity_value == job.address_clean
                ).first()
                if not existing_addr:
                    entity = VerifiedEntity(
                        entity_type="address",
                        entity_value=job.address_clean,
                        mapped_company=data.company
                    )
                    session.add(entity)
                    logger.info(f"🧠 [Auto-Learning] Saved Address {job.address_clean} -> Company '{data.company}'")

        if data.salary_raw:
            track_change("salary_raw", job.salary_raw, data.salary_raw)
            job.salary_raw = data.salary_raw
        if data.salary_min is not None:
            track_change("salary_min", job.salary_min, data.salary_min)
            job.salary_min = data.salary_min
        if data.salary_max is not None:
            track_change("salary_max", job.salary_max, data.salary_max)
            job.salary_max = data.salary_max
        if data.address_clean:
            track_change("address_clean", job.address_clean, data.address_clean)
            job.address_clean = data.address_clean
        if data.skills is not None:
            track_change("skills", job.skills, data.skills)
            job.skills = data.skills

        job.status = "approved"
        job.needs_review = False
        session.commit()

        return {
            "message": "Job approved",
            "corrections_made": corrections,
            "learned_entities": len(corrections) > 0
        }
    finally:
        session.close()

# --- API Admin: Phân Tích Xu Hướng Tuyển Dụng (Analytics) ---
@app.get("/api/admin/analytics")
def get_analytics():
    session = models.get_session()
    try:
        jobs = session.query(Job).all()

        # 1. Thống kê Kỹ năng
        skill_counts = {}
        for j in jobs:
            skills = j.skills
            if isinstance(skills, list):
                for s in skills:
                    s_clean = s.lower().strip()
                    skill_counts[s_clean] = skill_counts.get(s_clean, 0) + 1
            elif isinstance(skills, str) and skills.startswith("["):
                try:
                    lst = json.loads(skills)
                    for s in lst:
                        s_clean = s.lower().strip()
                        skill_counts[s_clean] = skill_counts.get(s_clean, 0) + 1
                except:
                    pass

        top_skills = [{"skill": k.upper(), "count": v} for k, v in sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:10]]

        # 2. Phân bố Nguồn cào (Source distribution)
        sources = {}
        for j in jobs:
            src = j.source_name or "unknown"
            sources[src] = sources.get(src, 0) + 1

        # 3. Phân bố Bán kính (Radius distribution - MOCK)
        radius = {
            "0-2 km": int(len(jobs) * 0.35),
            "2-5 km": int(len(jobs) * 0.45),
            "5-10 km": int(len(jobs) * 0.15),
            ">10 km": int(len(jobs) * 0.05)
        }

        # 4. Thống kê Mức Lương
        salary_mins = [j.salary_min for j in jobs if j.salary_min is not None]
        salary_maxs = [j.salary_max for j in jobs if j.salary_max is not None]

        salary_stats = {
            "avg_min": round(sum(salary_mins) / len(salary_mins) * 1000000, 0) if salary_mins else 0,
            "min": round(min(salary_mins) * 1000000, 0) if salary_mins else 0,
            "max": round(max(salary_maxs) * 1000000, 0) if salary_maxs else 0,
            "count": len(salary_mins)
        }

        return {
            "top_skills": top_skills,
            "source_distribution": sources,
            "radius_distribution": radius,
            "salary_stats": salary_stats
        }
    finally:
        session.close()

# --- API Admin & Public: Knowledge Graph ---
@app.get("/api/knowledge-graph")
def get_knowledge_graph():
    session = models.get_session()
    try:
        nodes = session.query(SkillNode).all()
        relations = session.query(SkillRelation).all()

        nodes_list = []
        for n in nodes:
            nodes_list.append({
                "id": n.name.lower(),
                "label": n.name,
                "group": n.category or "unknown"
            })

        # Fallback dữ liệu tĩnh nếu DB trống để UI Knowledge Graph luôn sinh động
        if not nodes_list:
            nodes_list = [
                {"id": "python", "label": "Python", "group": "programming"},
                {"id": "fastapi", "label": "FastAPI", "group": "web_backend"},
                {"id": "react", "label": "React", "group": "web_frontend"},
                {"id": "postgresql", "label": "PostgreSQL", "group": "database"},
                {"id": "docker", "label": "Docker", "group": "devops"},
                {"id": "machine learning", "label": "Machine Learning", "group": "data_science"},
            ]

        edges_list = []
        for r in relations:
            edges_list.append({
                "from": r.skill_from.lower(),
                "to": r.skill_to.lower(),
                "weight": r.weight or 1.0,
                "relation": r.relation_type or "related"
            })

        if not edges_list:
            edges_list = [
                {"from": "python", "to": "fastapi", "weight": 2.0, "relation": "requires"},
                {"from": "fastapi", "to": "react", "weight": 1.0, "relation": "related"},
                {"from": "fastapi", "to": "postgresql", "weight": 1.5, "relation": "requires"},
                {"from": "python", "to": "machine learning", "weight": 2.5, "relation": "related"},
                {"from": "postgresql", "to": "docker", "weight": 1.0, "relation": "related"}
            ]

        return {
            "nodes": nodes_list,
            "edges": edges_list
        }
    finally:
        session.close()

@app.get("/api/skills/{skill}/related")
def get_related_skills(skill: str, max_hops: int = 2):
    session = models.get_session()
    try:
        relations = session.query(SkillRelation).filter(
            (SkillRelation.skill_from.like(f"%{skill}%")) | (SkillRelation.skill_to.like(f"%{skill}%"))
        ).limit(20).all()

        results = []
        for r in relations:
            target = r.skill_to if r.skill_from.lower() == skill.lower() else r.skill_from
            results.append({
                "skill": target,
                "relation": r.relation_type or "related",
                "weight": r.weight
            })

        if not results:
            # Dữ liệu mẫu fallback
            results = [
                {"skill": "FastAPI", "relation": "requires", "weight": 2.0},
                {"skill": "Django", "relation": "related", "weight": 1.5},
                {"skill": "Pandas", "relation": "related", "weight": 2.5}
            ]
        return {"related": results}
    finally:
        session.close()

# --- API Public: Tìm kiếm Việc Làm & Bản Đồ (Map & Search) ---
@app.get("/api/jobs/map/data")
def get_map_jobs(radius_km: float = 10.0, user_lat: Optional[float] = None, user_lng: Optional[float] = None, source: Optional[str] = None):
    session = models.get_session()
    try:
        query = session.query(Job).filter(Job.status == "approved")
        if source:
            query = query.filter(Job.source_name == source)

        jobs = query.all()
        markers = []

        for j in jobs:
            # Tạo tọa độ Đà Nẵng fallback ngẫu nhiên nhỏ nếu thiếu tọa độ
            lat = j.latitude if j.latitude is not None else 16.0544
            lng = j.longitude if j.longitude is not None else 108.2022

            # Tính khoảng cách đơn giản (Haversine approximation)
            distance = 0.0
            if user_lat is not None and user_lng is not None:
                # Math approx: 1 degree lat = 111km, 1 degree lng = 111 * cos(lat)
                dx = (lng - user_lng) * 111.0 * 0.96 # Cos Đà Nẵngapprox
                dy = (lat - user_lat) * 111.0
                distance = round((dx**2 + dy**2)**0.5, 2)
                if distance > radius_km:
                    continue

            markers.append({
                "id": j.id,
                "title": j.title,
                "company": j.company or "N/A",
                "address": j.address_clean or j.address_raw or "Đà Nẵng",
                "salary": j.salary_raw or "Thỏa thuận",
                "lat": lat,
                "lng": lng,
                "url": j.source_url,
                "source": j.source_name,
                "skills": j.skills or [],
                "distance_km": distance if user_lat is not None else None
            })

        return {"markers": markers}
    finally:
        session.close()

class JobSearchQuery(BaseModel):
    query: Optional[str] = None
    skills: Optional[List[str]] = None
    user_lat: Optional[float] = None
    user_lng: Optional[float] = None
    radius_km: Optional[float] = 10.0
    salary_min: Optional[float] = None
    semantic: bool = False
    limit: int = 20
    offset: int = 0

@app.post("/api/jobs/search")
def search_jobs(q: JobSearchQuery):
    session = models.get_session()
    try:
        query = session.query(Job).filter(Job.status == "approved")

        if q.query:
            query = query.filter((Job.title.like(f"%{q.query}%")) | (Job.description.like(f"%{q.query}%")))
        
        if q.salary_min:
            query = query.filter((Job.salary_min >= q.salary_min / 1000000.0) | (Job.salary_min.is_(None)))

        jobs = query.all()
        results = []

        for j in jobs:
            lat = j.latitude if j.latitude is not None else 16.0544
            lng = j.longitude if j.longitude is not None else 108.2022

            distance = None
            if q.user_lat is not None and q.user_lng is not None:
                dx = (lng - q.user_lng) * 111.0 * 0.96
                dy = (lat - q.user_lat) * 111.0
                distance = round((dx**2 + dy**2)**0.5, 2)
                if q.radius_km and distance > q.radius_km:
                    continue

            results.append({
                "id": j.id,
                "title": j.title,
                "company": j.company or "N/A",
                "address_clean": j.address_clean,
                "address_raw": j.address_raw,
                "salary_raw": j.salary_raw,
                "source_name": j.source_name,
                "source_url": j.source_url,
                "skills": j.skills or [],
                "distance_km": distance
            })

        # Sắp xếp theo khoảng cách nếu có vị trí
        if q.user_lat is not None:
            results.sort(key=lambda x: x["distance_km"] or 9999)

        total = len(results)
        paginated_results = results[q.offset : q.offset + q.limit]

        return {
            "total": total,
            "results": paginated_results
        }
    finally:
        session.close()

@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: int):
    session = models.get_session()
    try:
        j = session.query(Job).filter(Job.id == job_id).first()
        if not j:
            raise HTTPException(status_code=404, detail="Job không tồn tại")
        
        res = j.to_dict()
        res["description"] = j.description
        res["requirements"] = j.requirements
        res["address_raw"] = j.address_raw
        
        # Gợi ý kỹ năng liên quan
        related = []
        if j.skills:
            for s in j.skills:
                # Quét SkillRelation tìm các kỹ năng liên đới
                relations = session.query(SkillRelation).filter(
                    (SkillRelation.skill_from == s) | (SkillRelation.skill_to == s)
                ).limit(3).all()
                for r in relations:
                    target = r.skill_to if r.skill_from.lower() == s.lower() else r.skill_from
                    if target not in related and target.lower() != s.lower():
                        related.append(target)
        res["related_skills"] = related[:5]
        return res
    finally:
        session.close()

# --- API: Ghi nhận Tương tác Người Dùng (Interactions) ---
class InteractionIn(BaseModel):
    job_id: int
    action: str

@app.post("/api/interactions")
def log_interaction(inter: InteractionIn):
    session = models.get_session()
    try:
        log = UserInteraction(
            job_id=inter.job_id,
            action=inter.action,
            created_at=datetime.utcnow()
        )
        session.add(log)
        session.commit()
        return {"status": "success"}
    finally:
        session.close()

# --- WebSocket: Giám Sát Agent Real-time (/ws/monitor) ---
@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Gửi thông tin trạng thái ban đầu
        session = models.get_session()
        try:
            total = session.query(Job).count()
            geocoded = session.query(Job).filter((Job.is_geocoded == True) | (Job.latitude.isnot(None))).count()
            rate = int(geocoded / total * 100) if total > 0 else 0
            
            await websocket.send_json({
                "type": "stats_update",
                "data": {
                    "active_threads": session.query(ScrapeTask).filter(ScrapeTask.status == "running").count(),
                    "geocoding_rate": rate,
                    "total_errors": 0,
                    "scrape_speed": 45, # Mock speed
                    "total_jobs": total,
                    "geocoded_jobs": geocoded,
                    "last_run_at": datetime.utcnow().isoformat()
                }
            })
        finally:
            session.close()

        while True:
            # Nhận thông điệp từ client (nếu có) để giữ kết nối sống
            data = await websocket.receive_text()
            # Trả lời lại dạng heartbeat
            await websocket.send_json({"type": "heartbeat", "time": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# --- Điều Hướng Giao Diện (Redirects) ---
@app.get("/")
def redirect_to_public():
    return RedirectResponse(url="/static/index.html")

@app.get("/admin")
def redirect_to_admin():
    return RedirectResponse(url="/static/admin.html")

# --- Phục vụ Website Tĩnh (Static Files) ---
# Thư mục /static sẽ ánh xạ trực tiếp đến các file static/index.html, static/admin.html,...
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Khởi Chạy Server ---
if __name__ == "__main__":
    import uvicorn
    # Đọc cấu hình từ config.py
    logger.info(f"🚀 Starting JobAgent FastAPI Web Server at http://{config.APP_HOST}:{config.APP_PORT}")
    logger.info(f"🔐 Admin Username: {config.ADMIN_USERNAME}")
    uvicorn.run("server:app", host=config.APP_HOST, port=config.APP_PORT, reload=config.DEBUG)
