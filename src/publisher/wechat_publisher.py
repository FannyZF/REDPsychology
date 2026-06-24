import json
import time
import httpx

from src.utils.logger import get_logger

logger = get_logger(__name__)

WECHAT_API = "https://api.weixin.qq.com"

_cache = {
    "token": "",
    "expires_at": 0,
}


def _get_token(appid: str, secret: str) -> str:
    now = time.time()
    if _cache["token"] and _cache["expires_at"] > now + 60:
        return _cache["token"]

    for url in [
        f"{WECHAT_API}/cgi-bin/token?grant_type=client_credential&appid={appid}&secret={secret}",
        f"{WECHAT_API}/cgi-bin/stable_token",
    ]:
        try:
            if "stable" in url:
                resp = httpx.post(url, json={"grant_type": "client_credential", "appid": appid, "secret": secret}, timeout=15)
            else:
                resp = httpx.get(url, timeout=15)
            data = resp.json()
            token = data.get("access_token", "")
            if token:
                expires = data.get("expires_in", 7200)
                _cache["token"] = token
                _cache["expires_at"] = now + expires - 300
                logger.info(f"WeChat token obtained, expires in {expires}s")
                return token
            logger.warning(f"WeChat token failed ({'stable' if 'stable' in url else 'normal'}): {data}")
        except Exception as e:
            logger.error(f"WeChat token request error: {e}")

    return ""


def upload_cover(token: str, image_path: str) -> str:
    """Upload cover image as permanent material, return media_id"""
    # Step 1: Upload as permanent image material
    with open(image_path, "rb") as f:
        resp = httpx.post(
            f"{WECHAT_API}/cgi-bin/material/add_material",
            params={"access_token": token, "type": "image"},
            files={"media": f},
            timeout=30,
        )
    data = resp.json()
    media_id = data.get("media_id", "")
    if media_id:
        logger.info(f"WeChat cover uploaded, media_id: {media_id}")
        return media_id
    
    # Fallback: try uploadimg (returns url, but draft API needs media_id)
    logger.warning(f"add_material failed: {data}, trying uploadimg...")
    with open(image_path, "rb") as f:
        resp = httpx.post(
            f"{WECHAT_API}/cgi-bin/media/uploadimg",
            params={"access_token": token},
            files={"media": f},
            timeout=30,
        )
    data = resp.json()
    url = data.get("url", "")
    if url:
        logger.info(f"WeChat image URL: {url}")
        return url
    
    logger.error(f"WeChat image upload failed: {data}")
    return ""


def add_draft(token: str, title: str, content: str, cover_url: str, digest: str = "") -> str:
    """Add draft to WeChat draft box, return media_id"""
    article = {
        "title": title,
        "content": content,
        "content_source_url": "",
        "thumb_media_id": cover_url,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
        "digest": digest or content[:100],
    }
    body = {"articles": [article]}
    resp = httpx.post(
        f"{WECHAT_API}/cgi-bin/draft/add",
        params={"access_token": token},
        json=body,
        timeout=15,
    )
    data = resp.json()
    media_id = data.get("media_id", "")
    if media_id:
        logger.info(f"WeChat draft created: {media_id}")
    else:
        logger.error(f"WeChat draft failed: {data}")
        return {"error": f"草稿创建失败: {data.get('errmsg', str(data))}"}


def submit_publish(token: str, media_id: str) -> str:
    """Submit draft for publishing, return publish_id"""
    resp = httpx.post(
        f"{WECHAT_API}/cgi-bin/freepublish/submit",
        params={"access_token": token},
        json={"media_id": media_id},
        timeout=15,
    )
    data = resp.json()
    publish_id = data.get("publish_id", "")
    if publish_id:
        logger.info(f"WeChat publish submitted: {publish_id}")
    else:
        logger.error(f"WeChat publish failed: {data}")
    return publish_id


def publish_article(title: str, content: str, cover_path: str,
                    appid: str, secret: str, digest: str = "") -> dict:
    """Returns {"status": "ok"} or {"error": "message"}"""
    token = _get_token(appid, secret)
    if not token:
        return {"error": "获取微信token失败"}

    cover_url = upload_cover(token, cover_path)
    if not cover_url:
        return {"error": "上传封面图片失败"}

    media_id = add_draft(token, title, content, cover_url, digest)
    if isinstance(media_id, dict):
        return media_id
    if not media_id:
        return {"error": "创建草稿失败"}

    publish_id = submit_publish(token, media_id)
    if not publish_id:
        return {"error": "发布提交失败"}
    
    return {"status": "ok", "publish_id": publish_id}
