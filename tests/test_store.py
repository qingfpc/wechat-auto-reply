import os
from pathlib import Path
from tempfile import TemporaryDirectory

from wechat_draft_brain import store


def test_capture_claim_persists_until_ttl_expires(monkeypatch):
    with TemporaryDirectory(dir=os.environ.get("APPDATA")) as dirname:
        data_dir = Path(dirname)
        monkeypatch.setattr(store, "DATA_DIR", data_dir)
        monkeypatch.setattr(store, "DB_PATH", data_dir / "test.sqlite3")
        store.init_db()

        assert store.claim_capture("same-message", 10, now=100.0)
        assert not store.claim_capture("same-message", 10, now=105.0)
        assert store.claim_capture("same-message", 10, now=111.0)
