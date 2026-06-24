import asyncio
import threading
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.storage.db import ContentStore
from src.processor.llm_client import LLMClient
from src.processor.pipeline import ProcessingPipeline
from src.utils.logger import get_logger
from src.utils.key_store import load as load_keys
from src.utils.config_store import load as load_schedule

logger = get_logger(__name__)
tz_utc8 = timezone(timedelta(hours=8))


class DailyPipeline:
    def __init__(self):
        self.store = ContentStore()

    async def step_collect(self):
        from src.collector.orchestrator import collect_all
        logger.info("[Daily] Step 1: Collecting sources...")
        try:
            result = await collect_all()
            logger.info(f"[Daily] Collect done: {result['total_new']} new, {result['total_skipped']} skipped")

            logger.info("[Daily] Step 1b: Collecting trending keywords...")
            await self._collect_trending()
            return result
        except Exception as e:
            logger.error(f"[Daily] Collect failed: {e}")
            return None

    async def _collect_trending(self):
        try:
            from src.collector.trending import collect_trending_from_newsnow
            from src.processor.trend_booster import merge_trending
            from src.utils.config_store import load as load_schedule
            config = load_schedule()
            enabled = config.get("trending_enabled", True)
            if not enabled:
                logger.info("[Trending] Disabled in config")
                return
            counts = await collect_trending_from_newsnow()
            if counts:
                merge_trending(counts)
                logger.info(f"[Trending] Collected {len(counts)} keywords via newsnow")
        except Exception as e:
            logger.warning(f"[Trending] Error: {e}")

    def step_process(self):
        logger.info("[Daily] Step 2: LLM processing...")
        pending = self.store.get_pending(limit=50)
        if not pending:
            logger.info("[Daily] No pending items")
            return {"success": 0, "failed": 0}

        client = LLMClient()
        pipeline = ProcessingPipeline(client, self.store)
        result = asyncio.run(pipeline.process_batch(pending))
        logger.info(f"[Daily] Process done: {result['success']} success, {result['failed']} failed, tokens={client.total_tokens}")
        return result

    async def step_video(self):
        from src.processor.scorer import select_top, score_content
        from src.utils.keyword_store import load as load_kw_config

        processed = self.store.get_processed(limit=50)
        if not processed:
            logger.info("[Daily] No processed items for video scoring")
            return {"success": 0, "failed": 0}

        kw_config = load_kw_config()
        top_items = select_top(processed, top_n=3, keywords_config=kw_config)

        if not top_items:
            logger.info("[Daily] No items matched keyword priority")
            return {"success": 0, "failed": 0}

        # Check video.enabled from both config.yaml and schedule.json
        video_enabled = True
        try:
            import yaml
            with open("/app/config.yaml", "r") as f:
                cfg = yaml.safe_load(f)
            video_enabled = cfg.get("video", {}).get("enabled", True)
        except Exception:
            pass
        try:
            from src.utils.config_store import load as load_schedule
            sch = load_schedule()
            if "video_enabled" in sch:
                video_enabled = sch["video_enabled"]
        except Exception:
            pass

        if not video_enabled:
            from src.video_generator.cover import generate_cover
            logger.info(f"[Daily] Video disabled, generating AI cover images for {len(top_items)} items")
            for item in top_items:
                path = await generate_cover(item.id[:8], item.xhs_title or item.title,
                                            item.topic_category)
                if path:
                    self.store.update_video_status(item.id, path, 0)
                    logger.info(f"Cover: {item.id[:8]}")
            return {"success": len(top_items), "failed": 0}

        from src.video_generator.composer import generate_all
        keys = load_keys()
        volc_key = keys.get("volcengine_api_key", "")
        if not volc_key:
            logger.warning("[Daily] Skipping video: no Volcengine API key")
            return {"success": 0, "failed": 0}

    def step_publish(self):
        from src.publisher.publish_service import PublishScheduler

        scheduler = PublishScheduler(self.store)
        can, reason = scheduler.can_publish_now()
        if not can:
            logger.info(f"[Daily] Skipping publish: {reason}")
            return {"published": 0, "reason": reason}

        queue = self.store.get_publish_queue(limit=1)
        if not queue:
            logger.info("[Daily] No items in publish queue")
            return {"published": 0}

        item = queue[0]
        logger.info(f"[Daily] Step 4: Publishing: {item.id[:8]}")

        # Check WeChat auto-publish
        try:
            from src.utils.config_store import load as load_schedule
            sch = load_schedule()
            auto_wechat = sch.get("wechat_auto_publish", False)
        except Exception:
            auto_wechat = False

        if auto_wechat:
            try:
                from src.utils.key_store import load as load_keys
                from src.publisher.wechat_publisher import publish_article
                keys = load_keys()
                appid = keys.get("wechat_appid", "")
                secret = keys.get("wechat_secret", "")
                if appid and secret and item.video_path:
                    ok = publish_article(
                        title=item.xhs_title or item.title,
                        content=(item.xhs_content or item.summary).replace("\\n", "\n"),
                        cover_path=item.video_path,
                        appid=appid, secret=secret,
                        digest=item.summary[:100] if item.summary else "",
                    )
                    if ok:
                        logger.info(f"[Daily] WeChat publish success: {item.id[:8]}")
                    else:
                        logger.error(f"[Daily] WeChat publish failed: {item.id[:8]}")
            except Exception as e:
                logger.error(f"[Daily] WeChat publish error: {e}")

        self.store.update_publish_status(item.id)
        logger.info(f"[Daily] Published: {item.id[:8]}")
        return {"published": 1}

    def run_full(self):
        logger.info("=" * 40)
        logger.info("DAILY PIPELINE START")
        logger.info("=" * 40)

        asyncio.run(self.step_collect())
        self.step_process()
        asyncio.run(self.step_video())
        self.step_publish()

        logger.info("=" * 40)
        logger.info("DAILY PIPELINE COMPLETE")
        logger.info("=" * 40)


def _run_collect_in_thread(pipeline: DailyPipeline):
    asyncio.run(pipeline.step_collect())


def setup_scheduler() -> BackgroundScheduler:
    config = load_schedule()
    pipeline = DailyPipeline()

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    collect_hour = config.get("collect_hour", 7)
    collect_min = config.get("collect_minute", 0)
    scheduler.add_job(
        _run_collect_in_thread,
        CronTrigger(hour=collect_hour, minute=collect_min),
        args=[pipeline],
        id="collect",
        name="collect",
    )

    process_hour = config.get("process_hour", 7)
    process_min = config.get("process_minute", 30)
    scheduler.add_job(
        pipeline.step_process,
        CronTrigger(hour=process_hour, minute=process_min),
        id="process",
        name="process",
    )

    video_hour = config.get("video_hour", 8)
    video_min = config.get("video_minute", 15)
    scheduler.add_job(
        lambda: asyncio.run(pipeline.step_video()),
        CronTrigger(hour=video_hour, minute=video_min),
        id="video",
        name="video",
    )

    publish_hour = config.get("publish_hour", 18)
    publish_min = config.get("publish_minute", 0)
    scheduler.add_job(
        pipeline.step_publish,
        CronTrigger(hour=publish_hour, minute=publish_min),
        id="publish",
        name="publish",
    )

    logger.info(
        f"Scheduler configured: "
        f"collect={collect_hour:02d}:{collect_min:02d}, "
        f"process={process_hour:02d}:{process_min:02d}, "
        f"video={video_hour:02d}:{video_min:02d}, "
        f"publish={publish_hour:02d}:{publish_min:02d}"
    )

    return scheduler
