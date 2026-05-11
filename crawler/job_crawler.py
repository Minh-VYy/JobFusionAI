from .base_crawler import BaseCrawler

class JobCrawler(BaseCrawler):
    def __init__(self, parser, cleaner, db_handler):
        super().__init__()
        self.parser = parser
        self.cleaner = cleaner
        self.db_handler = db_handler

    def crawl(self, seed_url: str, max_pages: int = 10):
        """Crawl list of pages"""
        # Logic to discover pages and crawl them
        pass
