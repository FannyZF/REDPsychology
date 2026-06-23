import asyncio
from pathlib import Path

import httpx

from src.utils.logger import get_logger
from src.utils.key_store import load as load_keys

logger = get_logger(__name__)

ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
GENERATE_URL = f"{ARK_BASE}/contents/generations/tasks"
DEFAULT_MODEL = "doubao-seedance-1-0-pro-fast-251015"


class VolcengineVideoClient:
    def __init__(self, api_key: str = "", model: str = ""):
        keys = load_keys()
        self.api_key = api_key or keys.get("volcengine_api_key", "")
        self.model = model or self._load_model_from_config()

    @staticmethod
    def _load_model_from_config() -> str:
        try:
            import yaml
            from pathlib import Path
            config_path = Path(__file__).parent.parent.parent / "config.yaml"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                return cfg.get("video", {}).get("model", DEFAULT_MODEL)
        except Exception:
            pass
        return DEFAULT_MODEL

    async def text_to_video(
        self, prompt: str, duration: int = 12, aspect_ratio: str = "9:16",
        generate_audio: bool = True,
    ) -> str:
        body = {
            "model": self.model,
            "content": [{"type": "text", "text": prompt}],
            "generate_audio": generate_audio,
            "ratio": aspect_ratio,
            "duration": duration,
            "watermark": False,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
            resp = await client.post(
                GENERATE_URL,
                json=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.error(f"Video task submit failed: {resp.status_code} {resp.text[:300]}")
                return ""
            data = resp.json()
            task_id = data.get("id") or data.get("task_id", "")
            if not task_id:
                logger.error(f"No task_id in response: {data}")
                return ""
            logger.info(f"Video task submitted: {task_id}")
            return task_id

    async def query_task(self, task_id: str) -> dict:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
            resp = await client.get(
                f"{ARK_BASE}/contents/generations/tasks/{task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if resp.status_code != 200:
                return {"status": "failed"}
            return resp.json()

    async def wait_for_completion(
        self, task_id: str, timeout: int = 600, poll_interval: int = 10
    ) -> str:
        elapsed = 0
        while elapsed < timeout:
            data = await self.query_task(task_id)
            status = str(data.get("status", "")).lower()

            if status in ("completed", "succeeded", "success", "done"):
                video_url = data.get("video_url", "")
                if not video_url:
                    content = data.get("content", {})
                    if isinstance(content, dict):
                        video_url = content.get("video_url", "")
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "video_url":
                                video_url = c.get("video_url", {}).get("url", "")
                                break
                if video_url:
                    logger.info(f"Video task completed: {task_id[:12]}")
                    return video_url
                logger.error(f"No video_url in completed response: {str(data)[:200]}")

            if status in ("failed", "error", "cancelled"):
                logger.error(f"Video task failed: {data.get('error', '')}")
                return ""

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            if elapsed % 30 == 0:
                logger.info(f"Waiting for video... ({elapsed}s, status={status})")

        logger.error(f"Video task timed out after {timeout}s")
        return ""

    async def download_video(self, video_url: str, output_path: str) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120)) as client:
            resp = await client.get(video_url)
            resp.raise_for_status()
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(resp.content)
            size = Path(output_path).stat().st_size
            if size == 0:
                logger.error("Downloaded video is empty")
                return ""
            logger.info(f"Video downloaded: {output_path} ({size} bytes)")
            return output_path

    async def generate(self, prompt: str, output_path: str,
                       duration: int = 15, aspect_ratio: str = "9:16",
                       timeout: int = 600) -> str:
        task_id = await self.text_to_video(prompt, duration, aspect_ratio)
        if not task_id:
            return ""

        video_url = await self.wait_for_completion(task_id, timeout)
        if not video_url:
            return ""

        return await self.download_video(video_url, output_path)
