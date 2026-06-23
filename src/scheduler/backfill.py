import asyncio
from datetime import datetime, timedelta

import yaml
from pathlib import Path

from src.collector.scraper import ConfigDrivenScraper
from src.collector.dedup import Deduplicator
from src.storage.db import ContentStore
from src.storage.models import ContentItem
from src.utils.logger import get_logger

logger = get_logger(__name__)
ROOT_DIR = Path(__file__).parent.parent.parent


async def backfill(config_path: str | None = None,
                   start_date: str | None = None,
                   days: int = 30) -> dict:
    if config_path is None:
        config_path = ROOT_DIR / "config.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sources = [s for s in config.get("sources", []) if s.get("enabled", False)]
    collection_cfg = config.get("collection", {})
    scraper = ConfigDrivenScraper(timeout=collection_cfg.get("request_timeout", 30))
    store = ContentStore()
    dedup = Deduplicator(store)

    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_dt = datetime.now() - timedelta(days=days)

    total_new = 0
    total_errors = 0

    for i in range(days):
        day = start_dt + timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        logger.info(f"[Backfill {i + 1}/{days}] Processing {day_str}")

        for source in sources:
            try:
                articles = await scraper.collect_source(source, lookback_days=0)
                day_articles = [a for a in articles if a.get("date", "") == day_str]

                if not day_articles:
                    # Try with lookback 0 (no date filtering, scraper returns all)
                    day_articles = articles

                for a in articles:
                    is_dup, _ = dedup.is_duplicate(a["url"], a["title"])
                    if is_dup:
                        continue
                    total_new += 1
                    store.insert(ContentItem(
                        url=a["url"],
                        title=a["title"],
                        original_text=a.get("content", ""),
                        source=source.get("name", ""),
                        published_at=a.get("date", day_str),
                        status="pending",
                    ))
            except Exception as e:
                logger.error(f"[Backfill] Error on {source.get('name')} day {day_str}: {e}")
                total_errors += 1

    logger.info(f"[Backfill] Complete: {total_new} new, {total_errors} errors")
    return {"total_new": total_new, "total_errors": total_errors}
