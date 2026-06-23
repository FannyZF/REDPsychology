import asyncio
import json

from src.processor.llm_client import LLMClient
from src.processor.prompt import (
    PSYCHOLOGY_SYSTEM_PROMPT,
    CATEGORY_VALID_VALUES,
    SUB_CATEGORY_VALID_VALUES,
    AUDIENCE_VALID_VALUES,
    PRIORITY_VALID_VALUES,
)
from src.storage.db import ContentStore
from src.storage.models import ContentItem
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _validate_result(result: dict) -> tuple[bool, str]:
    if not result:
        return False, "LLM returned empty result"

    category = result.get("topic_category", "")
    if category and category not in CATEGORY_VALID_VALUES:
        logger.warning(f"Invalid category: {category}")

    sub = result.get("sub_category", "")
    if sub and sub not in SUB_CATEGORY_VALID_VALUES:
        logger.warning(f"Invalid sub_category: {sub}")

    points = result.get("core_points", [])
    if isinstance(points, str):
        try:
            points = json.loads(points)
        except json.JSONDecodeError:
            points = []
    if not points or len(points) < 3:
        return False, f"core_points must be 3-5 items, got {len(points)}"
    if len(points) > 5:
        points = points[:5]
        result["core_points"] = points

    audience = result.get("target_audience", [])
    if isinstance(audience, str):
        try:
            audience = json.loads(audience)
        except json.JSONDecodeError:
            audience = []
    if not audience:
        return False, "target_audience is empty"

    priority = result.get("priority", "")
    if priority and priority not in PRIORITY_VALID_VALUES:
        logger.warning(f"Invalid priority: {priority}")

    title = result.get("xhs_title", "")
    if len(title) > 30:
        result["xhs_title"] = title[:30]

    tags = result.get("xhs_tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = []
    if len(tags) < 5:
        logger.warning(f"xhs_tags less than 5: {len(tags)}")
    if len(tags) > 10:
        result["xhs_tags"] = tags[:10]

    return True, ""


class ProcessingPipeline:
    def __init__(self, llm_client: LLMClient, store: ContentStore):
        self.llm = llm_client
        self.store = store
        self.concurrency = 3

    async def process_single(self, item: ContentItem) -> dict:
        user_prompt = f"标题：{item.title}\n\n正文：\n{item.original_text}"

        try:
            result = await self.llm.chat_json(
                system_prompt=PSYCHOLOGY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=4096,
            )
        except Exception as e:
            logger.error(f"LLM call failed for {item.id[:8]}: {e}")
            self.store.update_status(item.id, "failed", str(e))
            return {}

        valid, msg = _validate_result(result)
        if not valid:
            logger.warning(f"Validation failed for {item.id[:8]}: {msg}")
            self.store.update_status(item.id, "failed", msg)
            return {}

        try:
            self.store.update_after_process(item.id, result)
            logger.info(f"Processed {item.id[:8]} → {result.get('topic_category', '?')} / {result.get('priority', '?')}")
        except Exception as e:
            logger.error(f"DB update failed for {item.id[:8]}: {e}")
            self.store.update_status(item.id, "failed", str(e))
            return {}

        return result

    async def process_batch(self, items: list[ContentItem]) -> dict:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def process_with_limit(item):
            async with semaphore:
                return await self.process_single(item)

        results = await asyncio.gather(*[process_with_limit(i) for i in items], return_exceptions=True)

        success = sum(1 for r in results if isinstance(r, dict) and r)
        failed = len(items) - success

        logger.info(f"Batch complete: {success} success, {failed} failed (total: {len(items)})")
        return {"total": len(items), "success": success, "failed": failed}
