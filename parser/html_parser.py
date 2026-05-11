# parser/html_parser.py
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class HTMLParser:
    """
    Utility class — parse HTML thô thành dict.
    Dùng chung cho tất cả crawler.
    """

    def __init__(self, html: str):
        self.soup = BeautifulSoup(html, "lxml")

    def select_text(self, selector: str, default: str = "") -> str:
        """Lấy text của 1 element theo CSS selector"""
        el = self.soup.select_one(selector)
        return el.get_text(strip=True) if el else default

    def select_all_text(self, selector: str) -> list[str]:
        """Lấy text của nhiều elements"""
        els = self.soup.select(selector)
        return [el.get_text(strip=True) for el in els]

    def select_attr(self, selector: str, attr: str, default: str = "") -> str:
        """Lấy attribute của element (href, src,...)"""
        el = self.soup.select_one(selector)
        return el.get(attr, default) if el else default
