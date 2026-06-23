import asyncio
import json
import re
from datetime import datetime, timezone, timedelta

import httpx

from src.utils.logger import get_logger

logger = get_logger(__name__)
tz_utc8 = timezone(timedelta(hours=8))

NEWSNOW_API = "https://newsnow.busiyi.world/api/s"

PLATFORMS = {
    "weibo": {"name": "微博", "weight": 3.0},
    "zhihu": {"name": "知乎", "weight": 2.5},
    "baidu": {"name": "百度", "weight": 2.5},
    "toutiao": {"name": "今日头条", "weight": 2.0},
    "douyin": {"name": "抖音", "weight": 2.0},
    "bilibili": {"name": "B站", "weight": 1.5},
    "thepaper": {"name": "澎湃新闻", "weight": 1.0},
    "wallstreetcn": {"name": "华尔街见闻", "weight": 1.0},
    "cls": {"name": "财联社", "weight": 1.0},
    "ifeng": {"name": "凤凰网", "weight": 1.0},
    "tieba": {"name": "贴吧", "weight": 0.5},
}

STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那",
    "什么", "怎么", "如何", "为", "因为", "所以", "但是",
    "可以", "这个", "那个", "如果", "已经", "正在", "还是", "不是",
    "被", "把", "让", "给", "从", "对", "与", "或", "但", "而", "且",
    "万", "亿", "热", "热搜", "今天", "昨天", "视频", "发布", "最新",
}

KEYWORD_PATTERN = re.compile(r"[\u4e00-\u9fff\w]{2,}")


def extract_keywords(text: str, min_length: int = 2) -> list[str]:
    words = KEYWORD_PATTERN.findall(text)
    result = []
    for w in words:
        if len(w) >= min_length and w not in STOP_WORDS and not w.isdigit():
            result.append(w)
    return result


async def _fetch_platform(session: httpx.AsyncClient, pid: str) -> list[dict]:
    url = f"{NEWSNOW_API}?id={pid}&latest"
    for attempt in range(3):
        try:
            resp = await session.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") in ("success", "cache"):
                    return data.get("items", [])
            await asyncio.sleep(2 ** attempt)
        except Exception:
            await asyncio.sleep(2 ** attempt)
    return []


async def collect_trending_from_newsnow(
    platforms: list[str] | None = None,
    max_items: int = 30,
) -> dict[str, int]:
    if platforms is None:
        platforms = list(PLATFORMS.keys())

    keyword_scores: dict[str, float] = {}
    total_keywords = 0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15),
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        },
    ) as client:
        for pid in platforms:
            try:
                items = await _fetch_platform(client, pid)
                if not items:
                    logger.debug(f"[Trending] {pid}: no data")
                    continue

                pinfo = PLATFORMS.get(pid, {"weight": 1.0, "name": pid})
                weight = pinfo["weight"]
                count = 0

                for idx, item in enumerate(items[:max_items]):
                    title = item.get("title", "")
                    if not title or not isinstance(title, str):
                        continue

                    rank = idx + 1
                    position_boost = max(0.0, 1.0 - rank / max_items)
                    score = weight * (1.0 + position_boost)

                    keywords = extract_keywords(str(title))
                    for kw in keywords:
                        keyword_scores[kw] = keyword_scores.get(kw, 0.0) + score

                    count += 1

                source_count = len(set(k for v in keyword_scores.values()
                                      for k in keyword_scores if keyword_scores[k] == v
                                      )) if keyword_scores else 0
                logger.info(f"[Trending] {pinfo['name']}({pid}): {count} topics (weight={weight})")

            except Exception as e:
                logger.warning(f"[Trending] {pid} error: {e}")

    result: dict[str, int] = {}
    for kw, score in sorted(keyword_scores.items(), key=lambda x: x[1], reverse=True):
        result[kw] = max(1, round(score))

    logger.info(f"[Trending] Collected {len(result)} keywords from {len(platforms)} platforms via newsnow")
    return result
