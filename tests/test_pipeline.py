from wechat_draft_brain import pipeline
from wechat_draft_brain.chat_parser import ChatMessage
from wechat_draft_brain.vision import CaptureResult


def test_hotkey_passes_captured_contact_to_brain(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(pipeline, "_cfg", {"capture": "ocr", "layout": {}})
    monkeypatch.setattr(
        pipeline,
        "capture_context",
        lambda **kwargs: CaptureResult("对方: 在吗", None, contact="老高"),
    )

    def fake_ingest(text: str, *, contact: str, mode: str):
        captured.update(text=text, contact=contact, mode=mode)
        return {"ok": True}

    monkeypatch.setattr(pipeline, "ingest_text", fake_ingest)

    assert pipeline.ingest_hotkey() == {"ok": True}
    assert captured == {"text": "对方: 在吗", "contact": "老高", "mode": "copilot"}


def _ocr_capture() -> CaptureResult:
    return CaptureResult(
        "[会话] 老高\n对方: 在吗",
        None,
        contact="老高",
        messages=[ChatMessage("incoming", "text", "在吗")],
        used_source="ocr",
    )


def test_hotkey_rejects_recent_duplicate_before_drafting(monkeypatch):
    drafted = []
    monkeypatch.setattr(
        pipeline, "_cfg", {"capture": "ocr", "layout": {}, "capture_dedup_seconds": 10}
    )
    monkeypatch.setattr(pipeline, "capture_context", lambda **kwargs: _ocr_capture())
    monkeypatch.setattr(pipeline, "claim_capture", lambda fingerprint, ttl: False)
    monkeypatch.setattr(pipeline, "log_event", lambda *args: None)
    monkeypatch.setattr(pipeline, "ingest_text", lambda *args, **kwargs: drafted.append(args))

    result = pipeline.ingest_hotkey()

    assert result == {
        "ok": False,
        "duplicate": True,
        "error": "这条消息刚刚已经生成过草稿。",
    }
    assert drafted == []


def test_clipboard_capture_does_not_claim_ocr_fingerprint(monkeypatch):
    claims = []
    monkeypatch.setattr(pipeline, "_cfg", {"capture": "clipboard", "layout": {}})
    monkeypatch.setattr(
        pipeline,
        "capture_context",
        lambda **kwargs: CaptureResult("在吗", None, used_source="clipboard"),
    )
    monkeypatch.setattr(
        pipeline, "claim_capture", lambda *args: claims.append(args) or True
    )
    monkeypatch.setattr(pipeline, "ingest_text", lambda *args, **kwargs: {"ok": True})

    assert pipeline.ingest_hotkey() == {"ok": True}
    assert claims == []


def test_startup_writes_config_warnings_to_event_log(monkeypatch):
    events = []
    monkeypatch.setattr(pipeline, "_config_warnings", ["用户配置无法读取"])
    monkeypatch.setattr(pipeline, "init_db", lambda: None)
    monkeypatch.setattr(pipeline, "kv_get", lambda key: "copilot")
    monkeypatch.setattr(pipeline, "log_event", lambda message, level: events.append((message, level)))
    monkeypatch.setattr(pipeline, "start_hotkeys", lambda: None)

    pipeline.start_background()

    assert events == [("用户配置无法读取", "warn")]
