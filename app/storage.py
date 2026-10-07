"""Local SQLite storage for conversation history, keyed by a simple
username typed into the UI - no password, no real authentication. Anyone
who types a given username sees that username's history; this is "view my
previous conversations" for a single personal/local deployment, not access
control. Real auth is listed as deferred production work in the README.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "conversations.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                major_slug TEXT,
                title TEXT NOT NULL,
                messages_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def save_conversation(
    conversation_id: int | None, username: str, major_slug: str, messages: list[dict]
) -> int:
    """Insert a new conversation (conversation_id is None) or update an
    existing one in place. Returns the row's id either way, so the caller
    can remember it in st.session_state and keep updating the same row as
    the conversation continues."""
    now = datetime.now(timezone.utc).isoformat()
    first_question = next((m["content"] for m in messages if m["role"] == "user"), "New conversation")
    title = first_question[:80]
    messages_json = json.dumps(messages)

    with _connect() as conn:
        if conversation_id is None:
            cursor = conn.execute(
                "INSERT INTO conversations "
                "(username, major_slug, title, messages_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (username, major_slug, title, messages_json, now, now),
            )
            return cursor.lastrowid
        else:
            conn.execute(
                "UPDATE conversations SET major_slug=?, title=?, messages_json=?, updated_at=? "
                "WHERE id=?",
                (major_slug, title, messages_json, now, conversation_id),
            )
            return conversation_id


def list_conversations(username: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, major_slug, updated_at FROM conversations "
            "WHERE username = ? ORDER BY updated_at DESC",
            (username,),
        ).fetchall()
    return [dict(row) for row in rows]


def load_conversation(conversation_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["messages"] = json.loads(data["messages_json"])
    return data
