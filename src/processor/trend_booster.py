import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.utils.logger import get_logger

logger = get_logger(__name__)
tz_utc8 = timezone(timedelta(hours=8))

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BOOST_FILE = DATA_DIR / "trend_boosts.json"


def load_boosts() -> dict:
    if BOOST_FILE.exists():
        try:
            with open(BOOST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_boosts(boosts: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(BOOST_FILE, "w", encoding="utf-8") as f:
        json.dump(boosts, f, ensure_ascii=False, indent=2)


def expire_old_boosts(boosts: dict, max_age_days: int = 3) -> dict:
    now = datetime.now(tz_utc8)
    cutoff = now - timedelta(days=max_age_days)
    cleaned = {}
    for keyword, info in boosts.items():
        added_str = info.get("added", "")
        if added_str:
            try:
                added_dt = datetime.fromisoformat(added_str)
                if added_dt >= cutoff:
                    cleaned[keyword] = info
            except ValueError:
                cleaned[keyword] = info
        else:
            cleaned[keyword] = info
    return cleaned


def merge_trending(keyword_counts: dict[str, int],
                   multiplier: float = 1.0,
                   base_boost: int = 30) -> dict:
    boosts = load_boosts()
    boosts = expire_old_boosts(boosts)
    now_str = datetime.now(tz_utc8).isoformat()

    for keyword, count in keyword_counts.items():
        if keyword in boosts:
            info = boosts[keyword]
            info["count"] = count
            info["updated"] = now_str
        else:
            boosts[keyword] = {
                "count": count,
                "added": now_str,
                "updated": now_str,
            }

    save_boosts(boosts)
    logger.info(f"[TrendBooster] Merged {len(keyword_counts)} trending keywords, total boosts: {len(boosts)}")
    return boosts


def get_boost(keyword: str) -> int:
    boosts = load_boosts()
    boosts = expire_old_boosts(boosts)

    keyword_lower = keyword.lower()
    for kw, info in boosts.items():
        if kw.lower() == keyword_lower or kw.lower() in keyword_lower or keyword_lower in kw.lower():
            count = info.get("count", 1)
            added_str = info.get("added", "")
            if added_str:
                try:
                    added_dt = datetime.fromisoformat(added_str)
                    age_days = (datetime.now(tz_utc8) - added_dt).days
                    decay = max(0.0, 1.0 - age_days / 3.0)
                except ValueError:
                    decay = 1.0
            else:
                decay = 1.0
            boost = int(count * 15 * decay)
            return min(boost, 150)

    return 0


def get_all_active_boosts() -> dict[str, int]:
    boosts = load_boosts()
    boosts = expire_old_boosts(boosts)
    return {kw: get_boost(kw) for kw in boosts}
