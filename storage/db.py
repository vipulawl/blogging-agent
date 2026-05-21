import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path("blogging_agent.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                keyword TEXT NOT NULL,
                research_brief TEXT,
                source TEXT DEFAULT 'web_search',
                priority_score REAL DEFAULT 0.5,
                status TEXT DEFAULT 'queued',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER REFERENCES topics(id),
                title TEXT,
                slug TEXT,
                meta_description TEXT,
                tags TEXT DEFAULT '[]',
                content TEXT,
                version INTEGER DEFAULT 1,
                edit_notes TEXT,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS strategy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_pillars TEXT DEFAULT '[]',
                competitors TEXT DEFAULT '[]',
                content_gaps TEXT DEFAULT '[]',
                quick_wins TEXT DEFAULT '[]',
                avoid_topics TEXT DEFAULT '[]',
                strategic_summary TEXT,
                interview_data TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS competitor_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competitor_url TEXT NOT NULL,
                post_url TEXT NOT NULL UNIQUE,
                post_title TEXT,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS refreshes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                title TEXT,
                keyword TEXT,
                slug TEXT,
                original_content TEXT,
                refreshed_content TEXT,
                meta_description TEXT,
                refresh_notes TEXT,
                refresh_score INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


def save_topic(title: str, keyword: str, research_brief: str, source: str = "web_search", priority_score: float = 0.5) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO topics (title, keyword, research_brief, source, priority_score) VALUES (?, ?, ?, ?, ?)",
            (title, keyword, research_brief, source, priority_score)
        )
        return cursor.lastrowid


def get_next_topic() -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM topics WHERE status = 'queued' ORDER BY priority_score DESC, created_at ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE topics SET status = 'writing' WHERE id = ?", (row["id"],))
        return dict(row)


def get_topic_by_id(topic_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
        return dict(row) if row else None


def get_all_topics(status: str = None) -> list[dict]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM topics WHERE status = ? ORDER BY priority_score DESC, created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM topics ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def save_draft(topic_id: int, title: str, slug: str, meta_description: str, tags: list, content: str) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO drafts (topic_id, title, slug, meta_description, tags, content) VALUES (?, ?, ?, ?, ?, ?)",
            (topic_id, title, slug, meta_description, json.dumps(tags), content)
        )
        conn.execute("UPDATE topics SET status = 'editing' WHERE id = ?", (topic_id,))
        return cursor.lastrowid


def get_latest_draft_for_topic(topic_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM drafts WHERE topic_id = ? ORDER BY created_at DESC LIMIT 1",
            (topic_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = json.loads(d["tags"] or "[]")
        return d


def save_edited_draft(draft_id: int, content: str, edit_notes: str, title: str = None, meta_description: str = None) -> None:
    with get_conn() as conn:
        draft = conn.execute("SELECT topic_id FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not draft:
            return

        fields = {"content": content, "edit_notes": edit_notes, "version": 2, "status": "edited",
                  "updated_at": datetime.now().isoformat()}
        if title:
            fields["title"] = title
        if meta_description:
            fields["meta_description"] = meta_description

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE drafts SET {set_clause} WHERE id = ?", (*fields.values(), draft_id))
        conn.execute("UPDATE topics SET status = 'pending_approval' WHERE id = ?", (draft["topic_id"],))


def get_pending_drafts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT d.*, t.keyword
            FROM drafts d
            JOIN topics t ON d.topic_id = t.id
            WHERE d.status = 'edited'
            ORDER BY d.updated_at DESC
        """).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"] or "[]")
            result.append(d)
        return result


def approve_draft(draft_id: int) -> dict:
    with get_conn() as conn:
        conn.execute("UPDATE drafts SET status = 'approved' WHERE id = ?", (draft_id,))
        row = conn.execute("""
            SELECT d.*, t.keyword
            FROM drafts d JOIN topics t ON d.topic_id = t.id
            WHERE d.id = ?
        """, (draft_id,)).fetchone()
        conn.execute("UPDATE topics SET status = 'published' WHERE id = ?", (row["topic_id"],))
        d = dict(row)
        d["tags"] = json.loads(d["tags"] or "[]")
        return d


def reject_draft(draft_id: int) -> None:
    with get_conn() as conn:
        draft = conn.execute("SELECT topic_id FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        conn.execute("UPDATE drafts SET status = 'rejected' WHERE id = ?", (draft_id,))
        if draft:
            conn.execute("UPDATE topics SET status = 'rejected' WHERE id = ?", (draft["topic_id"],))


# ── Strategy ──────────────────────────────────────────────────────────────────

def save_strategy(data: dict, interview: dict = None) -> int:
    with get_conn() as conn:
        conn.execute("UPDATE strategy SET is_active = 0")
        cursor = conn.execute(
            """INSERT INTO strategy
               (content_pillars, competitors, content_gaps, quick_wins, avoid_topics, strategic_summary, interview_data)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                json.dumps(data.get("content_pillars", [])),
                json.dumps(data.get("competitors", [])),
                json.dumps(data.get("content_gaps", [])),
                json.dumps(data.get("quick_wins", [])),
                json.dumps(data.get("avoid_topics", [])),
                data.get("strategic_summary", ""),
                json.dumps(interview or {}),
            ),
        )
        return cursor.lastrowid


def get_active_strategy() -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM strategy WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("content_pillars", "competitors", "content_gaps", "quick_wins", "avoid_topics", "interview_data"):
            d[key] = json.loads(d[key] or "[]")
        return d


# ── Competitor post tracking ───────────────────────────────────────────────────

def get_known_post_urls(competitor_url: str) -> set[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT post_url FROM competitor_posts WHERE competitor_url = ?", (competitor_url,)
        ).fetchall()
        return {r["post_url"] for r in rows}


def save_competitor_posts(competitor_url: str, posts: list[dict]) -> list[dict]:
    """Save new posts; return only the ones not seen before."""
    known = get_known_post_urls(competitor_url)
    new_posts = [p for p in posts if p.get("url") and p["url"] not in known]
    with get_conn() as conn:
        for p in new_posts:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO competitor_posts (competitor_url, post_url, post_title) VALUES (?, ?, ?)",
                    (competitor_url, p["url"], p.get("title", "")),
                )
            except Exception:
                pass
    return new_posts


# ── Refresh tracking ──────────────────────────────────────────────────────────

def save_refresh(file_path: str, title: str, keyword: str, slug: str,
                 original_content: str, refreshed_content: str,
                 meta_description: str, refresh_notes: str, refresh_score: int) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO refreshes
               (file_path, title, keyword, slug, original_content, refreshed_content,
                meta_description, refresh_notes, refresh_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (file_path, title, keyword, slug, original_content, refreshed_content,
             meta_description, refresh_notes, refresh_score),
        )
        return cursor.lastrowid


def get_pending_refreshes() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM refreshes WHERE status = 'pending' ORDER BY refresh_score DESC, created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def mark_refresh_done(refresh_id: int, status: str = "pr_created") -> None:
    with get_conn() as conn:
        conn.execute("UPDATE refreshes SET status = ? WHERE id = ?", (status, refresh_id))


def was_recently_refreshed(file_path: str, within_days: int = 60) -> bool:
    """Prevent refreshing the same article too often."""
    with get_conn() as conn:
        cutoff = datetime.now().isoformat()[:10]
        row = conn.execute(
            """SELECT id FROM refreshes
               WHERE file_path = ? AND status != 'rejected'
               AND date(created_at) >= date(?, ?)
               LIMIT 1""",
            (file_path, cutoff, f"-{within_days} days"),
        ).fetchone()
        return row is not None
