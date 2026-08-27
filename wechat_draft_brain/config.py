from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

from wechat_draft_brain.paths import DEFAULT_CONFIG, USER_CONFIG

CAPTURE_SOURCES = ("ocr", "clipboard", "both")
CAPTURE_CHOICES = (
    ("ocr", "仅 OCR 当前窗口"),
    ("clipboard", "仅剪贴板"),
    ("both", "OCR 优先，没有字再用剪贴板"),
)
THEME_SOURCES = ("dark", "light")
THEME_CHOICES = (
    ("dark", "深色模式"),
    ("light", "浅色模式"),
)


def normalize_capture(raw: str | None) -> str:
    value = str(raw or "ocr").strip().lower()
    return value if value in CAPTURE_SOURCES else "ocr"


def normalize_theme(raw: str | None) -> str:
    value = str(raw or "dark").strip().lower()
    return value if value in THEME_SOURCES else "dark"


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    cfg = deep_merge(_read_yaml(DEFAULT_CONFIG), _read_yaml(USER_CONFIG))
    llm = cfg.setdefault("llm", {})
    llm["base_url"] = (
        os.environ.get("OPENAI_BASE_URL")
        or llm.get("base_url")
        or "https://api.openai.com/v1"
    )
    llm["api_key"] = os.environ.get("OPENAI_API_KEY") or llm.get("api_key") or ""
    llm["model"] = os.environ.get("DRAFT_MODEL") or llm.get("model") or "gpt-4o-mini"
    cfg.setdefault("hotkey", "<ctrl>+<alt>+w")
    cfg["capture"] = normalize_capture(cfg.get("capture"))
    cfg["theme"] = normalize_theme(cfg.get("theme"))
    return cfg


def save_user_settings(
    *,
    hotkey: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    capture: str | None = None,
    theme: str | None = None,
) -> None:
    data = _read_yaml(USER_CONFIG)
    if hotkey is not None:
        data["hotkey"] = hotkey.strip() or "<ctrl>+<alt>+w"
    if capture is not None:
        data["capture"] = normalize_capture(capture)
    if theme is not None:
        data["theme"] = normalize_theme(theme)
    llm = data.setdefault("llm", {})
    if api_key is not None:
        llm["api_key"] = api_key.strip()
    if base_url is not None:
        llm["base_url"] = base_url.strip()
    if model is not None:
        llm["model"] = model.strip() or "gpt-4o-mini"
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    USER_CONFIG.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
