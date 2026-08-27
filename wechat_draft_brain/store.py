from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from wechat_draft_brain.paths import DATA_DIR, DB_PATH

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kv (
              k TEXT PRIMARY KEY,
              v TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drafts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at REAL NOT NULL,
              mode TEXT NOT NULL,
              contact TEXT,
              scene TEXT,
              action TEXT,
              source_text TEXT,
              drafts_json TEXT,
              risks_json TEXT,
              reason TEXT,
              status TEXT NOT NULL DEFAULT 'pending',
              chosen_text TEXT,
              sent INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at REAL NOT NULL,
              level TEXT NOT NULL,
              message TEXT NOT NULL
            );
            """
        )


def kv_get(key: str, default: str | None = None) -> str | None:
    with db() as conn:
        row = conn.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        return row["v"] if row else default


def kv_set(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (key, value),
        )


def log_event(message: str, level: str = "info") -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO events(created_at, level, message) VALUES(?,?,?)",
            (time.time(), level, message),
        )


def list_events(limit: int = 40) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, created_at, level, message FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def insert_draft(row: dict[str, Any]) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO drafts(
              created_at, mode, contact, scene, action, source_text,
              drafts_json, risks_json, reason, status, sent
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                time.time(),
                row.get("mode") or "copilot",
                row.get("contact"),
                row.get("scene"),
                row.get("action"),
                row.get("source_text"),
                json.dumps(row.get("drafts") or [], ensure_ascii=False),
                json.dumps(row.get("risks") or [], ensure_ascii=False),
                row.get("reason"),
                row.get("status") or "pending",
                1 if row.get("sent") else 0,
            ),
        )
        return int(cur.lastrowid)


def list_drafts(limit: int = 30) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM drafts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["drafts"] = json.loads(item.pop("drafts_json") or "[]")
        item["risks"] = json.loads(item.pop("risks_json") or "[]")
        out.append(item)
    return out


def get_draft(draft_id: int) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["drafts"] = json.loads(item.pop("drafts_json") or "[]")
    item["risks"] = json.loads(item.pop("risks_json") or "[]")
    return item


def update_draft(draft_id: int, **fields: Any) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(
            f"UPDATE drafts SET {keys} WHERE id=?",
            (*fields.values(), draft_id),
        )


def auto_sent_last_hour() -> int:
    since = time.time() - 3600
    with db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM drafts WHERE sent=1 AND created_at>=?",
            (since,),
        ).fetchone()
    return int(row["n"] if row else 0)
