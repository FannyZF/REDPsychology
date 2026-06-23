from pathlib import Path
import textwrap

from src.utils.logger import get_logger

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).parent.parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "thumbnails"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

WIDTH, HEIGHT = 1080, 1440


def generate_cover(content_id: str, title: str, category: str = "",
                   color: str = "#4A90D9") -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("Pillow not installed. Run: pip install Pillow")
        return ""

    img = Image.new("RGB", (WIDTH, HEIGHT), color)
    draw = ImageDraw.Draw(img)

    font_large = _get_font(60)
    font_small = _get_font(36)

    if font_large:
        wrapped = textwrap.fill(title, width=18)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font_large)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (WIDTH - tw) // 2
        y = (HEIGHT - th) // 2 - 40
        draw.multiline_text((x, y), wrapped, fill="white", font=font_large,
                            align="center", spacing=20)

    if font_small and category:
        cat_text = f"—— {category} ——"
        bbox = draw.textbbox((0, 0), cat_text, font=font_small)
        cw = bbox[2] - bbox[0]
        draw.text(((WIDTH - cw) // 2, HEIGHT - 120), cat_text,
                  fill="rgba(255,255,255,180)", font=font_small)

    path = OUTPUT_DIR / f"{content_id}.png"
    img.save(str(path), "PNG")
    logger.info(f"Cover generated: {path}")
    return str(path)


def _get_font(size: int):
    import platform
    candidates = []
    if platform.system() == "Windows":
        candidates = [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
        ]
    elif platform.system() == "Darwin":
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
        ]
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


COLORS = [
    "#4A90D9", "#7B68EE", "#2E86AB", "#A23B72",
    "#F18F01", "#C73E1D", "#3B1F2B", "#1B998B",
]


def generate_all(items: list[dict]) -> list[str]:
    paths = []
    for i, item in enumerate(items):
        cid = item.get("id", "")[:8]
        title = item.get("xhs_title", "") or item.get("title", "")
        cat = item.get("topic_category", "")
        color = COLORS[i % len(COLORS)]
        path = generate_cover(cid, title, cat, color)
        if path:
            paths.append(path)
    return paths
