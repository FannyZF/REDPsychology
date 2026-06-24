import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SCHEDULE_FILE = DATA_DIR / "schedule.json"

DEFAULT_SCHEDULE = {
    "collect_hour": 7,
    "collect_minute": 0,
    "process_hour": 7,
    "process_minute": 30,
    "video_hour": 8,
    "video_minute": 15,
    "publish_hour": 18,
    "publish_minute": 0,
    "max_per_day": 5,
    "publish_window_minutes": 30,
    "video_enabled": True,
    "trending_enabled": True,
    "trending_sources": ["weibo"],
    "trending_multiplier": 1.0,
}


def load() -> dict:
    if SCHEDULE_FILE.exists():
        try:
            with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config = DEFAULT_SCHEDULE.copy()
            config.update(saved)
            return config
        except (json.JSONDecodeError, OSError):
            pass
    _save(DEFAULT_SCHEDULE)
    return DEFAULT_SCHEDULE.copy()


def _save(config: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def update(key: str, value):
    config = load()
    if key in DEFAULT_SCHEDULE:
        config[key] = value
    _save(config)
