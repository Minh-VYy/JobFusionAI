# cleaner/duplicate_detector.py
import hashlib
import re
import logging
from typing import List
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class DuplicateDetector:
    """
    Phát hiện bài đăng trùng lặp bằng 3 phương pháp:
    1. Exact hash match
    2. Phone number match
    3. TF-IDF Cosine Similarity
    """

    def __init__(self, similarity_threshold: float = 0.85):
        self.threshold = similarity_threshold
        self.seen_hashes = set()
        self.seen_phones = set()
        self.corpus = []          # List text đã lưu
        self.corpus_ids = []      # ID tương ứng
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            min_df=1,
        )
        self._fitted = False

    def load_existing(self, fingerprints: List[str]):
        """Load fingerprints từ DB để nhớ bài cũ sau khi restart."""
        for fp in fingerprints:
            self.seen_hashes.add(fp)
        logger.info(f"[DuplicateDetector] Loaded {len(fingerprints)} existing fingerprints")

    # ============================================================
    # MAIN CHECK
    # ============================================================

    def is_duplicate(self, text: str, phone: str = "") -> tuple[bool, str, float]:
        """
        Kiểm tra bài có trùng không.
        Trả về (is_dup, method, similarity_score)
        """
        normalized = self._normalize(text)

        # Bước 1: Exact hash
        fingerprint = self._make_hash(normalized)
        if fingerprint in self.seen_hashes:
            return True, "exact_hash", 1.0

        # Bước 2: Phone match
        if phone and phone in self.seen_phones:
            return True, "phone_match", 1.0

        # Bước 3: TF-IDF Cosine Similarity
        if len(self.corpus) >= 2:
            sim_score = self._cosine_check(normalized)
            if sim_score >= self.threshold:
                return True, "cosine_similarity", sim_score

        # Không trùng → thêm vào corpus
        self.seen_hashes.add(fingerprint)
        if phone:
            self.seen_phones.add(phone)
        self._add_to_corpus(normalized)

        return False, "", 0.0

    # ============================================================
    # COSINE SIMILARITY
    # ============================================================

    def _cosine_check(self, text: str) -> float:
        """So sánh text mới với toàn bộ corpus"""
        try:
            all_texts = self.corpus + [text]
            tfidf_matrix = self.vectorizer.fit_transform(all_texts)

            # Vector của text mới (dòng cuối)
            new_vec = tfidf_matrix[-1]
            # Matrix của corpus (bỏ dòng cuối)
            corpus_matrix = tfidf_matrix[:-1]

            if corpus_matrix.shape[0] == 0:
                return 0.0

            similarities = cosine_similarity(new_vec, corpus_matrix)[0]
            return float(np.max(similarities))

        except Exception as e:
            logger.debug(f"Cosine error: {e}")
            return 0.0

    # ============================================================
    # HELPERS
    # ============================================================

    def _normalize(self, text: str) -> str:
        """Normalize text để so sánh chính xác hơn"""
        text = text.lower().strip()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s]', '', text)
        # Xóa số điện thoại (tránh so sánh nhầm do thay số)
        text = re.sub(r'(?:0|\+84)\d{9}', 'PHONE', text)
        return text

    def _make_hash(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _add_to_corpus(self, text: str):
        self.corpus.append(text)

    def batch_check(self, texts: list[str], phones: list[str] = None) -> list[dict]:
        """Kiểm tra duplicate cho list bài"""
        if phones is None:
            phones = [""] * len(texts)

        results = []
        for text, phone in zip(texts, phones):
            is_dup, method, score = self.is_duplicate(text, phone)
            results.append({
                "is_duplicate": is_dup,
                "method": method,
                "score": round(score, 3),
            })
        return results