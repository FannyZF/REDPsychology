from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TTSClient:
    def __init__(self, lang: str = "zh-CN", tld: str = "com"):
        self.lang = lang
        self.tld = tld

    async def synthesize(self, text: str, output_path: str) -> tuple[str, float]:
        import asyncio
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._sync_synthesize, text, str(path.resolve()))
            dur = self._get_mp3_duration(str(path.resolve()))
            if dur > 0:
                logger.info(f"gTTS: {path.name} ({dur:.1f}s)")
            return str(path.resolve()), dur
        except Exception as e:
            logger.error(f"gTTS error: {e}")
            return "", 0.0

    def _sync_synthesize(self, text: str, output_path: str):
        from gtts import gTTS
        tts = gTTS(text=text, lang=self.lang, tld=self.tld, slow=False)
        tts.save(output_path)

    @staticmethod
    def _get_mp3_duration(path: str) -> float:
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=10,
            )
            return float(result.stdout.strip())
        except Exception:
            pass
        try:
            sz = Path(path).stat().st_size
            with open(path, "rb") as f:
                for _ in range(100):
                    h = f.read(4)
                    if len(h) < 4:
                        return 0.0
                    if h[0] == 0xFF and (h[1] & 0xE0) == 0xE0:
                        br = 128000
                        sr = 44100
                        return sz * 8 / br * 0.95 if br > 0 else 0.0
        except Exception:
            pass
        return 0.0
