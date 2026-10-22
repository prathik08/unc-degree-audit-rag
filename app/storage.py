"""Local SQLite storage for conversation history, keyed by an identity
string - the caller's job to supply a trustworthy one (app/streamlit_app.py
uses the verified email from Google login, not a typed username). Also
tracks spend and request counts across stored conversations for the
public-deploy rate limits (see total_cost_usd / user_cost_usd /
user_request_count) - a public link calling a paid API with no limit is a
real cost risk, not a hypothetical one.

Caveat: this ledger lives in a SQLite file on local disk. On a host with an
ephemeral filesystem (e.g. Streamlit Community Cloud across a container
restart), it resets to zero - these in-app caps are a courtesy, not the
backstop. The actual backstop is a spend limit set on the Anthropic API key
itself, in the Anthropic Console.
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


def _sum_cost(messages_json: str) -> float:
    messages = json.loads(messages_json)
    return sum(
        (m.get("meta") or {}).get("cost_usd", 0.0)
        for m in messages
        if m["role"] == "assistant"
    )


def total_cost_usd() -> float:
    """Spend across every stored conversation, all users combined - the
    number the global spending cap checks. Deliberately not per-session:
    a cap a visitor can reset just by starting a new session protects
    nothing."""
    with _connect() as conn:
        rows = conn.execute("SELECT messages_json FROM conversations").fetchall()
    return sum(_sum_cost(row["messages_json"]) for row in rows)


def user_cost_usd(username: str) -> float:
    """Spend across one identity's conversations - the per-user cap, on top
    of (not instead of) the global one."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT messages_json FROM conversations WHERE username = ?", (username,)
        ).fetchall()
    return sum(_sum_cost(row["messages_json"]) for row in rows)


def user_request_count(username: str) -> int:
    """Number of questions one identity has actually sent to the model
    (assistant messages with a meta - i.e. not the free structured-data
    answers). A dollar cap alone lets many cheap questions slip through
    before it trips; a flat count bounds that regardless of per-question
    cost."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT messages_json FROM conversations WHERE username = ?", (username,)
        ).fetchall()
    return sum(
        1
        for row in rows
        for m in json.loads(row["messages_json"])
        if m["role"] == "assistant" and m.get("meta")
    )
