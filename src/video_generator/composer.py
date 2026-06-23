import asyncio
import asyncio
import json
import os
import subprocess
import platform
from pathlib import Path

from src.video_generator.client import VolcengineVideoClient
from src.video_generator.tts_client import EdgeTTSClient
from src.video_generator.template import build_video_prompt, get_music
from src.storage.models import ContentItem
from src.storage.db import ContentStore
from src.utils.logger import get_logger

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).parent.parent.parent
OUTPUT_DIR = ROOT_DIR / "output"
VIDEO_DIR = OUTPUT_DIR / "videos"
SUBTITLE_DIR = OUTPUT_DIR / "subtitles"
ASSETS_DIR = ROOT_DIR / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
TEMPLATES_DIR = ASSETS_DIR / "templates"

import platform
if platform.system() == "Windows":
    FONT_NAME = "Microsoft YaHei"
elif platform.system() == "Darwin":
    FONT_NAME = "PingFang SC"
else:
    FONT_NAME = "Noto Sans CJK SC"

try: VIDEO_DIR.mkdir(parents=True, exist_ok=True)
except OSError: pass
try: SUBTITLE_DIR.mkdir(parents=True, exist_ok=True)
except OSError: pass
# MUSIC_DIR created in Dockerfile
# TEMPLATES_DIR created in Dockerfile


def _build_ass(content_id: str, title: str, core_points: list[str],
               duration: float = 15.0,
               segment_durations: list[float] | None = None) -> str:
    n = len(core_points)
    title_end = min(1.8, duration * 0.12)

    if segment_durations and len(segment_durations) == n:
        point_durations = segment_durations
    else:
        default_dur = (duration - title_end - 1.5) / max(n, 1)
        point_durations = [default_dur] * n

    gap = max(0.0, (duration - title_end - sum(point_durations) - 1.5) / max(n + 1, 1))
    cursor = title_end
    for pd in point_durations:
        cursor += pd + gap
    end_start = cursor + gap

    ass_path = SUBTITLE_DIR / f"{content_id}.ass"
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: None",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Title,{FONT_NAME},80,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,1,0,0,0,100,100,6,0,4,0,0,5,120,120,0,1",
        f"Style: Point,{FONT_NAME},64,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,1,0,0,0,100,100,6,0,4,0,0,5,160,160,0,1",
        f"Style: Gold,{FONT_NAME},64,&H0000DDFF,&H000000FF,&H00000000,&HA0000000,1,0,0,0,100,100,6,0,4,0,0,5,160,160,0,1",
        f"Style: Bar,{FONT_NAME},46,&H00CCCCCC,&H000000FF,&H00000000,&HA0000000,1,0,0,0,100,100,4,0,4,0,0,5,120,120,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    # Title card - auto-wrap to 2 lines if needed
    safe_title = title.replace(",", "，").replace("\n", " ")
    if len(safe_title) > 12:
        safe_title = f"{safe_title[:len(safe_title)//2]}\\N{safe_title[len(safe_title)//2:]}"
    lines.append(
        f"Dialogue: 0,0:00:00.00,{_sec_to_ass(title_end)},Title,,0,0,0,,{safe_title}"
    )

    # Core points with per-segment timing matching TTS
    cursor = title_end
    for i, point in enumerate(core_points):
        start_s = cursor
        pd = point_durations[i]
        cursor += pd + gap
        end_s = min(cursor, duration - 0.3)

        safe_point = _add_emphasis(point.replace(",", "，").replace("\n", " "))
        if len(safe_point) > 18:
            half = len(safe_point) // 2
            safe_point = f"{safe_point[:half]}\\N{safe_point[half:]}"
        lines.append(
            f"Dialogue: 0,{_sec_to_ass(start_s)},{_sec_to_ass(end_s)},Point,,0,0,0,,{safe_point}"
        )

    # End card
    if end_start < duration - 0.3:
        lines.append(
            f"Dialogue: 0,{_sec_to_ass(end_start)},{_sec_to_ass(duration)},Bar,,0,0,0,,"
            "关注我们，了解更多心理学知识"
        )

    content = "\n".join(lines)
    ass_path.write_text(content, encoding="utf-8")
    return str(ass_path)


def _add_emphasis(text: str) -> str:
    import re
    patterns = [
        (r"(\d+[\u4e00-\u9fff]*%)", r"{\\c&H0000DDFF&}\1{\\r}"),
        (r"(\d+\s*[分钟秒次天周月种个步])", r"{\\c&H0000DDFF&}\1{\\r}"),
        (r"([\u4e00-\u9fff]+法\b)", r"{\\c&H0000DDFF&}\1{\\r}"),
    ]
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result


def _sec_to_ass(seconds: float) -> str:
    total_cs = round(seconds * 100)
    h = total_cs // 360000
    m = (total_cs % 360000) // 6000
    s = (total_cs % 6000) // 100
    cs = total_cs % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _get_ffprobe() -> str:
    for c in [str(ROOT_DIR / "output" / "ffprobe.exe"), str(ROOT_DIR / "output" / "ffprobe"), "ffprobe"]:
        if c == "ffprobe" or Path(c).exists():
            return c
    return "ffprobe"


def _get_video_duration(path: str) -> int:
    try:
        cmd = [
            _get_ffprobe(), "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return int(float(result.stdout.strip()))
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        return 0


def _run_ffmpeg(cmd: list[str], description: str) -> bool:
    # Auto-detect ffmpeg binary location
    ffmpeg_bin = "ffmpeg"
    candidates = [
        str(ROOT_DIR / "output" / "ffmpeg.exe"),
        str(ROOT_DIR / "output" / "ffmpeg"),
        "ffmpeg",
    ]
    for c in candidates:
        if c == "ffmpeg" or Path(c).exists():
            ffmpeg_bin = c
            break
    cmd[0] = ffmpeg_bin
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"FFmpeg {description} failed: {result.stderr[:300]}")
            return False
        logger.info(f"FFmpeg {description} done")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"FFmpeg {description} timed out")
        return False
    except FileNotFoundError:
        logger.error("FFmpeg not found. Install with: apt install ffmpeg")
        return False


class VideoComposer:
    def __init__(self, video_client: VolcengineVideoClient | None = None):
        self.video_client = video_client

    async def generate(self, content: ContentItem, template_name: str = "清新治愈",
                       duration: int = 15) -> str:
        content_id = content.id[:8]
        logger.info(f"Generating video for {content_id} ({template_name})")

        core_points = []
        if content.core_points:
            try:
                core_points = json.loads(content.core_points)
            except json.JSONDecodeError:
                core_points = []

        if not core_points:
            logger.error(f"No core points for {content_id}")
            return ""

        if not self.video_client:
            logger.info(f"No video client configured, skipping API generation for {content_id}")
            return ""

        # Step 1: TTS narration with retry and rate-limit delay
        narration_segments = []
        total_narration_dur = 0.0
        actual_duration = float(duration)

        try:
            tts = EdgeTTSClient()
            for i, point in enumerate(core_points):
                seg_path = str(VIDEO_DIR / f"{content.id}_seg{i}.mp3")
                Path(seg_path).unlink(missing_ok=True)
                seg_dur = 0.0
                for attempt in range(4):
                    if attempt > 0:
                        await asyncio.sleep(4)
                    _, d = await tts.synthesize(point, seg_path)
                    seg_dur = d if d > 0 and Path(seg_path).stat().st_size > 1000 else 0.0
                    if seg_dur > 0:
                        break
                if seg_dur > 0:
                    narration_segments.append((seg_path, seg_dur))
                    total_narration_dur += seg_dur
                    logger.info(f"TTS seg {i}: {seg_dur:.1f}s (attempts={attempt+1})")
                else:
                    logger.warning(f"TTS seg {i} failed after {attempt+1} attempts")
                await asyncio.sleep(3)
        except Exception as e:
            logger.warning(f"TTS failed: {e}")

        # Fallback: single combined TTS
        if not narration_segments:
            try:
                combined = "。".join(core_points) + "。"
                combined_path = str(VIDEO_DIR / f"{content.id}_narration.mp3")
                Path(combined_path).unlink(missing_ok=True)
                _, tts_dur = await EdgeTTSClient().synthesize(combined, combined_path)
                if tts_dur > 0 and Path(combined_path).stat().st_size > 1000:
                    narration_segments = [(combined_path, tts_dur)]
                    total_narration_dur = tts_dur
                    logger.info(f"TTS combined: {tts_dur:.1f}s")
            except Exception as e:
                logger.warning(f"TTS fallback failed: {e}")

        if narration_segments:
            actual_duration = total_narration_dur + 2.5
            actual_duration = max(actual_duration, 10.0)
            actual_duration = min(actual_duration, 12.0)  # Seedance fast model max 12s
            logger.info(f"Video target duration: {actual_duration:.1f}s (TTS: {total_narration_dur:.1f}s)")

        # Step 2: Generate video at TTS-matched duration
        raw_path = str(VIDEO_DIR / f"{content.id}_raw.mp4")
        prompt = ""
        if hasattr(content, 'video_prompt') and content.video_prompt:
            prompt = content.video_prompt
        if not prompt:
            prompt = build_video_prompt(content, template_name, int(actual_duration))

        result = await self.video_client.generate(
            prompt=prompt,
            output_path=raw_path,
            duration=int(actual_duration),
            aspect_ratio="9:16",
            timeout=600,
        )
        if not result or not Path(raw_path).exists():
            logger.error(f"Video API generation failed for {content_id}")
            return ""

        # Step 3: Generate ASS subtitles with per-segment timing
        has_narration = bool(narration_segments)
        seg_durations = [d for _, d in narration_segments] if has_narration else None
        ass_path = _build_ass(
            content_id=content.id,
            title=content.xhs_title or content.title,
            core_points=core_points,
            duration=actual_duration,
            segment_durations=seg_durations,
        )

        # Step 4: Concat narration (if segmented) + composite
        final_path = str(VIDEO_DIR / f"{content.id}_final.mp4")
        music_file = _find_music(template_name)
        ass_path_abs = str(Path(ass_path).resolve().as_posix())

        if has_narration:
            if len(narration_segments) > 1:
                concat_list = str(VIDEO_DIR / f"{content.id}_concat.txt")
                narration_path = str(VIDEO_DIR / f"{content.id}_narration.mp3")
                with open(concat_list, "w") as f:
                    for seg_path, _ in narration_segments:
                        f.write(f"file '{Path(seg_path).resolve().as_posix()}'\n")
                _run_ffmpeg([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_list, "-c", "copy", narration_path,
                ], "concat narration")
            else:
                narration_path = narration_segments[0][0]
        else:
            narration_path = None

        if narration_path and Path(narration_path).exists():
            nar_abs = str(Path(narration_path).resolve().as_posix())
            # Calculate speed ratio: stretch video to match narration
            tts_dur = _get_video_duration(nar_abs)
            speed_ratio = tts_dur / actual_duration if actual_duration > 0 and tts_dur > actual_duration else 1.0
            if speed_ratio > 1.0:
                logger.info(f"Video speed adjusted: {speed_ratio:.2f}x (video={actual_duration:.0f}s, TTS={tts_dur:.0f}s)")
            if speed_ratio > 1.0:
                logger.info(f"Video speed adjusted: {speed_ratio:.2f}x (video={actual_duration:.0f}s, TTS={tts_dur:.0f}s)")
                if music_file and Path(music_file).exists():
                    music_abs = str(Path(music_file).resolve().as_posix())
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", raw_path,
                        "-i", nar_abs,
                        "-stream_loop", "-1",
                        "-i", music_abs,
                        "-filter_complex",
                        f"[0:v]setpts={speed_ratio}*PTS,subtitles='{ass_path_abs}'[v];"
                        f"[2:a]volume=0.12,afade=t=in:d=2,afade=t=out:st={actual_duration - 2}:d=2[a2];"
                        f"[1:a]volume=1.2[a1];"
                        f"[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[a]",
                        "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "128k",
                        "-t", str(actual_duration),
                        final_path,
                    ]
                else:
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", raw_path,
                        "-i", nar_abs,
                        "-filter_complex",
                        f"[0:v]setpts={speed_ratio}*PTS,subtitles='{ass_path_abs}'[v]",
                        "-map", "[v]", "-map", "1:a",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "128k",
                        "-t", str(actual_duration),
                        final_path,
                    ]
            elif music_file and Path(music_file).exists():
                music_abs = str(Path(music_file).resolve().as_posix())
                # No speed adjustment needed (video >= TTS)
                cmd = [
                    "ffmpeg", "-y",
                    "-i", raw_path,
                    "-i", nar_abs,
                    "-stream_loop", "-1",
                    "-i", music_abs,
                    "-vf", f"subtitles='{ass_path_abs}'",
                    "-filter_complex",
                    f"[2:a]volume=0.12,afade=t=in:d=2,afade=t=out:st={actual_duration - 2}:d=2[a2];"
                    f"[1:a]volume=1.2[a1];"
                    f"[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[a]",
                    "-map", "0:v",
                    "-map", "[a]",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-t", str(actual_duration),
                    final_path,
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-i", raw_path,
                    "-i", nar_abs,
                    "-vf", f"subtitles='{ass_path_abs}'",
                    "-map", "0:v",
                    "-map", "1:a",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-t", str(actual_duration),
                    final_path,
                ]
        elif music_file and Path(music_file).exists():
            music_abs = str(Path(music_file).resolve().as_posix())
            cmd = [
                "ffmpeg", "-y",
                "-i", raw_path,
                "-stream_loop", "-1",
                "-i", music_abs,
                "-vf", f"subtitles='{ass_path_abs}'",
                "-filter_complex",
                f"[1:a]volume=0.15,afade=t=in:d=2,afade=t=out:st={actual_duration - 2}:d=2[a2];"
                f"[0:a]volume=1.0[a1];"
                f"[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[a]",
                "-map", "0:v",
                "-map", "[a]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-t", str(actual_duration),
                final_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", raw_path,
                "-vf", f"subtitles='{ass_path_abs}'",
                "-map", "0:v",
                "-map", "0:a",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                final_path,
            ]

        if _run_ffmpeg(cmd, "final composite"):
            logger.info(f"Video complete: {final_path} ({actual_duration:.1f}s)")
            return final_path

        return raw_path


def _find_music(template_name: str) -> str:
    music_name = get_music(template_name)
    candidates = [
        MUSIC_DIR / f"{music_name}.wav",
        MUSIC_DIR / f"{music_name}.mp3",
        MUSIC_DIR / f"{music_name}.ogg",
        MUSIC_DIR / "light_piano.wav",
        MUSIC_DIR / "light_piano.mp3",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


async def generate_all(store: ContentStore, template_name: str = "清新治愈",
                       max_count: int = 3,
                       specific_items: list[ContentItem] | None = None) -> dict:
    from src.utils.key_store import load as load_keys
    keys = load_keys()
    volc_key = keys.get("volcengine_api_key", "")

    if not volc_key:
        logger.error("Volcengine API key not configured")
        return {"success": 0, "failed": 0, "error": "no_api_key"}

    client = VolcengineVideoClient()
    composer = VideoComposer(client)

    if specific_items is not None:
        items = specific_items
    else:
        items = store.get_processed(limit=max_count)

    if not items:
        logger.info("No processed items to generate videos for")
        return {"success": 0, "failed": 0}

    logger.info(f"Generating videos for {len(items)} items")
    success = 0
    failed = 0

    for item in items:
        try:
            final_path = await composer.generate(item, template_name)
            if final_path:
                duration = _get_video_duration(final_path)
                store.update_video_status(item.id, final_path, duration)
                success += 1
                logger.info(f"Video generated: {item.id[:8]} -> {final_path}")
            else:
                store.update_status(item.id, "video_failed", "Video generation failed")
                failed += 1
        except Exception as e:
            logger.error(f"Video generation error for {item.id[:8]}: {e}")
            store.update_status(item.id, "video_failed", str(e))
            failed += 1

    await client.close()
    return {"success": success, "failed": failed}
