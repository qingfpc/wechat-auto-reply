from wechat_draft_brain import pipeline
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
