from src.storage.models import ContentItem
from src.utils.keyword_store import load as load_keywords
from src.processor.trend_booster import get_boost


def score_content(item: ContentItem, keywords_config: list[dict] | None = None,
                  use_trending: bool = True) -> int:
    if keywords_config is None:
        keywords_config = load_keywords()

    text = (item.title + " " + item.original_text + " " +
            item.xhs_title + " " + item.xhs_content + " " +
            item.topic_category + " " + item.sub_category + " " +
            item.summary).lower()

    total = 0
    matched = 0

    for kw in keywords_config:
        if not kw.get("enabled", True):
            continue
        keyword = kw.get("keyword", "").lower()
        weight = kw.get("weight", 50)
        if keyword and keyword in text:
            total += weight
            matched += 1

    if use_trending and text:
        text_keywords = set()
        for word in text.split():
            if len(word) >= 2:
                text_keywords.add(word)
        trend_boost_total = 0
        for w in text_keywords:
            boost = get_boost(w)
            if boost > 0:
                trend_boost_total += boost
        total += min(trend_boost_total, 200)

    if total == 0:
        return 0

    bonus = min(matched * 10, 50)
    return total + bonus


def select_top(content_items: list[ContentItem], top_n: int = 3,
               keywords_config: list[dict] | None = None) -> list[ContentItem]:
    if keywords_config is None:
        keywords_config = load_keywords()

    scored = [(score_content(item, keywords_config), item) for item in content_items]
    scored.sort(key=lambda x: x[0], reverse=True)

    selected = [item for score, item in scored[:top_n] if score > 0]

    return selected
