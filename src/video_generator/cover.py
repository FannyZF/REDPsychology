import httpx
import textwrap
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
                "watermark": False,
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
            logger.error("No image_url in response")
            return ""

        img_resp = await c.get(image_url)
        raw_path = OUTPUT_DIR / f"{content_id}_raw.png"
        raw_path.write_bytes(img_resp.content)

        # Overlay title text on image
        final_path = OUTPUT_DIR / f"{content_id}.png"
        _add_title_text(str(raw_path), str(final_path), title)
        raw_path.unlink(missing_ok=True)

        logger.info(f"Cover generated: {final_path}")
        return str(final_path)


def _build_image_prompt(title: str, category: str = "") -> str:
    parts = [
        "A warm and inviting social media cover image for a parenting and child psychology article.",
        "Soft pastel color palette with gentle gradients, clean and minimal composition.",
        "The overall mood should be calming, trustworthy, and professional.",
        "Leave the center area relatively clean for text overlay.",
        "No text, no letters, no numbers, no watermarks.",
        "Aspect ratio 3:4 portrait orientation.",
    ]
    if category:
        cat_visuals = {
            "情绪管理": "gentle flowing wave patterns or soft clouds at the edges",
            "学业心理": "abstract book and stationery elements in pastel blue at edges",
            "人际关系": "two soft overlapping circles at the top representing connection",
            "自我成长": "a growing plant or tree silhouette with soft light at the bottom",
            "行为习惯": "clean abstract clock or daily routine elements at edges",
            "青春期心理": "butterfly silhouette with soft pink and purple tones at the top",
            "家庭教育": "warm house-shaped light glow with soft edges at the bottom",
            "心理危机": "a single light beam from top corner with soft gray background",
        }
        visual = cat_visuals.get(category, "soft abstract shapes at the edges")
        parts.append(f"Visual motif: {visual}.")
    return " ".join(parts)


def _add_title_text(input_path: str, output_path: str, title: str):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        import shutil
        shutil.copy(input_path, output_path)
        return

    img = Image.open(input_path)
    W, H = img.size

    # Crop bottom 60px to remove potential watermark
    img = img.crop((0, 0, W, H - 60))

    draw = ImageDraw.Draw(img)
    font = _get_font(56)

    if font:
        # Semi-transparent dark overlay bar behind text
        overlay = Image.new("RGBA", (W, 300), (0, 0, 0, 100))
        bar_y = (H - 60) // 2 - 150
        img.paste(overlay, (0, bar_y), overlay)

        wrapped = textwrap.fill(title, width=16)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        y = bar_y + 150 - (bbox[3] - bbox[1]) // 2
        draw.multiline_text((x, y), wrapped, fill="white", font=font,
                            align="center", spacing=16)

    img.save(output_path, "PNG")


def _get_font(size: int):
    import platform
    candidates = []
    if platform.system() == "Windows":
        candidates = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]
    elif platform.system() == "Darwin":
        candidates = ["/System/Library/Fonts/PingFang.ttc"]
    else:
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        ]
    try:
        from PIL import ImageFont
        for c in candidates:
            if Path(c).exists():
                return ImageFont.truetype(c, size)
    except Exception:
        pass
    try:
        from PIL import ImageFont
        return ImageFont.truetype(size=size)
    except Exception:
        return None


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
