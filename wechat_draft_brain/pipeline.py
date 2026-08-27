from __future__ import annotations

import threading
import time
from typing import Any

from wechat_draft_brain.brain import SCENE_LABELS, run_brain
from wechat_draft_brain.config import load_config
from wechat_draft_brain.paths import LAST_SHOT
from wechat_draft_brain.phone import PhoneError, adb_status, run_auto_tick
from wechat_draft_brain.store import (
    auto_sent_last_hour,
    init_db,
    insert_draft,
    kv_get,
    kv_set,
    log_event,
)
from wechat_draft_brain.vision import capture_context

_cfg = load_config()
_lock = threading.Lock()
_hotkeys = None
_auto_stop = threading.Event()
_auto_thread: threading.Thread | None = None
_last_adb_warn = 0


def _bool_kv(key: str, default: bool) -> bool:
    raw = kv_get(key)
    if raw is None:
        return default
    return raw in {"1", "true", "yes", "on"}


def current_flags() -> dict[str, Any]:
    return {
        "mode": kv_get("mode") or _cfg.get("mode") or "copilot",
        "auto_armed": _bool_kv("auto_armed", False),
        "dry_run": _bool_kv("dry_run", bool(_cfg.get("dry_run", True))),
        "hotkey": _cfg.get("hotkey") or "<ctrl>+<alt>+w",
        "poll_seconds": int(_cfg.get("poll_seconds") or 30),
    }


def set_flags(**kwargs: Any) -> dict[str, Any]:
    mapping = {
        "mode": lambda v: "auto" if v == "auto" else "copilot",
        "auto_armed": lambda v: "1" if v else "0",
        "dry_run": lambda v: "1" if v else "0",
    }
    with _lock:
        for k, conv in mapping.items():
            if k in kwargs:
                kv_set(k, conv(kwargs[k]))
        flags = current_flags()
    log_event(
        f"模式={flags['mode']} 保险={'开' if flags['auto_armed'] else '关'} 空跑={'开' if flags['dry_run'] else '关'}"
    )
    return flags


def _save_result(result, mode: str, sent: bool, status: str) -> int:
    return insert_draft(
        {
            "mode": mode,
            "contact": result.contact,
            "scene": result.scene,
            "action": result.action,
            "source_text": result.source_text,
            "drafts": result.drafts,
            "risks": result.risks,
            "reason": result.reason,
            "status": status,
            "sent": sent,
        }
    )


def ingest_text(source_text: str, *, contact: str = "", mode: str | None = None) -> dict[str, Any]:
    flags = current_flags()
    use_mode = mode or flags["mode"]
    result = run_brain(
        source_text,
        _cfg,
        mode=use_mode,
        dry_run=flags["dry_run"],
        auto_armed=flags["auto_armed"],
        contact=contact,
        sent_last_hour=auto_sent_last_hour(),
    )
    status = "ignored" if result.action == "ignore" else "pending"
    sent = False
    draft_id = _save_result(result, use_mode, sent, status)
    log_event(
        f"拟稿 #{draft_id} {SCENE_LABELS.get(result.scene, result.scene)} → {result.action} / {result.contact}"
    )
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
        "source_text": result.source_text,
        "status": status,
        "sent": sent,
    }


def ingest_hotkey() -> dict[str, Any]:
    text, image = capture_context(prefer_clipboard=True)
    if image is not None:
        LAST_SHOT.parent.mkdir(parents=True, exist_ok=True)
        image.save(LAST_SHOT)
    if not text:
        log_event("快捷键已触发，但剪贴板和当前窗口都没有可用文字", "warn")
        return {"ok": False, "error": "没有识别到对话。先复制聊天记录，或把微信窗口置于前台再按快捷键。"}
    payload = ingest_text(text, mode="copilot")
    payload["ok"] = True
    return payload


def ingest_auto_tick() -> dict[str, Any]:
    flags = current_flags()
    if flags["mode"] != "auto":
        return {"ok": True, "skipped": True, "detail": "当前是拟稿模式，跳过轮询"}
    try:
        tick = run_auto_tick(_cfg)
    except PhoneError as e:
        global _last_adb_warn
        now = time.time()
        if now - _last_adb_warn > 120:
            log_event(str(e), "warn")
            _last_adb_warn = now
        return {"ok": False, "error": str(e)}
    if not tick.get("found"):
        return {"ok": True, "skipped": True, "detail": tick.get("detail")}
    source = tick.get("source") or ""
    if not source:
        log_event(tick.get("detail") or "自动轮询无文本", "warn")
        return {"ok": True, "skipped": True, "detail": tick.get("detail")}
    result = run_brain(
        source,
        _cfg,
        mode="auto",
        dry_run=flags["dry_run"],
        auto_armed=flags["auto_armed"],
        contact=tick.get("contact") or "",
        sent_last_hour=auto_sent_last_hour(),
    )
    sent = False
    status = "pending"
    phone = tick.get("phone")
    if result.action == "auto_send" and result.drafts and phone:
        try:
            phone.send_message(result.drafts[0], tick.get("image"))
            sent = True
            status = "sent"
            log_event(f"已自动回复 {result.contact}: {result.drafts[0][:40]}")
        except Exception as e:
            log_event(f"自动发送失败: {e}", "error")
            result.risks.append(f"发送失败: {e}")
            result.action = "queue"
            result.reason = "识别成功但发送失败，草稿留在队列。"
    if phone:
        try:
            phone.back()
        except Exception:
            pass
    if result.action == "ignore":
        status = "ignored"
    draft_id = _save_result(result, "auto", sent, status)
    return {
        "ok": True,
        "id": draft_id,
        "detail": result.reason,
        "action": result.action,
        "sent": sent,
        "contact": result.contact,
    }


def _auto_loop() -> None:
    while not _auto_stop.is_set():
        flags = current_flags()
        seconds = max(8, int(flags["poll_seconds"]))
        if flags["mode"] == "auto":
            try:
                ingest_auto_tick()
            except Exception as e:
                log_event(f"自动轮询异常: {e}", "error")
        _auto_stop.wait(seconds)


def start_background() -> None:
    global _hotkeys, _auto_thread
    init_db()
    if kv_get("mode") is None:
        kv_set("mode", _cfg.get("mode") or "copilot")
        kv_set("dry_run", "1" if _cfg.get("dry_run", True) else "0")
        kv_set("auto_armed", "0")
    if _hotkeys is None:
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
            log_event(f"快捷键监听失败，请用页面粘贴。原因: {e}", "warn")
    if _auto_thread is None:
        _auto_thread = threading.Thread(target=_auto_loop, name="auto-ocr-adb", daemon=True)
        _auto_thread.start()


def snapshot() -> dict[str, Any]:
    flags = current_flags()
    return {
        **flags,
        "adb": adb_status(_cfg),
        "llm_ready": bool((_cfg.get("llm") or {}).get("api_key")),
        "model": (_cfg.get("llm") or {}).get("model"),
        "last_shot": str(LAST_SHOT) if LAST_SHOT.exists() else "",
    }
