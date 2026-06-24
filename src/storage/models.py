import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel, Field

tz_utc8 = timezone(timedelta(hours=8))


def now() -> str:
    return datetime.now(tz_utc8).isoformat()


def new_uuid() -> str:
    return str(uuid.uuid4())


class ContentItem(BaseModel):
    id: str = Field(default_factory=new_uuid)
    url: str
    title: str = ""
    original_text: str = ""
    source: str = ""
    published_at: str = ""
    collected_at: str = Field(default_factory=now)

    topic_category: str = ""
    sub_category: str = ""
    core_points: str = "[]"
    summary: str = ""
    target_audience: str = "[]"
    priority: str = ""

    xhs_title: str = ""
    xhs_content: str = ""
    xhs_tags: str = "[]"

    video_path: str = ""
    video_duration: int = 0
    video_status: str = ""
    video_prompt: str = ""

    publish_status: str = ""
    xhs_note_id: str = ""
    xhs_published_at: str = ""
    scheduled_time: str = ""

    status: str = "pending"
    processed_at: str = ""
    error_message: str = ""


class Stats(BaseModel):
    total: int = 0
    pending: int = 0
    processed: int = 0
    video_generated: int = 0
    published: int = 0
    failed: int = 0
