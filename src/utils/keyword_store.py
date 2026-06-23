import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PRIORITY_FILE = DATA_DIR / "keyword_priority.json"

DEFAULT_KEYWORDS = [
    {"keyword": "教育部", "weight": 100, "enabled": True},
    {"keyword": "政策", "weight": 90, "enabled": True},
    {"keyword": "心理健康", "weight": 80, "enabled": True},
    {"keyword": "抑郁", "weight": 70, "enabled": True},
    {"keyword": "焦虑", "weight": 70, "enabled": True},
    {"keyword": "欺凌", "weight": 70, "enabled": True},
    {"keyword": "网络成瘾", "weight": 60, "enabled": True},
    {"keyword": "家庭教育", "weight": 60, "enabled": True},
    {"keyword": "青春期", "weight": 50, "enabled": True},
    {"keyword": "考试", "weight": 50, "enabled": True},
]


def load() -> list[dict]:
    if PRIORITY_FILE.exists():
        try:
            with open(PRIORITY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    _save(DEFAULT_KEYWORDS)
    return [kw.copy() for kw in DEFAULT_KEYWORDS]


def _save(keywords: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PRIORITY_FILE, "w", encoding="utf-8") as f:
        json.dump(keywords, f, ensure_ascii=False, indent=2)


def update(keywords: list[dict]):
    _save(keywords)


def reset():
    _save(DEFAULT_KEYWORDS)
