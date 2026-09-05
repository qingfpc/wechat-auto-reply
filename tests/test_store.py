import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from wechat_draft_brain import store


def _use_temp_db(monkeypatch, dirname: str) -> Path:
    data_dir = Path(dirname)
    db_path = data_dir / "test.sqlite3"
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "DB_PATH", db_path)
    return db_path


def test_init_db_creates_current_schema(monkeypatch):
    with TemporaryDirectory() as dirname:
        db_path = _use_temp_db(monkeypatch, dirname)

        store.init_db()

        with closing(sqlite3.connect(db_path)) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert version == store.CURRENT_SCHEMA_VERSION
        assert {"kv", "drafts", "events", "capture_claims"} <= tables


def test_init_db_versions_legacy_schema_without_losing_rows(monkeypatch):
    with TemporaryDirectory() as dirname:
        db_path = _use_temp_db(monkeypatch, dirname)
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            conn.execute("INSERT INTO kv(k, v) VALUES('mode', 'copilot')")
            conn.commit()

        store.init_db()

        with closing(sqlite3.connect(db_path)) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            value = conn.execute("SELECT v FROM kv WHERE k='mode'").fetchone()[0]
        assert version == store.CURRENT_SCHEMA_VERSION
        assert value == "copilot"


def test_init_db_rejects_newer_schema(monkeypatch):
    with TemporaryDirectory() as dirname:
        db_path = _use_temp_db(monkeypatch, dirname)
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA user_version = 99")

        try:
            store.init_db()
        except RuntimeError as exc:
            assert "数据库版本 99" in str(exc)
        else:
            raise AssertionError("应拒绝程序无法识别的新数据库版本")


def test_capture_claim_persists_until_ttl_expires(monkeypatch):
    with TemporaryDirectory() as dirname:
        _use_temp_db(monkeypatch, dirname)
        store.init_db()

        assert store.claim_capture("same-message", 10, now=100.0)
        assert not store.claim_capture("same-message", 10, now=105.0)
        assert store.claim_capture("same-message", 10, now=111.0)
