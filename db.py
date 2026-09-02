import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "requests.sqlite3"


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operator_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                username TEXT,
                message_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def save_operator_request(telegram_user_id: int, username: str | None, message_text: str) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO operator_requests (telegram_user_id, username, message_text, created_at) "
            "VALUES (?, ?, ?, ?)",
            (telegram_user_id, username, message_text, created_at),
        )
