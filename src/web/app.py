import asyncio
import json
import yaml
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from jinja2 import Environment, FileSystemLoader

from src.storage.db import ContentStore
from src.storage.models import ContentItem
from src.utils.logger import get_logger
from src.utils.key_store import load as load_keys, update as update_key
from src.utils.config_store import load as load_schedule_config, update as update_schedule_config

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).parent.parent.parent
TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="心语视界 - 管理后台")
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), auto_reload=True)
store = ContentStore()


def render(name: str, context: dict, request: Request | None = None) -> HTMLResponse:
    ctx = dict(context)
    ctx["request"] = request or {}
    template = jinja_env.get_template(name)
    return HTMLResponse(template.render(ctx))


def load_yaml_config() -> dict:
    config_path = ROOT_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def save_yaml_config(config: dict):
    config_path = ROOT_DIR / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# === Pages ===

@app.get("/", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    stats = store.get_stats()
    pending = [i.model_dump() for i in store.list_all(status="pending", limit=10)]
    queue = [i.model_dump() for i in store.get_publish_queue(limit=5)]
    return render("dashboard.html.j2", {
        "stats": stats.model_dump(), "pending": pending, "queue": queue
    }, request)


@app.get("/content", response_class=HTMLResponse)
async def page_content_list(request: Request, status: str = "", page: int = 1):
    per_page = 20
    offset = (page - 1) * per_page
    items = [i.model_dump() for i in store.list_all(status=status, limit=per_page, offset=offset)]
    total = store.get_stats().total
    return render("content_list.html.j2", {
        "items": items, "status_filter": status,
        "page": page, "per_page": per_page, "total": total,
    }, request)


@app.get("/content/{item_id}", response_class=HTMLResponse)
async def page_content_detail(request: Request, item_id: str):
    item = store.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    item_dict = item.model_dump()
    points = []
    tags = []
    audience = []
    if item.core_points:
        try: points = json.loads(item.core_points)
        except json.JSONDecodeError: pass
    if item.xhs_tags:
        try: tags = json.loads(item.xhs_tags)
        except json.JSONDecodeError: pass
    if item.target_audience:
        try: audience = json.loads(item.target_audience)
        except json.JSONDecodeError: pass
    return render("content_detail.html.j2", {
        "item": item_dict, "points": points, "tags": tags, "audience": audience,
    }, request)


@app.get("/sources", response_class=HTMLResponse)
async def page_sources(request: Request):
    config = load_yaml_config()
    sources = config.get("sources", [])
    return render("sources.html.j2", {"sources": sources}, request)


@app.get("/video", response_class=HTMLResponse)
async def page_video(request: Request):
    items = [i.model_dump() for i in store.list_all(status="video_generated", limit=20)]
    return render("video.html.j2", {"items": items}, request)


@app.get("/publish", response_class=HTMLResponse)
async def page_publish(request: Request):
    queue = [i.model_dump() for i in store.get_publish_queue(limit=10)]
    published = [i.model_dump() for i in store.list_all(limit=50) if i.publish_status == "published"][:20]
    return render("publish.html.j2", {"queue": queue, "published": published}, request)


@app.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    keys = load_keys()
    schedule = load_schedule_config()
    time_fields = {}
    for prefix in ["collect", "process", "video", "publish"]:
        h = schedule.get(f"{prefix}_hour", 0)
        m = schedule.get(f"{prefix}_minute", 0)
        time_fields[f"{prefix}_time"] = f"{h:02d}:{m:02d}"
    # Also load from config.yaml for video.enabled
    try:
        import yaml
        cfg = load_yaml_config()
        schedule["video_enabled"] = cfg.get("video", {}).get("enabled", True)
    except Exception:
        pass
    return render("settings.html.j2", {
        "keys": keys, "schedule": schedule, "time": time_fields,
    }, request)


@app.get("/login", response_class=HTMLResponse)
async def page_login(request: Request):
    return render("login.html.j2", {}, request)


@app.post("/api/login/qrcode")
async def api_login_qrcode():
    import threading, time
    from src.publisher.selenium_publisher import XiaohongshuPublisher
    from selenium.webdriver.common.by import By

    def _capture():
        xhs = XiaohongshuPublisher(headless=True)
        try:
            xhs.start()
            xhs.driver.get("https://creator.xiaohongshu.com/login")
            time.sleep(5)
            ss = Path(ROOT_DIR / "output" / "screenshots" / "login_qr.png")
            ss.parent.mkdir(parents=True, exist_ok=True)

            # Try multiple strategies to get just the QR code
            qr_selectors = [
                "//img[contains(@src,'qrcode') or contains(@src,'qr')]",
                "//canvas",
                "//div[contains(@class,'qrcode') or contains(@class,'qr')]//img",
                "//div[contains(@class,'qrcode') or contains(@class,'qr')]//canvas",
                "//*[contains(@class,'login')]//img",
                "//*[contains(@class,'login')]//canvas",
            ]
            found = False
            for sel in qr_selectors:
                try:
                    el = xhs.driver.find_element(By.XPATH, sel)
                    el.screenshot(str(ss))
                    logger.info(f"QR captured via: {sel}")
                    found = True
                    break
                except Exception:
                    continue

            if not found:
                # Take full screenshot and crop center (QR usually centered)
                from PIL import Image
                full = Path(ROOT_DIR / "output" / "screenshots" / "login_full.png")
                xhs.driver.save_screenshot(str(full))
                img = Image.open(full)
                W, H = img.size
                # Crop center 50% (QR typically in the middle third)
                left, top = int(W * 0.25), int(H * 0.2)
                right, bottom = int(W * 0.75), int(H * 0.7)
                cropped = img.crop((left, top, right, bottom))
                cropped.save(str(ss))
                logger.info("QR captured via center crop")

            logger.info("QR captured, waiting for scan...")

            for i in range(60):
                time.sleep(2)
                try:
                    xhs.driver.get("https://creator.xiaohongshu.com")
                    xhs.driver.find_element("xpath", "//*[contains(text(), '发布笔记')]")
                    logger.info("Login successful via QR scan!")
                    xhs.driver.save_screenshot(str(ss))
                    break
                except Exception:
                    if i % 5 == 0:
                        logger.info(f"Waiting for scan... ({(i+1)*2}s)")
        except Exception as e:
            logger.error(f"QR failed: {e}")
        finally:
            xhs.close()

    threading.Thread(target=_capture, daemon=True).start()
    return {"status": "capturing"}


@app.get("/api/login/qrcode-image")
async def api_login_qrcode_image():
    from fastapi.responses import FileResponse
    ss = Path(ROOT_DIR / "output" / "screenshots" / "login_qr.png")
    if not ss.exists():
        raise HTTPException(404, "QR not ready yet, retry in a few seconds")
    return FileResponse(str(ss), media_type="image/png")


@app.get("/api/login/check")
async def api_login_check():
    import threading
    try:
        from src.publisher.selenium_publisher import XiaohongshuPublisher
        result = {"logged_in": False}

        def _check():
            xhs = XiaohongshuPublisher(headless=True)
            try:
                xhs.start()
                xhs.driver.get("https://creator.xiaohongshu.com")
                import time; time.sleep(2)
                try:
                    xhs.driver.find_element("xpath", "//*[contains(text(), '发布笔记')]")
                    result["logged_in"] = True
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                xhs.close()

        t = threading.Thread(target=_check, daemon=True)
        t.start()
        t.join(timeout=15)
        return result
    except Exception as e:
        return {"logged_in": False, "error": str(e)}


@app.get("/api/content/{item_id}/video")
async def api_video_file(item_id: str):
    item = store.get_by_id(item_id)
    if not item or not item.video_path:
        raise HTTPException(404)
    path = Path(item.video_path)
    if not path.exists():
        raise HTTPException(404)
    if path.suffix == '.png':
        return FileResponse(str(path), media_type="image/png")
    return FileResponse(str(path), media_type="video/mp4")


# === API Endpoints ===

@app.get("/api/stats")
async def api_stats():
    return store.get_stats().model_dump()


@app.get("/api/content")
async def api_content(status: str = "", limit: int = 50, offset: int = 0):
    items = store.list_all(status=status, limit=limit, offset=offset)
    return {"items": [i.model_dump() for i in items], "total": len(items)}


@app.post("/api/pipeline/collect")
async def api_collect():
    from src.collector.orchestrator import collect_all
    try:
        result = await collect_all()
        return result
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/pipeline/process")
async def api_process():
    from src.processor.llm_client import LLMClient
    from src.processor.pipeline import ProcessingPipeline
    pending = store.get_pending(limit=50)
    if not pending:
        return {"success": 0, "message": "No pending items"}
    client = LLMClient()
    pipeline = ProcessingPipeline(client, store)
    result = await pipeline.process_batch(pending)
    return result


@app.post("/api/pipeline/video")
async def api_video():
    from src.video_generator.composer import generate_all
    result = await generate_all(store, max_count=3)
    return result


@app.post("/api/pipeline/run")
async def api_run():
    from src.scheduler.daily_pipeline import DailyPipeline
    import threading
    def _run():
        DailyPipeline().run_full()
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}


@app.post("/api/content/{item_id}/reprocess")
async def api_reprocess(item_id: str):
    from src.processor.llm_client import LLMClient
    from src.processor.pipeline import ProcessingPipeline
    item = store.get_by_id(item_id)
    if not item:
        raise HTTPException(404)
    item.status = "pending"
    store.insert(item)
    client = LLMClient()
    pipeline = ProcessingPipeline(client, store)
    await pipeline.process_single(item)
    return {"status": "ok"}


@app.post("/api/content/{item_id}/revideo")
async def api_revideo(item_id: str):
    from src.video_generator.composer import VideoComposer
    from src.video_generator.client import VolcengineVideoClient
    item = store.get_by_id(item_id)
    if not item:
        raise HTTPException(404)
    client = VolcengineVideoClient()
    composer = VideoComposer(client)
    path = await composer.generate(item)
    if path:
        from src.video_generator.composer import _get_video_duration
        dur = _get_video_duration(path)
        store.update_video_status(item_id, path, dur)
        return {"status": "ok", "path": path}
    return {"status": "failed"}


@app.delete("/api/content/{item_id}")
async def api_delete(item_id: str):
    store.delete(item_id)
    return {"status": "deleted"}


@app.post("/api/publish/{item_id}")
async def api_publish_single(item_id: str):
    from src.publisher.selenium_publisher import XiaohongshuPublisher
    from src.publisher.publish_service import ContentPublisher
    item = store.get_by_id(item_id)
    if not item:
        raise HTTPException(404)
    xhs = XiaohongshuPublisher(headless=True)
    publisher = ContentPublisher(xhs, store)
    try:
        xhs.start()
        if xhs.ensure_login():
            publisher.publish_one(item)
            return {"status": "published"}
        return {"status": "login_failed"}
    finally:
        xhs.close()


@app.put("/api/settings/api_key")
async def api_update_key(data: dict):
    for k, v in data.items():
        update_key(k, v)


@app.put("/api/settings/schedule")
async def api_update_schedule(data: dict):
    for k, v in data.items():
        update_schedule_config(k, v)


@app.post("/api/sources/detect")
async def api_detect_source(data: dict):
    from src.collector.selector_detect import detect_selectors
    url = data.get("url", "")
    if not url:
        raise HTTPException(400, "url required")
    result = await detect_selectors(url)
    return result or {}


@app.post("/api/sources/add")
async def api_add_source(data: dict):
    config = load_yaml_config()
    sources = config.get("sources", [])
    sources.append(data)
    config["sources"] = sources
    save_yaml_config(config)


@app.delete("/api/sources/{index}")
async def api_delete_source(index: int):
    config = load_yaml_config()
    sources = config.get("sources", [])
    if 0 <= index < len(sources):
        sources.pop(index)
        config["sources"] = sources
        save_yaml_config(config)


@app.put("/api/sources/{index}/toggle")
async def api_toggle_source(index: int):
    config = load_yaml_config()
    sources = config.get("sources", [])
    if 0 <= index < len(sources):
        sources[index]["enabled"] = not sources[index].get("enabled", True)
        save_yaml_config(config)


@app.get("/api/settings/keywords")
async def api_get_keywords():
    from src.utils.keyword_store import load as load_kw
    return {"keywords": load_kw()}


@app.put("/api/settings/keywords")
async def api_update_keywords(data: dict):
    from src.utils.keyword_store import update as update_kw
    update_kw(data.get("keywords", []))


@app.post("/api/settings/keywords/reset")
async def api_reset_keywords():
    from src.utils.keyword_store import reset
    reset()
    return {"status": "reset"}


@app.get("/api/trending/status")
async def api_trending_status():
    from src.processor.trend_booster import load_boosts, get_all_active_boosts, expire_old_boosts
    boosts = load_boosts()
    boosts = expire_old_boosts(boosts)
    active = get_all_active_boosts()
    sorted_active = sorted(active.items(), key=lambda x: x[1], reverse=True)[:20]
    return {
        "total_keywords": len(boosts),
        "active_boosts": [{"keyword": k, "boost": v} for k, v in sorted_active],
    }


@app.post("/api/trending/collect")
async def api_collect_trending():
    from src.collector.trending import collect_trending_from_newsnow
    from src.processor.trend_booster import merge_trending
    counts = await collect_trending_from_newsnow()
    merge_trending(counts)
    return {"keywords_collected": len(counts)}


@app.post("/api/trending/clear")
async def api_clear_trending():
    from src.processor.trend_booster import save_boosts
    save_boosts({})
    return {"status": "cleared"}


@app.get("/api/pipeline/score")
async def api_score_preview():
    from src.processor.scorer import score_content
    from src.utils.keyword_store import load as load_kw
    kw_config = load_kw()
    processed = store.get_processed(limit=50)
    if not processed:
        return {"items": []}
    scored = [(score_content(it, kw_config), it.model_dump()) for it in processed]
    scored.sort(key=lambda x: x[0], reverse=True)
    return {"items": [{"score": s, "id": it["id"][:8], "title": it["title"][:60]} for s, it in scored[:10]]}
