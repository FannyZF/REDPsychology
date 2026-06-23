import asyncio
import yaml
from pathlib import Path

from src.collector.scraper import ConfigDrivenScraper
from src.collector.dedup import Deduplicator
from src.storage.db import ContentStore
from src.storage.models import ContentItem
from src.utils.logger import get_logger

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).parent.parent.parent


def load_config(config_path: str | None = None) -> dict:
    if config_path is None:
        config_path = ROOT_DIR / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def collect_all(config: dict | None = None, lookback_days: int | None = None) -> dict:
    if config is None:
        config = load_config()

    collection_cfg = config.get("collection", {})
    if lookback_days is None:
        lookback_days = collection_cfg.get("lookback_days", 1)

    sources = [s for s in config.get("sources", []) if s.get("enabled", False)]
    scraper = ConfigDrivenScraper(timeout=collection_cfg.get("request_timeout", 30))
    store = ContentStore()
    dedup = Deduplicator(store)

    total_new = 0
    total_skipped = 0
    errors = []

    semaphore = asyncio.Semaphore(collection_cfg.get("max_concurrent_sources", 3))

    async def process_one(source):
        nonlocal total_new, total_skipped
        async with semaphore:
            try:
                articles = await scraper.collect_source(source, lookback_days)
                source_new = 0
                for a in articles:
                    is_dup, reason = dedup.is_duplicate(a["url"], a["title"])
                    if is_dup:
                        total_skipped += 1
                        continue
                    total_new += 1
                    source_new += 1
                    store.insert(ContentItem(
                        url=a["url"],
                        title=a["title"],
                        original_text=a.get("content", ""),
                        source=source.get("name", ""),
                        published_at=a.get("date", ""),
                        status="pending",
                    ))
                logger.info(f"[{source.get('name', '')}] {source_new} new, {len(articles) - source_new} skipped")
            except Exception as e:
                logger.error(f"[{source.get('name', '')}] Error: {e}")
                errors.append({"source": source.get("name", "unknown"), "error": str(e)})

    await asyncio.gather(*[process_one(s) for s in sources])

    return {
        "total_new": total_new,
        "total_skipped": total_skipped,
        "errors": errors,
    }
