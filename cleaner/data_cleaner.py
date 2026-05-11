# cleaner/data_cleaner.py
import pandas as pd
import re
import logging

logger = logging.getLogger(__name__)

class DataCleaner:
    """
    Làm sạch và chuẩn hóa dữ liệu job sau khi crawl.
    Input : list[dict] hoặc DataFrame thô
    Output: DataFrame đã clean
    """

    def clean(self, jobs: list[dict]) -> pd.DataFrame:
        """Pipeline làm sạch chính"""
        if not jobs:
            logger.warning("⚠️  Không có dữ liệu để clean")
            return pd.DataFrame()

        df = pd.DataFrame(jobs)
        logger.info(f"🧹 Bắt đầu clean {len(df)} records...")

        df = self._drop_duplicates(df)
        df = self._clean_title(df)
        df = self._clean_salary(df)
        df = self._clean_location(df)
        df = self._clean_company(df)
        df = self._fill_missing(df)

        logger.info(f"✅ Clean xong: {len(df)} records hợp lệ")
        return df

    # ==================== CÁC BƯỚC CLEAN ====================

    def _drop_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Xóa job trùng lặp theo URL hoặc title+company"""
        before = len(df)

        # Ưu tiên dedup theo URL
        if "job_url" in df.columns:
            df = df.drop_duplicates(subset=["job_url"], keep="first")
        
        # Dedup theo title + company nếu không có URL
        df = df.drop_duplicates(subset=["title", "company"], keep="first")

        after = len(df)
        logger.info(f"   🗑️  Xóa {before - after} duplicates")
        return df

    def _clean_title(self, df: pd.DataFrame) -> pd.DataFrame:
        """Chuẩn hóa title — xóa ký tự thừa, capitalize"""
        if "title" not in df.columns:
            return df

        df["title"] = (
            df["title"]
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)   # Nhiều space → 1 space
            .str.replace(r"[^\w\s\-\/\(\)\,\.]", "", regex=True)  # Xóa ký tự lạ
        )

        # Xóa rows có title rỗng hoặc quá ngắn
        df = df[df["title"].str.len() > 3]
        return df

    def _clean_salary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Chuẩn hóa salary — thống nhất format"""
        if "salary" not in df.columns:
            return df

        def normalize_salary(s: str) -> str:
            s = str(s).strip()
            if not s or s in ["nan", "None", ""]:
                return "Thỏa thuận"
            # Xóa HTML tags nếu còn sót
            s = re.sub(r"<[^>]+>", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        df["salary"] = df["salary"].apply(normalize_salary)
        return df

    def _clean_location(self, df: pd.DataFrame) -> pd.DataFrame:
        if "location" not in df.columns:
            return df

        def normalize_location(s: str) -> str:
            s = str(s).strip()
            if not s or s in ["nan", "None"]:
                return "Không xác định"
            
            # Xóa chữ "(mới)" TopCV thêm vào
            s = re.sub(r"\s*\(mới\)", "", s)
            s = re.sub(r"\s*\(new\)", "", s, flags=re.IGNORECASE)
            
            # Chuẩn hóa tên thành phố
            location_map = {
                "Hồ Chí Minh": "TP. Hồ Chí Minh",
                "TP.HCM": "TP. Hồ Chí Minh",
                "HCM": "TP. Hồ Chí Minh",
                "HN": "Hà Nội",
                "DN": "Đà Nẵng",
            }
            for short, full in location_map.items():
                if short in s:
                    s = s.replace(short, full)
            
            return s.strip()

        df["location"] = df["location"].apply(normalize_location)
        return df
    def _clean_company(self, df: pd.DataFrame) -> pd.DataFrame:
        """Chuẩn hóa tên công ty"""
        if "company" not in df.columns:
            return df

        df["company"] = (
            df["company"]
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
        )
        return df

    def _fill_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        """Điền giá trị mặc định cho ô trống"""
        defaults = {
            "title": "Không có tiêu đề",
            "company": "Không xác định",
            "salary": "Thỏa thuận",
            "location": "Không xác định",
            "skills": "",
            "description": "",
        }
        for col, default in defaults.items():
            if col in df.columns:
                df[col] = df[col].replace(
                    ["", "nan", "None", None], default
                )
        return df
