import re
import asyncio
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.utils.logger import get_logger

logger = get_logger(__name__)
tz_utc8 = timezone(timedelta(hours=8))

DATE_PATTERNS = {
    "iso": re.compile(r"\d{4}-\d{2}-\d{2}"),
    "slash": re.compile(r"\d{4}/\d{1,2}/\d{1,2}"),
    "chinese": re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
    "dot": re.compile(r"\d{4}\.\d{1,2}\.\d{1,2}"),
}


class ConfigDrivenScraper:
    def __init__(self, timeout: int = 30, max_retries: int = 2):
        self.timeout = timeout
        self.max_retries = max_retries

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> str:
        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                if resp.encoding and resp.encoding.lower() != "utf-8":
                    resp.encoding = "utf-8"
                return resp.text
            except Exception as e:
                logger.warning(f"Fetch attempt {attempt + 1}/{self.max_retries + 1} failed for {url}: {e}")
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(2 ** attempt)
        return ""

    def _clean_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript", "iframe", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
        return "\n".join(lines)

    def _extract_text(self, soup: BeautifulSoup, selector: str) -> str:
        if not selector:
            return ""
        els = soup.select(selector)
        if not els:
            return ""
        return els[0].get_text(strip=True)

    def _extract_attr(self, soup: BeautifulSoup, selector: str, attr: str) -> str:
        if not selector:
            return ""
        els = soup.select(selector)
        if not els:
            return ""
        return els[0].get(attr, "")

    def _extract_all_text(self, soup: BeautifulSoup, selector: str) -> str:
        if not selector:
            return ""
        els = soup.select(selector)
        return " ".join(el.get_text(strip=True) for el in els if el.get_text(strip=True))

    def _parse_date(self, raw: str) -> str:
        if not raw:
            return ""
        raw = raw.strip()

        m = DATE_PATTERNS["chinese"].search(raw)
        if m:
            return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

        m = DATE_PATTERNS["iso"].search(raw)
        if m:
            return m.group(0)[:10]

        m = DATE_PATTERNS["slash"].search(raw)
        if m:
            parts = m.group(0).split("/")
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"

        m = DATE_PATTERNS["dot"].search(raw)
        if m:
            parts = m.group(0).split(".")
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"

        return ""

    def _resolve_url(self, base_url: str, link: str) -> str:
        if not link:
            return ""
        if link.startswith("http"):
            return link
        if link.startswith("//"):
            return "https:" + link
        return urljoin(base_url, link)

    async def fetch_list(self, source_config: dict) -> list[dict]:
        results = []
        selectors = source_config.get("selectors", {})
        article_selector = source_config.get("article_selector", {})
        pagination = source_config.get("pagination", {})
        base_url = source_config.get("base_url", "")
        list_url = source_config.get("list_url", "")
        max_pages = source_config.get("max_list_pages", 1)

        pattern = pagination.get("pattern", "")
        start = pagination.get("start", 1)

        async with self._build_client() as client:
            for page in range(start, start + max_pages):
                if pattern and page > start:
                    page_url = source_config["base_url"].rstrip("/") + pattern.replace("{page}", str(page))
                else:
                    page_url = list_url

                try:
                    html = await self._fetch(client, page_url)
                except Exception as e:
                    logger.error(f"Failed to fetch list page {page_url}: {e}")
                    if page == start:
                        break
                    continue

                soup = BeautifulSoup(html, "lxml")
                container_sel = selectors.get("list_container", "")
                if container_sel:
                    items = soup.select(container_sel)
                else:
                    items = [soup]

                if not items and page > start:
                    break

                for item in items:
                    title = self._extract_text(item, selectors.get("title", "a"))
                    if not title:
                        continue

                    raw_link = self._extract_attr(item, selectors.get("link", "a"), "href")
                    link = self._resolve_url(base_url, raw_link)
                    if not link:
                        continue

                    raw_date = None
                    date_sel = selectors.get("date", "")
                    date_attr = selectors.get("date_attr", "")

                    if date_sel and date_attr:
                        raw_date = self._extract_attr(item, date_sel, date_attr)
                    elif date_sel:
                        raw_date = self._extract_text(item, date_sel)

                    summary_sel = selectors.get("summary", "")
                    summary = self._extract_text(item, summary_sel) if summary_sel else ""

                    parsed_date = self._parse_date(raw_date or "")

                    results.append({
                        "title": title,
                        "url": link,
                        "date": parsed_date,
                        "raw_date": raw_date or "",
                        "summary": summary,
                        "source": source_config.get("name", ""),
                    })

                if not pattern or page >= start + max_pages - 1:
                    break

        return results

    async def fetch_article(self, url: str, article_config: dict) -> str:
        content_sel = article_config.get("content", "")
        if not content_sel:
            content_sel = "article, .article, .content, .post-body, .entry-content, div.article_content, div.TRS_Editor"

        async with self._build_client() as client:
            html = await self._fetch(client, url)
            soup = BeautifulSoup(html, "lxml")
            text = self._extract_all_text(soup, content_sel)
            if not text:
                text = self._clean_html(html)
            return text

    async def collect_source(self, source_config: dict, lookback_days: int = 1,
                             existing_urls: set | None = None) -> list[dict]:
        if existing_urls is None:
            existing_urls = set()

        cutoff_date = None
        if lookback_days > 0:
            cutoff_date = (datetime.now(tz_utc8) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        list_items = await self.fetch_list(source_config)
        logger.info(f"Fetched {len(list_items)} list items from {source_config.get('name', 'unknown')}")

        articles = []
        skipped_old = 0
        skipped_dup = 0

        for item in list_items:
            url = item["url"]
            if url in existing_urls:
                skipped_dup += 1
                continue

            if cutoff_date and item["date"] and item["date"] < cutoff_date:
                skipped_old += 1
                continue

            try:
                text = await self.fetch_article(url, source_config.get("article_selector", {}))
                item["content"] = text
                articles.append(item)
                existing_urls.add(url)
            except Exception as e:
                logger.warning(f"Failed to fetch article {url}: {e}")
                continue

        logger.info(
            f"Collected {len(articles)} new articles from {source_config.get('name', 'unknown')} "
            f"(skipped: {skipped_dup} dup, {skipped_old} old)"
        )
        return articles
