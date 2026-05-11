# cleaner/skill_extractor.py
import re
import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)

# ================================================================
# SKILL DICTIONARY — canonical name: [aliases]
# ================================================================
SKILL_DICTIONARY = {
    # === PROGRAMMING LANGUAGES ===
    "Python": ["python", "py"],
    "JavaScript": ["javascript", "js", "java script"],
    "TypeScript": ["typescript", "ts"],
    "Java": ["java", "core java"],
    "C#": ["c#", "csharp", "c sharp"],
    "C++": ["c++", "cpp", "c plus plus"],
    "PHP": ["php"],
    "Ruby": ["ruby", "ruby on rails", "ror"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "Golang": ["golang", "go lang"],
    "Rust": ["rust lang", "rust programming"],
    "Scala": ["scala"],
    "Dart": ["dart"],

    # === FRONTEND ===
    "React": ["reactjs", "react.js", "react js"],
    "Vue": ["vuejs", "vue.js", "vue js"],
    "Angular": ["angular", "angularjs"],
    "Next.js": ["next.js", "nextjs"],
    "HTML": ["html5", "html/css"],
    "CSS": ["css3"],
    "Tailwind CSS": ["tailwind", "tailwindcss"],
    "Bootstrap": ["bootstrap"],
    "jQuery": ["jquery"],
    "Redux": ["redux"],

    # === BACKEND ===
    "Node.js": ["node.js", "nodejs", "node js"],
    "Django": ["django"],
    "FastAPI": ["fastapi", "fast api"],
    "Flask": ["flask"],
    "Spring Boot": ["spring boot", "springboot", "spring framework"],
    "Laravel": ["laravel"],
    "Express.js": ["expressjs", "express.js"],
    "NestJS": ["nestjs", "nest.js"],
    "ASP.NET": ["asp.net", "dotnet core", ".net core"],
    ".NET": [".net framework"],

    # === MOBILE ===
    "React Native": ["react native"],
    "Flutter": ["flutter"],
    "Android": ["android sdk", "android development"],
    "iOS": ["ios development", "ios sdk"],

    # === DATABASE ===
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "mongo db"],
    "SQL Server": ["sql server", "mssql", "ms sql"],
    "Oracle DB": ["oracle database", "oracle db"],
    "Redis": ["redis cache"],
    "Elasticsearch": ["elastic search", "elk stack"],
    "SQL": ["t-sql", "pl/sql", "sql query"],

    # === CLOUD / DEVOPS ===
    "AWS": ["amazon web services", "amazon aws"],
    "Azure": ["microsoft azure", "azure cloud"],
    "GCP": ["google cloud", "google cloud platform"],
    "Docker": ["docker container"],
    "Kubernetes": ["k8s", "kubernetes"],
    "Jenkins": ["jenkins ci"],
    "Git": ["github", "gitlab", "bitbucket", "git version"],
    "CI/CD": ["ci cd", "cicd", "continuous integration"],
    "Linux": ["ubuntu", "centos", "linux server"],
    "Terraform": ["terraform"],
    "Nginx": ["nginx"],

    # === AI / ML ===
    "Machine Learning": ["machine learning", "ml model"],
    "Deep Learning": ["deep learning"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "Scikit-learn": ["scikit-learn", "sklearn"],
    "NLP": ["natural language processing", "text mining"],
    "Computer Vision": ["computer vision", "image processing"],
    "LLM": ["large language model", "llm"],
    "RAG": ["retrieval augmented", "rag pipeline"],
    "LangChain": ["langchain"],
    "OpenAI": ["openai api", "chatgpt api", "gpt api"],

    # === TESTING ===
    "Selenium": ["selenium webdriver"],
    "Postman": ["postman api"],
    "Jest": ["jest testing"],
    "PyTest": ["pytest"],
    "JMeter": ["jmeter"],
    "Appium": ["appium"],

    # === DATA ===
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Apache Spark": ["pyspark", "apache spark"],
    "Kafka": ["apache kafka"],
    "Tableau": ["tableau"],
    "Power BI": ["powerbi", "power bi"],
    "Airflow": ["apache airflow"],

    # === ARCHITECTURE ===
    "Microservices": ["micro services", "microservice"],
    "RESTful API": ["rest api", "restful", "restapi"],
    "GraphQL": ["graphql"],
    "OOP": ["object oriented", "oop", "oops"],
    "Design Patterns": ["design pattern", "gang of four"],
    "System Design": ["system design", "hld", "lld"],
    "Agile": ["scrum", "kanban", "agile methodology"],
    # Chức danh → infer skills
    "Manual Testing": [
        "manual tester", "kiểm thử phần mềm",
        "software tester", "tester", "qa tester",
        "quality control", "manual qc"
    ],
    "Automation Testing": [
        "automation tester", "automation testing",
        "kiểm thử tự động", "test automation"
    ],
    "Penetration Testing": [
        "penetration tester", "pentest",
        "security tester", "ethical hacker"
    ],
    "Embedded Systems": [
        "lập trình nhúng", "embedded", "embedded systems",
        "embedded engineer", "firmware"
    ],
    "Frontend Development": [
        "lập trình frontend", "front-end developer",
        "frontend engineer", "front end"
    ],
    "Backend Development": [
        "lập trình backend", "back-end developer",
        "backend engineer", "back end"
    ],
    "Fullstack Development": [
        "lập trình fullstack", "full-stack developer",
        "fullstack engineer", "full stack"
    ],
    "Mobile Development": [
        "lập trình di động", "mobile developer",
        "mobile engineer", "lập trình mobile",
        "lập trình ứng dụng di động"
    ],
    "Data Analysis": [
        "phân tích dữ liệu", "data analyst",
        "data analysis", "business intelligence"
    ],
    "Business Analysis": [
        "phân tích nghiệp vụ", "business analyst", "ba"
    ],
    "Project Management": [
        "quản lý dự án", "project manager", "pm",
        "it project manager", "scrum master"
    ],
    "UI/UX Design": [
        "ui/ux", "uiux", "ui ux", "ux designer",
        "ui designer", "thiết kế giao diện"
    ],
    "DevOps": ["devops engineer", "devops"],
    "Data Science": [
        "data scientist", "data science",
        "khoa học dữ liệu"
    ],
    "Network Engineering": [
        "kỹ sư mạng", "network engineer",
        "system admin", "sysadmin"
    ],
    "IT Consulting": [
        "tư vấn it", "it consultant",
        "giải pháp cntt"
    ],
    "Frontend Development": [
    "lập trình frontend", "front-end developer",
    "frontend engineer", "front end",
    "frontend developer",          # ← thêm
    "frontend dev",                # ← thêm
    ],

    "Backend Development": [
        "lập trình backend", "back-end developer",
        "backend engineer", "back end",
        "backend developer",           # ← thêm
        "backend dev",                 # ← thêm
        "backend developer hà nội",    # ← thêm
    ],

    "Software Testing": [             # ← thêm mới
        "software testing", "software tester",
        "testing internship", "software testing internship",
        "qa engineer", "qc engineer",
        "it operations", "it operations officer",
    ],

    "Product Management": [           # ← thêm mới
        "product owner", "product manager",
        "po ", " po,",
    ],

    "IT Consulting": [
        "tư vấn it", "it consultant",
        "giải pháp cntt",
        "tư vấn giải pháp công nghệ",  # ← thêm
        "nhân viên tư vấn giải pháp",  # ← thêm
    ],

    "Internship": [                   # ← thêm mới
        "internship engineer",
        "thực tập sinh",
        "intern engineer",
    ],
    "Team Leadership": [              # ← thêm mới
    "team leader", "tech lead", "trưởng nhóm kỹ thuật",
    "trưởng nhóm it", "it lead", "technical lead",
    ],

    "IT Support": [                   # ← thêm mới
        "it helpdesk", "helpdesk", "it support",
        "support engineer", "nhân viên it",
        "it generalist", "it officer",
        "chuyên viên công nghệ thông tin",
    ],

    "Fullstack Development": [
        "lập trình fullstack", "full-stack developer",
        "fullstack engineer", "full stack",
        "fullstack software engineer",    # ← thêm
        "fullstack developer",            # ← thêm
    ],

    "Automation Engineering": [       # ← thêm mới
        "automation engineer", "lập trình tự động",
        "electrical automation", "thiết kế điện lập trình",
    ],

    "Cybersecurity": [                # ← thêm mới
        "an ninh mạng", "cybersecurity", "security engineer",
        "information security", "bảo mật", "an toàn thông tin",
    ],
}
BLACKLIST = {
    # Địa điểm
    "hcm", "hà nội", "hanoi", "hồ chí minh", "ho chi minh",
    "đà nẵng", "da nang", "remote", "toàn quốc",

    # Acronym chung
    "it", "b2b", "b2c", "hr", "vn", "co", "ltd",
    "upto", "ok", "id", "ai", "nan",

    # ✅ THÊM MỚI: Tags ngành TopCV
    "it - phần mềm", "phần mềm", "game", "fintech",
    "giáo dục / đào tạo", "giáo viên bộ môn khác",
    "giáo dục", "y tế", "thương mại điện tử",
    "logistics", "bất động sản", "ngân hàng",
    "marketing", "kế toán", "nhân sự", "hành chính",

    # ✅ THÊM MỚI: Tags vị trí chung (không phải skill)
    "backend developer", "frontend developer",
    "fullstack developer", "mobile developer",
    "software engineer", "it project manager",
    "it consultant", "business analyst (phân tích nghiệp vụ)",
    "software tester (automation & manual)",
    "embedded engineer/lập trình nhúng",
    "chuyên môn công nghệ thông tin khác",

    # Phúc lợi
    "nghỉ thứ 7", "nghỉ phép", "bảo hiểm",
    "du lịch", "team building",

    # Kinh nghiệm
    "fresher", "intern", "senior", "junior",
    "middle", "lead", "manager", "director",

    # Ngôn ngữ không phải skill code
    "english", "tiếng anh", "tiếng nhật",
    "communication", "teamwork",
}
# Build alias map: lowercase alias → canonical
ALIAS_MAP: dict[str, str] = {}
for canonical, aliases in SKILL_DICTIONARY.items():
    # Alias chính = lowercase của canonical
    ALIAS_MAP[canonical.lower()] = canonical
    for alias in aliases:
        ALIAS_MAP[alias.lower()] = canonical

# ================================================================
# BLACKLIST — Không phải skill kỹ thuật
# ================================================================
BLACKLIST = {
    # Địa điểm
    "hcm", "hà nội", "hanoi", "hồ chí minh", "ho chi minh",
    "đà nẵng", "da nang", "remote", "toàn quốc",

    # Acronym chung / mô hình KD
    "it", "b2b", "b2c", "hr", "vn", "co", "ltd",
    "upto", "ok", "id",

    # Phúc lợi / chế độ
    "nghỉ thứ 7", "nghỉ phép", "bảo hiểm", "thưởng",
    "du lịch", "team building", "13th", "14th",

    # Ngành nghề rộng
    "phần mềm", "tài chính", "ngân hàng", "bảo hiểm",
    "giáo dục", "y tế", "thương mại", "logistics",

    # Kinh nghiệm / học vấn
    "fresher", "intern", "senior", "junior", "middle",
    "lead", "manager", "director",

    # Tiếng Việt phổ biến không phải skill
    "english", "tiếng anh", "tiếng nhật", "japanese",
    "communication", "teamwork", "problem solving",
}


class SkillExtractor:
    """
    Trích xuất và chuẩn hóa skills từ job text.
    Kết hợp Keyword Matching + Pattern-based extraction.
    """

    def __init__(self):
        # Sort aliases dài trước để tránh match nhầm
        self.sorted_aliases = sorted(
            ALIAS_MAP.keys(), key=len, reverse=True
        )

    # ============================================================
    # ENTRY POINT
    # ============================================================

    def extract(self, title="", description="", requirements="") -> list:
        full_text = " ".join([
            str(title), str(description), str(requirements)
        ])

        matched = self._keyword_matching(full_text)
        patterns = self._pattern_extraction(full_text)

        # Gộp, dedup, filter
        all_skills = self._finalize(matched + patterns)
        return all_skills

    # ============================================================
    # BƯỚC 1: KEYWORD MATCHING
    # ============================================================

    def _keyword_matching(self, text: str) -> list:
        text_lower = text.lower()
        found = []
        matched_spans = []

        for alias in self.sorted_aliases:
            escaped = re.escape(alias)
            # Word boundary cho cả tiếng Anh lẫn ký tự đặc biệt
            pattern = r'(?<![a-zA-Z0-9\+\#])' + escaped + r'(?![a-zA-Z0-9\+\#])'

            for m in re.finditer(pattern, text_lower):
                s, e = m.start(), m.end()
                # Không overlap với match trước
                if not any(s < pe and e > ps for ps, pe in matched_spans):
                    canonical = ALIAS_MAP[alias]
                    if canonical not in found:
                        found.append(canonical)
                    matched_spans.append((s, e))

        return found

    # ============================================================
    # BƯỚC 2: PATTERN EXTRACTION
    # ============================================================

    def _pattern_extraction(self, text: str) -> list:
        found = []

        # Pattern: sau từ khóa kỹ năng tiếng Việt/Anh
        triggers = [
            r"thành thạo\s+([A-Za-z][A-Za-z0-9\.\+\#\s]{1,30}?)(?=[,;\n]|$)",
            r"am hiểu\s+([A-Za-z][A-Za-z0-9\.\+\#\s]{1,30}?)(?=[,;\n]|$)",
            r"kinh nghiệm (?:với|về)?\s*([A-Za-z][A-Za-z0-9\.\+\#]{1,20})",
            r"proficient in\s+([A-Za-z][A-Za-z0-9\.\+\#\s]{1,25}?)(?=[,;\n]|$)",
            r"experience (?:with|in)\s+([A-Za-z][A-Za-z0-9\.\+\#]{1,20})",
            r"knowledge of\s+([A-Za-z][A-Za-z0-9\.\+\#]{1,20})",
            r"familiar with\s+([A-Za-z][A-Za-z0-9\.\+\#]{1,20})",
        ]

        for pattern in triggers:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                skill = m.group(1).strip().rstrip(".,;")
                if (len(skill) >= 2
                        and skill.lower() not in ALIAS_MAP
                        and skill.lower() not in BLACKLIST
                        and skill not in found):
                    found.append(skill)

        return found

    # ============================================================
    # FINALIZE — Filter + Chuẩn hóa
    # ============================================================

    def _finalize(self, skills: list) -> list:
        """Lọc blacklist, dedup, giữ thứ tự"""
        seen = set()
        result = []

        for skill in skills:
            skill_lower = skill.lower().strip()

            # Bỏ blacklist
            if skill_lower in BLACKLIST:
                continue

            # Bỏ quá ngắn / quá dài
            if len(skill) < 2 or len(skill) > 40:
                continue

            # Bỏ nếu chỉ là số
            if re.match(r'^\d+$', skill):
                continue

            # Bỏ nếu chứa "năm kinh nghiệm"
            if re.search(r'\d+\s*năm', skill_lower):
                continue

            # Dedup case-insensitive
            if skill_lower not in seen:
                seen.add(skill_lower)
                result.append(skill)

        return result

    # ============================================================
    # BATCH PROCESSING
    # ============================================================

    def process_dataframe(self, df):
        import pandas as pd
        logger.info(f"🧠 NLP: {len(df)} jobs...")

        results = []
        for _, row in df.iterrows():
            skills = self.extract(
                title=row.get("title", ""),
                description=row.get("description", ""),
                requirements=row.get("requirements", ""),
            )
            results.append(", ".join(skills))

        df = df.copy()
        df["skills_extracted"] = results

        # Merge: skills crawled + skills extracted
        df["skills_final"] = df.apply(
            lambda r: self._merge_skills(
                r.get("skills", ""),
                r.get("skills_extracted", "")
            ), axis=1
        )

        logger.info("✅ NLP xong!")
        return df

    def _merge_skills(self, crawled: str, extracted: str) -> str:
        s1 = [s.strip() for s in str(crawled).split(",") if s.strip()]
        s2 = [s.strip() for s in str(extracted).split(",") if s.strip()]

        seen = set()
        merged = []
        for skill in s1 + s2:
            sk_lower = skill.lower().strip()

            if sk_lower in BLACKLIST:
                continue
            if len(skill) < 2 or len(skill) > 40:
                continue
            if re.search(r'\d+\s*năm', sk_lower):
                continue
            if sk_lower not in seen:
                seen.add(sk_lower)
                merged.append(skill)

        return ", ".join(merged)