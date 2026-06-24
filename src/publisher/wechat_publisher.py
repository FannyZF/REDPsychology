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

    resp = httpx.post(
        f"{WECHAT_API}/cgi-bin/stable_token",
        json={"grant_type": "client_credential", "appid": appid, "secret": secret},
        timeout=15,
    )
    data = resp.json()
    token = data.get("access_token", "")
    expires = data.get("expires_in", 7200)
    _cache["token"] = token
    _cache["expires_at"] = now + expires - 300
    logger.info(f"WeChat token obtained, expires in {expires}s")
    return token


def upload_cover(token: str, image_path: str) -> str:
    """Upload cover image, return media_id (not url, but for draft use)"""
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
        logger.info(f"WeChat image uploaded: {url}")
    else:
        logger.error(f"WeChat image upload failed: {data}")
    return url


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
    return media_id


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
                    appid: str, secret: str, digest: str = "") -> bool:
    """Complete publish flow: upload cover -> add draft -> publish"""
    token = _get_token(appid, secret)
    if not token:
        return False

    cover_url = upload_cover(token, cover_path)
    if not cover_url:
        return False

    media_id = add_draft(token, title, content, cover_url, digest)
    if not media_id:
        return False

    publish_id = submit_publish(token, media_id)
    return bool(publish_id)
