import asyncio
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.utils.logger import get_logger

logger = get_logger(__name__)

CANDIDATE_CLASSES = [
    "news", "article", "list", "post", "content",
    "news-list", "news_list", "article-list", "article_list",
]


def _score_container(container) -> tuple[int, int, int]:
    links = len(container.select("a"))
    dates = len(container.select(
        "time, .time, .date, .pubdate, span[class*=date], span[class*=time]"
    ))
    children = len(list(container.children))
    return links, dates, children


def _css_path(el, root) -> str:
    if el == root:
        return ""
    parts = []
    current = el
    while current and current != root:
        tag = current.name
        cls = current.get("class", [])
        if cls:
            parts.insert(0, f"{tag}.{'.'.join(cls)}")
        else:
            parts.insert(0, tag)
        current = current.parent
    return " > ".join(parts)


async def detect_selectors(url: str, timeout: int = 30) -> Optional[dict]:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        },
    ) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    soup = BeautifulSoup(html, "lxml")

    best_container = None
    best_score = (0, 0, 0)

    for cls in CANDIDATE_CLASSES:
        for el in soup.select(f".{cls}, [class*={cls}]"):
            score = _score_container(el)
            if score[0] > best_score[0]:
                best_score = score
                best_container = el
            elif score[0] == best_score[0] and score[1] > best_score[1]:
                best_score = score
                best_container = el

    if not best_container:
        body = soup.find("body")
        if body:
            best_container = body
        else:
            return None

    list_container_sel = _css_path(best_container, soup)

    title_sel = ""
    link_sel = ""
    date_sel = ""
    date_attr = ""
    summary_sel = ""

    links = best_container.select("a")
    for a in links:
        text = a.get_text(strip=True)
        if len(text) > 5:
            parent = a.parent
            title_path = _css_path(a, best_container) or "a"
            title_sel = title_path
            link_sel = title_path
            break

    time_els = best_container.select("time, .time, .date, .pubdate")
    for te in time_els:
        date_sel = _css_path(te, best_container) or "time"
        if te.name == "time" and te.get("datetime"):
            date_attr = "datetime"
        break

    return {
        "list_container": list_container_sel,
        "title": title_sel,
        "link": link_sel,
        "date": date_sel,
        "date_attr": date_attr,
        "summary": summary_sel,
    }
