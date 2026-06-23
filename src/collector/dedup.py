from difflib import SequenceMatcher

from src.utils.logger import get_logger

logger = get_logger(__name__)

TITLE_SIMILARITY_THRESHOLD = 0.85


class Deduplicator:
    def __init__(self, store):
        self.store = store

    def is_duplicate_url(self, url: str) -> bool:
        return self.store.exists(url)

    def is_similar_title(self, title: str, threshold: float = TITLE_SIMILARITY_THRESHOLD) -> tuple[bool, str]:
        recent = self.store.list_all(limit=200, offset=0)
        for item in recent:
            if not item.title:
                continue
            ratio = SequenceMatcher(None, title, item.title).ratio()
            if ratio >= threshold:
                return True, item.title
        return False, ""

    def is_duplicate(self, url: str, title: str) -> tuple[bool, str]:
        if self.is_duplicate_url(url):
            return True, "url_exists"

        similar, matched = self.is_similar_title(title)
        if similar:
            logger.info(f"Title similarity: '{title[:40]}...' ~ '{matched[:40]}...'")
            return True, "similar_title"

        return False, ""
