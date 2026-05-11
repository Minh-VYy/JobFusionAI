-- =============================================
-- AI JOB RECOMMENDATION SYSTEM
-- RESET DATABASE + CREATE ALL TABLES
-- SQL SERVER VERSION
-- Cập nhật: bổ sung các cột cần thiết cho crawler
--           và bảng facebook_groups
-- =============================================

USE master;
GO

-- =============================================
-- XÓA DATABASE NẾU ĐÃ TỒN TẠI
-- =============================================

IF EXISTS (SELECT name FROM sys.databases WHERE name = 'job_agent_db')
BEGIN
    ALTER DATABASE job_agent_db SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE job_agent_db;
    PRINT 'Database cũ đã được xóa.';
END
GO

-- =============================================
-- TẠO DATABASE MỚI
-- =============================================

CREATE DATABASE job_agent_db
COLLATE Vietnamese_CI_AS;
GO

USE job_agent_db;
GO

PRINT 'Database mới đã được tạo.';
GO

-- =============================================
-- USERS
-- =============================================

CREATE TABLE users (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    username                NVARCHAR(100) NOT NULL UNIQUE,
    email                   NVARCHAR(200) NOT NULL UNIQUE,
    password_hash           NVARCHAR(300) NOT NULL,

    full_name               NVARCHAR(200) NULL,
    phone                   NVARCHAR(30)  NULL,

    role                    NVARCHAR(20) NOT NULL DEFAULT 'job_seeker',

    latitude                FLOAT NULL,
    longitude               FLOAT NULL,
    address                 NVARCHAR(500) NULL,

    is_ready_to_work        BIT DEFAULT 0,
    location_updated_at     DATETIME NULL,

    preferred_radius_km     FLOAT DEFAULT 5.0,
    preferred_salary_min    DECIMAL(18,2) NULL,

    preferred_skills        NVARCHAR(MAX) NULL,

    cv_text                 NVARCHAR(MAX) NULL,
    cv_embedding            NVARCHAR(MAX) NULL,   -- JSON float array

    avatar_url              NVARCHAR(1000) NULL,

    is_active               BIT DEFAULT 1,

    created_at              DATETIME DEFAULT GETUTCDATE(),
    updated_at              DATETIME DEFAULT GETUTCDATE(),
    last_login              DATETIME NULL,

    CONSTRAINT CHK_user_role
        CHECK (role IN ('job_seeker','employer','admin'))
);
GO

-- =============================================
-- EMPLOYER PROFILES
-- =============================================

CREATE TABLE employer_profiles (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    user_id                 INT NOT NULL UNIQUE,

    company_name            NVARCHAR(300) NOT NULL,
    tax_code                NVARCHAR(100) NULL,

    company_description     NVARCHAR(MAX) NULL,
    company_address         NVARCHAR(500) NULL,

    website                 NVARCHAR(300) NULL,

    verified                BIT DEFAULT 0,

    created_at              DATETIME DEFAULT GETUTCDATE(),

    CONSTRAINT FK_employer_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);
GO

-- =============================================
-- JOBS
-- Bao gồm đầy đủ:
--   - Các cột gốc (title, salary, address...)
--   - Cột bổ sung cho crawler (normalized_*, phone, fingerprint...)
--   - Cột cho Cross-Source Detection (cross_dup_*)
-- =============================================

CREATE TABLE jobs (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    -- ── Thông tin cơ bản ───────────────────────────────────────────
    title                   NVARCHAR(500) NOT NULL,
    company                 NVARCHAR(300) NULL,

    description             NVARCHAR(MAX) NULL,
    requirements            NVARCHAR(MAX) NULL,

    -- ── Lương ─────────────────────────────────────────────────────
    salary_min              DECIMAL(18,2) NULL,    -- đơn vị: triệu VND
    salary_max              DECIMAL(18,2) NULL,
    salary_raw              NVARCHAR(200) NULL,    -- chuỗi gốc: "5TR5-7TR"

    -- ── Địa chỉ ───────────────────────────────────────────────────
    address_raw             NVARCHAR(500) NULL,
    address_clean           NVARCHAR(500) NULL,

    latitude                FLOAT NULL,
    longitude               FLOAT NULL,
    geocoding_confidence    FLOAT DEFAULT 0,

    -- ── Nguồn dữ liệu ─────────────────────────────────────────────
    source_url              NVARCHAR(1000) NULL,
    source_name             NVARCHAR(100)  NULL,   -- 'facebook','topcv','itviec'...
    source_type             NVARCHAR(50)   NULL,   -- 'group_post','listing'...
    external_id             NVARCHAR(200)  NULL,   -- ID gốc từ nguồn

    created_by              INT NULL,

    -- ── Phân loại ─────────────────────────────────────────────────
    job_type                NVARCHAR(100) NULL,    -- 'full-time','part-time'...
    experience_year         NVARCHAR(100) NULL,
    education               NVARCHAR(200) NULL,

    skills                  NVARCHAR(MAX) NULL,
    industry                NVARCHAR(200) NULL,

    -- ── Trạng thái ────────────────────────────────────────────────
    status                  NVARCHAR(20) DEFAULT 'pending',

    is_geocoded             BIT DEFAULT 0,
    needs_review            BIT DEFAULT 0,
    review_notes            NVARCHAR(MAX) NULL,

    -- ── AI/Embedding ──────────────────────────────────────────────
    embedding               NVARCHAR(MAX) NULL,    -- JSON float array

    -- ── Thời gian ─────────────────────────────────────────────────
    posted_date             DATETIME NULL,
    deadline                DATETIME NULL,

    scraped_at              DATETIME DEFAULT GETUTCDATE(),
    created_at              DATETIME DEFAULT GETUTCDATE(),
    updated_at              DATETIME DEFAULT GETUTCDATE(),

    -- ── Normalized fields (dùng cho Cross-Source Detection) ───────
    normalized_title        NVARCHAR(500) NULL,    -- title đã clean/lowercase
    normalized_location     NVARCHAR(300) NULL,    -- tên tỉnh/thành chuẩn hóa

    -- ── Liên hệ ───────────────────────────────────────────────────
    phone                   NVARCHAR(50)  NULL,    -- số điện thoại trích xuất

    -- ── Deduplication ─────────────────────────────────────────────
    fingerprint_hash        NVARCHAR(64)  NULL,    -- SHA-256 của nội dung chuẩn hóa

    -- ── Cross-Source Duplicate Detection ──────────────────────────
    cross_dup_score         FLOAT         NULL,    -- điểm tương đồng (0.0-1.0)
    cross_dup_of            NVARCHAR(200) NULL,    -- external_id của job gốc

    CONSTRAINT FK_jobs_user
        FOREIGN KEY (created_by) REFERENCES users(id)
        ON DELETE SET NULL,

    CONSTRAINT CHK_job_status
        CHECK (status IN ('pending','approved','rejected','expired'))
);
GO

-- =============================================
-- FACEBOOK GROUPS
-- Lưu thông tin & trust score các group Facebook
-- Dùng bởi facebook_db.py / FacebookCrawler
-- =============================================

CREATE TABLE facebook_groups (
    id                  INT IDENTITY(1,1) PRIMARY KEY,

    group_id            NVARCHAR(100)  NOT NULL UNIQUE,  -- URL hoặc group ID
    group_name          NVARCHAR(300)  NULL,
    group_url           NVARCHAR(500)  NULL,

    -- Trust scoring (tự động cập nhật sau mỗi phiên crawl)
    trust_score         FLOAT          DEFAULT 0.5,
    spam_ratio          FLOAT          DEFAULT 0.0,
    duplicate_ratio     FLOAT          DEFAULT 0.0,
    crawl_priority      NVARCHAR(20)   DEFAULT 'normal',  -- 'high','normal','low'

    -- Thống kê
    total_crawled       INT            DEFAULT 0,
    total_spam          INT            DEFAULT 0,
    total_duplicate     INT            DEFAULT 0,

    last_crawled        DATETIME       NULL,
    is_active           BIT            DEFAULT 1,

    created_at          DATETIME       DEFAULT GETUTCDATE()
);
GO

-- =============================================
-- JOB APPLICATIONS
-- =============================================

CREATE TABLE job_applications (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    user_id                 INT NOT NULL,
    job_id                  INT NOT NULL,

    cv_url                  NVARCHAR(1000) NULL,
    cover_letter            NVARCHAR(MAX)  NULL,

    status                  NVARCHAR(20) DEFAULT 'pending',

    applied_at              DATETIME DEFAULT GETUTCDATE(),
    updated_at              DATETIME DEFAULT GETUTCDATE(),

    CONSTRAINT FK_application_user
        FOREIGN KEY (user_id) REFERENCES users(id),

    CONSTRAINT FK_application_job
        FOREIGN KEY (job_id) REFERENCES jobs(id)
        ON DELETE CASCADE,

    CONSTRAINT CHK_application_status
        CHECK (status IN ('pending','reviewing','accepted','rejected'))
);
GO

-- =============================================
-- SAVED JOBS
-- =============================================

CREATE TABLE saved_jobs (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    user_id                 INT NOT NULL,
    job_id                  INT NOT NULL,

    created_at              DATETIME DEFAULT GETUTCDATE(),

    CONSTRAINT FK_saved_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT FK_saved_job
        FOREIGN KEY (job_id) REFERENCES jobs(id)
        ON DELETE CASCADE
);
GO

-- =============================================
-- NOTIFICATIONS
-- =============================================

CREATE TABLE notifications (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    user_id                 INT NOT NULL,

    title                   NVARCHAR(300) NOT NULL,
    message                 NVARCHAR(MAX) NULL,

    type                    NVARCHAR(100) NULL,   -- 'job_match','application_update'...
    is_read                 BIT DEFAULT 0,

    created_at              DATETIME DEFAULT GETUTCDATE(),

    CONSTRAINT FK_notification_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);
GO

-- =============================================
-- USER INTERACTIONS
-- Dùng cho AI recommendation (click, view, rate)
-- =============================================

CREATE TABLE user_interactions (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    user_id                 INT NULL,
    job_id                  INT NOT NULL,

    action                  NVARCHAR(50)  NULL,   -- 'view','click','apply','save'
    rating                  INT           NULL,   -- 1-5

    search_query            NVARCHAR(500) NULL,

    user_lat                FLOAT NULL,
    user_lng                FLOAT NULL,

    session_id              NVARCHAR(100) NULL,

    created_at              DATETIME DEFAULT GETUTCDATE(),

    CONSTRAINT FK_interaction_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE SET NULL,

    CONSTRAINT FK_interaction_job
        FOREIGN KEY (job_id) REFERENCES jobs(id)
        ON DELETE CASCADE,

    CONSTRAINT CHK_rating
        CHECK (rating IS NULL OR (rating >= 1 AND rating <= 5))
);
GO

-- =============================================
-- SCRAPE TASKS
-- Lịch chạy và trạng thái các tác vụ crawl
-- =============================================

CREATE TABLE scrape_tasks (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    name                    NVARCHAR(200) NOT NULL,

    source_name             NVARCHAR(100) NULL,   -- 'facebook','topcv','itviec'
    seed_url                NVARCHAR(1000) NOT NULL,

    max_pages               INT DEFAULT 10,
    max_depth               INT DEFAULT 3,

    status                  NVARCHAR(20) DEFAULT 'idle',

    schedule_cron           NVARCHAR(100) NULL,
    is_scheduled            BIT DEFAULT 0,

    total_found             INT DEFAULT 0,
    total_scraped           INT DEFAULT 0,
    total_errors            INT DEFAULT 0,

    last_run_at             DATETIME NULL,
    next_run_at             DATETIME NULL,

    error_log               NVARCHAR(MAX) NULL,

    created_at              DATETIME DEFAULT GETUTCDATE(),
    updated_at              DATETIME DEFAULT GETUTCDATE(),

    CONSTRAINT CHK_task_status
        CHECK (status IN ('idle','running','completed','failed','paused'))
);
GO

-- =============================================
-- SKILL NODES
-- =============================================

CREATE TABLE skill_nodes (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    name                    NVARCHAR(200) NOT NULL UNIQUE,

    category                NVARCHAR(100) NULL,   -- 'tech','soft','language'...
    aliases                 NVARCHAR(MAX) NULL,   -- JSON array

    weight                  FLOAT DEFAULT 1.0
);
GO

-- =============================================
-- SKILL RELATIONS
-- =============================================

CREATE TABLE skill_relations (
    id                      INT IDENTITY(1,1) PRIMARY KEY,

    skill_from              NVARCHAR(200) NOT NULL,
    skill_to                NVARCHAR(200) NOT NULL,

    relation_type           NVARCHAR(100) NULL,   -- 'requires','related','parent'
    weight                  FLOAT DEFAULT 1.0,

    CONSTRAINT UQ_skill_relation
        UNIQUE (skill_from, skill_to)
);
GO

-- =============================================
-- UNIQUE INDEX — CHỐNG TRÙNG JOBS
-- =============================================

CREATE UNIQUE INDEX UQ_jobs_source_external
ON jobs(source_name, external_id)
WHERE external_id IS NOT NULL;
GO

-- =============================================
-- INDEX CHO JOBS
-- =============================================

CREATE INDEX IX_jobs_status          ON jobs(status);
CREATE INDEX IX_jobs_location        ON jobs(latitude, longitude);
CREATE INDEX IX_jobs_source          ON jobs(source_name);
CREATE INDEX IX_jobs_created_by      ON jobs(created_by);
CREATE INDEX IX_jobs_fingerprint     ON jobs(fingerprint_hash);          -- dedup lookup
CREATE INDEX IX_jobs_norm_location   ON jobs(normalized_location);       -- cross-source
CREATE INDEX IX_jobs_phone           ON jobs(phone) WHERE phone IS NOT NULL; -- phone dedup
GO

-- =============================================
-- INDEX CHO CÁC BẢNG KHÁC
-- =============================================

CREATE INDEX IX_interactions_job     ON user_interactions(job_id);
CREATE INDEX IX_notifications_user   ON notifications(user_id);
CREATE INDEX IX_applications_user    ON job_applications(user_id);
CREATE INDEX IX_applications_job     ON job_applications(job_id);
CREATE INDEX IX_scrape_tasks_status  ON scrape_tasks(status);
CREATE INDEX IX_fb_groups_priority   ON facebook_groups(crawl_priority, trust_score DESC);
GO

-- =============================================
-- PRINT SUMMARY
-- =============================================

PRINT '============================================';
PRINT ' AI Job Recommendation DB — Created!';
PRINT ' Tables:';
PRINT '   users, employer_profiles';
PRINT '   jobs (+ normalized + dedup + cross-source)';
PRINT '   facebook_groups (trust scoring)';
PRINT '   job_applications, saved_jobs';
PRINT '   notifications, user_interactions';
PRINT '   scrape_tasks';
PRINT '   skill_nodes, skill_relations';
PRINT '============================================';
GO
