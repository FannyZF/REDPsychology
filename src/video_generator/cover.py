import httpx
from pathlib import Path

from src.utils.logger import get_logger
from src.utils.key_store import load as load_keys

logger = get_logger(__name__)

ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
IMAGE_MODEL = "doubao-seedream-4-0-250828"

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "thumbnails"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def generate_cover(content_id: str, title: str, category: str = "") -> str:
    keys = load_keys()
    api_key = keys.get("volcengine_api_key", "")
    if not api_key:
        logger.error("No Volcengine API key")
        return ""

    prompt = _build_image_prompt(title, category)

    async with httpx.AsyncClient(timeout=httpx.Timeout(60)) as c:
        resp = await c.post(
            f"{ARK_BASE}/images/generations",
            json={
                "model": IMAGE_MODEL,
                "prompt": prompt,
                "size": "1080x1440",
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            logger.error(f"Image generation failed: {resp.status_code} {resp.text[:200]}")
            return ""

        data = resp.json()
        image_url = ""
        for d in data.get("data", []):
            image_url = d.get("url", "")
            if image_url:
                break

        if not image_url:
            logger.error(f"No image_url in response")
            return ""

        img_resp = await c.get(image_url)
        path = OUTPUT_DIR / f"{content_id}.png"
        path.write_bytes(img_resp.content)
        logger.info(f"Cover image generated: {path}")
        return str(path)


def _build_image_prompt(title: str, category: str = "") -> str:
    parts = [
        "A warm and inviting social media cover image for a parenting and child psychology article.",
        "Soft pastel color palette with gentle gradients, clean and minimal composition.",
        "The overall mood should be calming, trustworthy, and professional.",
        "No text, no letters, no numbers, no watermarks.",
        "Aspect ratio 3:4 portrait orientation.",
    ]
    if category:
        cat_visuals = {
            "情绪管理": "gentle flowing wave patterns or soft clouds",
            "学业心理": "abstract book and stationery elements in pastel blue",
            "人际关系": "two soft overlapping circles representing connection",
            "自我成长": "a growing plant or tree silhouette with soft light",
            "行为习惯": "clean abstract clock or daily routine elements",
            "青春期心理": "butterfly silhouette with soft pink and purple tones",
            "家庭教育": "warm house-shaped light glow with soft edges",
            "心理危机": "a single light beam breaking through soft gray gradient",
        }
        visual = cat_visuals.get(category, "soft abstract shapes")
        parts.append(f"Visual motif: {visual}.")
    return " ".join(parts)


async def generate_all(items: list[dict]) -> list[str]:
    paths = []
    for item in items:
        cid = item.get("id", "")[:8]
        title = item.get("xhs_title", "") or item.get("title", "")
        cat = item.get("topic_category", "")
        path = await generate_cover(cid, title, cat)
        if path:
            paths.append(path)
    return paths
