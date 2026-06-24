import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
KEY_FILE = DATA_DIR / "api_key.json"

DEFAULT_KEYS = {
    "deepseek_api_key": "",
    "deepseek_base_url": "https://api.deepseek.com",
    "volcengine_api_key": "",
    "wechat_appid": "",
    "wechat_secret": "",
}


def load(env: dict | None = None) -> dict:
    keys = DEFAULT_KEYS.copy()

    if env is None:
        env = {}
    for env_key, store_key in [
        ("DEEPSEEK_API_KEY", "deepseek_api_key"),
        ("DEEPSEEK_BASE_URL", "deepseek_base_url"),
        ("VOLCENGINE_API_KEY", "volcengine_api_key"),
    ]:
        val = env.get(env_key, "")
        if val:
            keys[store_key] = val

    if KEY_FILE.exists():
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            keys.update(saved)
        except (json.JSONDecodeError, OSError):
            pass

    _save(keys)
    return keys


def _save(keys: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=2)


def update(key: str, value: str):
    keys = load()
    if key in DEFAULT_KEYS:
        keys[key] = value
    _save(keys)


def get(key: str) -> str:
    keys = load()
    return keys.get(key, "")
