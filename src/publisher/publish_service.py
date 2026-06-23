import json
import random
import time
from datetime import datetime, timezone, timedelta

from src.publisher.selenium_publisher import XiaohongshuPublisher
from src.storage.db import ContentStore
from src.storage.models import ContentItem
from src.utils.logger import get_logger
from src.utils.config_store import load as load_schedule

logger = get_logger(__name__)
tz_utc8 = timezone(timedelta(hours=8))


class ContentPublisher:
    def __init__(self, xhs: XiaohongshuPublisher, store: ContentStore):
        self.xhs = xhs
        self.store = store

    def publish_one(self, content: ContentItem) -> bool:
        has_video = bool(content.video_path)
        core_points = []
        if content.core_points:
            try:
                core_points = json.loads(content.core_points)
            except json.JSONDecodeError:
                pass

        tags = []
        if content.xhs_tags:
            try:
                tags = json.loads(content.xhs_tags)
            except json.JSONDecodeError:
                pass

        title = content.xhs_title or content.title
        body = content.xhs_content or content.summary

        if has_video:
            logger.info(f"Publishing video note: {content.id[:8]} -> {title[:20]}")
            ok = self.xhs.publish_video_note(
                video_path=content.video_path,
                title=title,
                content=body,
                tags=tags,
            )
        else:
            logger.info(f"Publishing image note: {content.id[:8]} -> {title[:20]}")
            ok = self.xhs.publish_image_note(
                title=title,
                content=body,
                tags=tags,
            )

        if ok:
            self.store.update_publish_status(content.id)
            logger.info(f"Published: {content.id[:8]}")
        else:
            logger.error(f"Publish failed: {content.id[:8]}")

        return ok

    def publish_queue(self) -> dict:
        items = self.store.get_publish_queue(limit=1)
        if not items:
            logger.info("No items in publish queue")
            return {"published": 0}

        item = items[0]
        try:
            ok = self.publish_one(item)
            return {"published": 1 if ok else 0, "failed": 0 if ok else 1}
        except Exception as e:
            logger.error(f"Publish error for {item.id[:8]}: {e}")
            return {"published": 0, "failed": 1, "error": str(e)}


class PublishScheduler:
    def __init__(self, store: ContentStore):
        self.store = store

    def can_publish_now(self) -> tuple[bool, str]:
        config = load_schedule()
        max_per_day = config.get("max_per_day", 1)
        publish_hour = config.get("publish_hour", 18)
        publish_minute = config.get("publish_minute", 0)
        window_minutes = config.get("publish_window_minutes", 30)

        now_dt = datetime.now(tz_utc8)
        window_start = now_dt.replace(hour=publish_hour, minute=publish_minute, second=0, microsecond=0)
        window_end = window_start + timedelta(minutes=window_minutes)

        if now_dt < window_start:
            return False, f"Before publish window ({publish_hour}:{publish_minute:02d})"
        if now_dt > window_end:
            return False, "After publish window"

        published_today = self.store.count_published_today()
        if published_today >= max_per_day:
            return False, f"Daily limit reached ({published_today}/{max_per_day})"

        return True, "Ok"

    def wait_until_window(self) -> bool:
        config = load_schedule()
        publish_hour = config.get("publish_hour", 18)
        publish_minute = config.get("publish_minute", 0)

        now_dt = datetime.now(tz_utc8)
        target = now_dt.replace(hour=publish_hour, minute=publish_minute, second=0, microsecond=0)

        if now_dt >= target:
            target = target + timedelta(days=1)

        wait_seconds = (target - now_dt).total_seconds()
        if wait_seconds <= 0:
            return True

        logger.info(f"Waiting {wait_seconds:.0f}s until publish window ({publish_hour}:{publish_minute:02d})")
        time.sleep(min(wait_seconds, 3600))
        return True

    def auto_publish(self, xhs: XiaohongshuPublisher) -> dict:
        self.wait_until_window()

        can, reason = self.can_publish_now()
        if not can:
            logger.warning(f"Cannot publish: {reason}")
            return {"published": 0, "reason": reason}

        publisher = ContentPublisher(xhs, self.store)

        try:
            xhs.start()
            if not xhs.ensure_login():
                logger.error("Login failed, cannot publish")
                return {"published": 0, "reason": "login_failed"}

            result = publisher.publish_queue()
            return result
        finally:
            xhs.close()
