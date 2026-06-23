import sqlite3
import json
from pathlib import Path
from typing import Optional

from .models import ContentItem, Stats, new_uuid, now

DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH = DB_DIR / "content.db"


def _ensure_dir():
    DB_DIR.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS content (
            id TEXT PRIMARY KEY,
            url TEXT UNIQUE NOT NULL,
            title TEXT DEFAULT '',
            original_text TEXT DEFAULT '',
            source TEXT DEFAULT '',
            published_at TEXT DEFAULT '',
            collected_at TEXT DEFAULT '',
            topic_category TEXT DEFAULT '',
            sub_category TEXT DEFAULT '',
            core_points TEXT DEFAULT '[]',
            summary TEXT DEFAULT '',
            target_audience TEXT DEFAULT '[]',
            priority TEXT DEFAULT '',
            xhs_title TEXT DEFAULT '',
            xhs_content TEXT DEFAULT '',
            xhs_tags TEXT DEFAULT '[]',
            video_path TEXT DEFAULT '',
            video_duration INTEGER DEFAULT 0,
            video_status TEXT DEFAULT '',
            video_prompt TEXT DEFAULT '',
            publish_status TEXT DEFAULT '',
            xhs_note_id TEXT DEFAULT '',
            xhs_published_at TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            processed_at TEXT DEFAULT '',
            error_message TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_content_status ON content(status)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_content_source ON content(source)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_content_collected_at ON content(collected_at)
    """)
    conn.commit()
    conn.close()


def _row_to_item(row: sqlite3.Row) -> ContentItem:
    return ContentItem(**dict(row))


class ContentStore:
    def __init__(self):
        init_db()

    def insert(self, item: ContentItem) -> str:
        conn = _get_conn()
        data = item.model_dump()
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        conn.execute(
            f"INSERT OR IGNORE INTO content ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        conn.commit()
        conn.close()
        return item.id

    def exists(self, url: str) -> bool:
        conn = _get_conn()
        row = conn.execute("SELECT 1 FROM content WHERE url = ?", (url,)).fetchone()
        conn.close()
        return row is not None

    def get_by_url(self, url: str) -> Optional[ContentItem]:
        conn = _get_conn()
        row = conn.execute("SELECT * FROM content WHERE url = ?", (url,)).fetchone()
        conn.close()
        return _row_to_item(row) if row else None

    def get_by_id(self, id: str) -> Optional[ContentItem]:
        conn = _get_conn()
        row = conn.execute("SELECT * FROM content WHERE id = ?", (id,)).fetchone()
        conn.close()
        return _row_to_item(row) if row else None

    def get_pending(self, limit: int = 50) -> list[ContentItem]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM content WHERE status = 'pending' ORDER BY collected_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [_row_to_item(r) for r in rows]

    def get_processed(self, limit: int = 10) -> list[ContentItem]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM content WHERE status = 'processed' ORDER BY processed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [_row_to_item(r) for r in rows]

    def get_publish_queue(self, limit: int = 1) -> list[ContentItem]:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT * FROM content
               WHERE status = 'video_generated' AND publish_status != 'published'
               ORDER BY
                 CASE priority WHEN '高' THEN 1 WHEN '中' THEN 2 WHEN '低' THEN 3 ELSE 4 END,
                 processed_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [_row_to_item(r) for r in rows]

    def list_all(self, status: str = "", source: str = "",
                 limit: int = 100, offset: int = 0) -> list[ContentItem]:
        conn = _get_conn()
        query = "SELECT * FROM content WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY collected_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [_row_to_item(r) for r in rows]

    def count_by_status(self, status: str) -> int:
        conn = _get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM content WHERE status = ?", (status,)
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0

    def update_after_process(self, id: str, result: dict):
        conn = _get_conn()
        conn.execute(
            """UPDATE content SET
               topic_category = ?, sub_category = ?, core_points = ?,
               summary = ?, target_audience = ?, priority = ?,
               xhs_title = ?, xhs_content = ?, xhs_tags = ?,
               video_prompt = ?,
               status = 'processed', processed_at = ?, error_message = ''
               WHERE id = ?""",
            (
                result.get("topic_category", ""),
                result.get("sub_category", ""),
                json.dumps(result.get("core_points", []), ensure_ascii=False),
                result.get("summary", ""),
                json.dumps(result.get("target_audience", []), ensure_ascii=False),
                result.get("priority", ""),
                result.get("xhs_title", ""),
                result.get("xhs_content", ""),
                json.dumps(result.get("xhs_tags", []), ensure_ascii=False),
                result.get("video_prompt", ""),
                now(),
                id,
            ),
        )
        conn.commit()
        conn.close()

    def update_status(self, id: str, status: str, error_message: str = ""):
        conn = _get_conn()
        conn.execute(
            "UPDATE content SET status = ?, error_message = ? WHERE id = ?",
            (status, error_message, id),
        )
        conn.commit()
        conn.close()

    def update_video_status(self, id: str, video_path: str, duration: int):
        conn = _get_conn()
        conn.execute(
            """UPDATE content SET
               video_path = ?, video_duration = ?,
               video_status = 'completed', status = 'video_generated'
               WHERE id = ?""",
            (video_path, duration, id),
        )
        conn.commit()
        conn.close()

    def update_publish_status(self, id: str, note_id: str = ""):
        conn = _get_conn()
        conn.execute(
            """UPDATE content SET
               publish_status = 'published', xhs_note_id = ?,
               xhs_published_at = ? WHERE id = ?""",
            (note_id, now(), id),
        )
        conn.commit()
        conn.close()

    def delete(self, id: str):
        conn = _get_conn()
        conn.execute("DELETE FROM content WHERE id = ?", (id,))
        conn.commit()
        conn.close()

    def get_stats(self) -> Stats:
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM content").fetchone()[0]

        statuses = ["pending", "processed", "video_generated", "published", "failed"]
        counts = {}
        for s in statuses:
            r = conn.execute(
                "SELECT COUNT(*) FROM content WHERE status = ?", (s,)
            ).fetchone()
            counts[s] = r[0] if r else 0
        conn.close()

        return Stats(total=total, **counts)

    def count_published_today(self) -> int:
        conn = _get_conn()
        today = now()[:10]
        row = conn.execute(
            "SELECT COUNT(*) FROM content WHERE publish_status = 'published' AND xhs_published_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        conn.close()
        return row[0] if row else 0
