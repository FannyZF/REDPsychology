import asyncio
import subprocess
import tempfile
import os
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class EdgeTTSClient:
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural"):
        self.voice = voice

    async def synthesize(self, text: str, output_path: str,
                         speed: str = "-5%") -> tuple[str, float]:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                          encoding="utf-8", delete=False) as f:
            f.write(text)
            text_file = f.name

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["edge-tts", "--voice", self.voice, "--rate", speed,
                     "--file", text_file, "--write-media", str(path.resolve())],
                    capture_output=True, text=True, timeout=60,
                ),
            )
            if result.returncode != 0:
                logger.warning(f"edge-tts code {result.returncode}")
            dur = _get_audio_duration(str(path.resolve()))
            if dur > 0:
                logger.info(f"Edge-TTS: {path.name} ({dur:.1f}s)")
            return str(path.resolve()), dur
        except FileNotFoundError:
            logger.error("edge-tts not installed")
            return "", 0.0
        except Exception as e:
            logger.error(f"TTS error: {e}")
            return "", 0.0
        finally:
            try:
                os.unlink(text_file)
            except Exception:
                pass


def _get_audio_duration(path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        pass

    try:
        from pathlib import Path as P
        sz = P(path).stat().st_size
        with open(path, "rb") as f:
            for _ in range(100):
                h = f.read(4)
                if len(h) < 4:
                    return 0.0
                if h[0] == 0xFF and (h[1] & 0xE0) == 0xE0:
                    br_map = {9: 128000, 11: 192000, 13: 256000, 14: 320000}
                    br = br_map.get((h[2] >> 4) & 0x0F, 128000)
                    sr_map = {0: 44100, 1: 48000, 2: 32000}
                    sr = sr_map.get((h[2] >> 2) & 0x03, 44100)
                    spf = 1152
                    frame_size = 144 * br // sr if sr > 0 else 417
                    return sz / max(frame_size, 1) * spf / sr
                return 0.0
    except Exception:
        return 0.0
    return 0.0
