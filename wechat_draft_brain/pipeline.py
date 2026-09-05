from __future__ import annotations

import hashlib
import threading
from typing import Any

from wechat_draft_brain.brain import SCENE_LABELS, run_brain
from wechat_draft_brain.config import load_config_result
from wechat_draft_brain.paths import LAST_SHOT
from wechat_draft_brain.store import (
    auto_sent_last_hour,
    claim_capture,
    clear_history,
    init_db,
    insert_draft,
    kv_get,
    kv_set,
    log_event,
)
from wechat_draft_brain.vision import capture_context

_config_result = load_config_result()
_cfg = _config_result.config
_config_warnings = list(_config_result.warnings)
_lock = threading.Lock()
_hotkeys = None


def _capture_fingerprint(capture) -> str:
    message = capture.latest_actionable_message
    if capture.used_source != "ocr" or message is None or message.role != "incoming":
        return ""
    normalize = lambda value: " ".join((value or "").split())
    payload = "\x1f".join(
        (
            normalize(capture.contact),
            "group" if capture.is_group else "private",
            message.kind,
            normalize(message.author),
            normalize(message.text),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def reload_config() -> dict[str, Any]:
    global _cfg, _config_warnings
    result = load_config_result()
    _cfg = result.config
    _config_warnings = list(result.warnings)
    enforce_privacy_settings()
    return _cfg


def _privacy_flags() -> dict[str, bool]:
    privacy = _cfg.get("privacy") or {}
    return {
        "save_source_text": bool(privacy.get("save_source_text", True)),
        "save_last_screenshot": bool(privacy.get("save_last_screenshot", True)),
    }


def enforce_privacy_settings() -> None:
    if not _privacy_flags()["save_last_screenshot"]:
        LAST_SHOT.unlink(missing_ok=True)


def clear_local_history() -> dict[str, int | bool]:
    screenshot_removed = LAST_SHOT.exists()
    LAST_SHOT.unlink(missing_ok=True)
    counts = clear_history()
    return {**counts, "screenshot_removed": screenshot_removed}


def current_flags() -> dict[str, Any]:
    return {
        "mode": "copilot",
        "hotkey": _cfg.get("hotkey") or "<ctrl>+<alt>+w",
        "llm_ready": bool((_cfg.get("llm") or {}).get("api_key")),
        "model": (_cfg.get("llm") or {}).get("model") or "gpt-4o-mini",
        "last_shot": str(LAST_SHOT) if LAST_SHOT.exists() else "",
        "capture": _cfg.get("capture") or "ocr",
        "privacy": _privacy_flags(),
        "config_warnings": list(_config_warnings),
    }


def _save_result(result, mode: str, sent: bool, status: str) -> int:
    return insert_draft(
        {
            "mode": mode,
            "contact": result.contact,
            "scene": result.scene,
            "action": result.action,
            "source_text": (
                result.source_text if _privacy_flags()["save_source_text"] else ""
            ),
            "drafts": result.drafts,
            "risks": result.risks,
            "reason": result.reason,
            "status": status,
            "sent": sent,
            "generation_source": result.generation_source,
            "fallback_reason": result.fallback_reason,
        }
    )


def ingest_text(source_text: str, *, contact: str = "", mode: str | None = None) -> dict[str, Any]:
    use_mode = mode or "copilot"
    result = run_brain(
        source_text,
        _cfg,
        mode=use_mode,
        dry_run=True,
        auto_armed=False,
        contact=contact,
        sent_last_hour=auto_sent_last_hour(),
    )
    status = "ignored" if result.action == "ignore" else "pending"
    draft_id = _save_result(result, use_mode, False, status)
    source_label = {"llm": "模型", "rules": "规则", "none": "未生成"}.get(
        result.generation_source, result.generation_source
    )
    event_message = (
        f"拟稿 #{draft_id} {SCENE_LABELS.get(result.scene, result.scene)} → "
        f"{result.action} / {result.contact} / {source_label}"
    )
    if result.fallback_reason:
        event_message += f"；已降级：{result.fallback_reason}"
    log_event(event_message, "warn" if result.fallback_reason else "info")
    return {
        "id": draft_id,
        "contact": result.contact,
        "scene": result.scene,
        "scene_label": SCENE_LABELS.get(result.scene, result.scene),
        "confidence": result.confidence,
        "action": result.action,
        "risks": result.risks,
        "drafts": result.drafts,
        "reason": result.reason,
        "generation_source": result.generation_source,
        "fallback_reason": result.fallback_reason,
        "source_text": result.source_text,
        "status": status,
        "sent": False,
        "ok": True,
    }


def ingest_hotkey() -> dict[str, Any]:
    source = _cfg.get("capture") or "ocr"
    capture = capture_context(source=source, layout=_cfg.get("layout") or {})
    text, image = capture.text, capture.image
    fingerprint = _capture_fingerprint(capture)
    dedup_seconds = float(_cfg.get("capture_dedup_seconds") or 10)
    if fingerprint and not claim_capture(fingerprint, dedup_seconds):
        msg = "这条消息刚刚已经生成过草稿。"
        log_event(msg, "warn")
        return {"ok": False, "duplicate": True, "error": msg}
    if image is not None and _privacy_flags()["save_last_screenshot"]:
        LAST_SHOT.parent.mkdir(parents=True, exist_ok=True)
        image.save(LAST_SHOT)
    if not text:
        if source == "clipboard":
            msg = "剪贴板没有可用文字。先复制聊天记录再按快捷键。"
        elif source == "both":
            msg = "没有识别到对话。把微信窗口置于前台，或先复制聊天记录。"
        else:
            msg = "没有识别到对话。把微信窗口置于前台再按快捷键。"
        log_event(f"快捷键已触发，但未读到文字。{msg}", "warn")
        return {"ok": False, "error": msg}
    return ingest_text(text, contact=capture.contact, mode="copilot")


def stop_hotkeys() -> None:
    global _hotkeys
    if _hotkeys is None:
        return
    try:
        _hotkeys.stop()
    except Exception:
        pass
    _hotkeys = None


def start_hotkeys() -> None:
    global _hotkeys
    stop_hotkeys()
    from pynput import keyboard

    combo = current_flags()["hotkey"]

    def _wrapped():
        try:
            ingest_hotkey()
        except Exception as e:
            log_event(f"快捷键处理失败: {e}", "error")

    try:
        _hotkeys = keyboard.GlobalHotKeys({combo: _wrapped})
        _hotkeys.start()
        log_event(f"快捷键已监听 {combo}")
    except Exception as e:
        _hotkeys = None
        log_event(f"快捷键监听失败，请用窗口粘贴。原因: {e}", "warn")


def restart_hotkeys() -> None:
    with _lock:
        reload_config()
        start_hotkeys()


def start_background() -> None:
    init_db()
    enforce_privacy_settings()
    for warning in _config_warnings:
        log_event(warning, "warn")
    if kv_get("mode") is None:
        kv_set("mode", "copilot")
    start_hotkeys()


def stop_background() -> None:
    stop_hotkeys()
