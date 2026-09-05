from __future__ import annotations

import copy
import math
import os
from dataclasses import dataclass
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

_LAYOUT_DEFAULTS = {
    "sidebar_px": 360.0,
    "sidebar_min_px": 150.0,
    "sidebar_min_contrast": 30.0,
    "sidebar_max_ratio": 0.42,
    "header_px": 78.0,
    "ocr_min_score": 0.75,
    "chat_bottom": 0.90,
    "incoming_max_x": 0.48,
    "outgoing_min_x": 0.52,
}


@dataclass(frozen=True)
class ConfigLoadResult:
    config: dict
    warnings: tuple[str, ...] = ()


def normalize_capture(raw: str | None) -> str:
    value = str(raw or "ocr").strip().lower()
    return value if value in CAPTURE_SOURCES else "ocr"


def normalize_theme(raw: str | None) -> str:
    value = str(raw or "dark").strip().lower()
    return value if value in THEME_SOURCES else "dark"


def _read_yaml(path: Path, label: str) -> tuple[dict, list[str]]:
    try:
        if not path.exists():
            return {}, []
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return {}, [f"{label}无法读取（{type(exc).__name__}），已使用安全默认值。"]
    if data is None:
        return {}, []
    if not isinstance(data, dict):
        return {}, [f"{label}根节点必须是对象，已忽略该文件。"]
    return data, []


def deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _number(value, default: float, field_name: str, warnings: list[str]) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        warnings.append(f"配置项 {field_name} 不是有效数字，已使用默认值。")
        return default
    if not math.isfinite(number):
        warnings.append(f"配置项 {field_name} 不是有限数字，已使用默认值。")
        return default
    return number


def load_config_result() -> ConfigLoadResult:
    defaults, warnings = _read_yaml(DEFAULT_CONFIG, "默认配置")
    user, user_warnings = _read_yaml(USER_CONFIG, "用户配置")
    warnings.extend(user_warnings)
    cfg = deep_merge(defaults, user)

    llm = cfg.get("llm")
    if llm is None:
        llm = {}
        cfg["llm"] = llm
    elif not isinstance(llm, dict):
        warnings.append("配置项 llm 必须是对象，已使用默认值。")
        llm = {}
        cfg["llm"] = llm
    llm["base_url"] = (
        os.environ.get("OPENAI_BASE_URL")
        or llm.get("base_url")
        or "https://api.openai.com/v1"
    )
    llm["api_key"] = os.environ.get("OPENAI_API_KEY") or llm.get("api_key") or ""
    llm["model"] = os.environ.get("DRAFT_MODEL") or llm.get("model") or "gpt-4o-mini"

    hotkey = cfg.get("hotkey")
    if not isinstance(hotkey, str) or not hotkey.strip():
        if hotkey is not None:
            warnings.append("配置项 hotkey 不是有效字符串，已使用默认值。")
        hotkey = "<ctrl>+<alt>+w"
    cfg["hotkey"] = hotkey
    cfg["capture"] = normalize_capture(cfg.get("capture"))
    cfg["theme"] = normalize_theme(cfg.get("theme"))
    cfg["capture_dedup_seconds"] = _number(
        cfg.get("capture_dedup_seconds", 10), 10.0, "capture_dedup_seconds", warnings
    )

    layout = cfg.get("layout")
    if layout is None:
        layout = {}
    elif not isinstance(layout, dict):
        warnings.append("配置项 layout 必须是对象，已使用默认值。")
        layout = {}
    cfg["layout"] = {
        **layout,
        **{
            key: _number(layout.get(key, default), default, f"layout.{key}", warnings)
            for key, default in _LAYOUT_DEFAULTS.items()
        },
    }

    policy = cfg.get("policy")
    if policy is None:
        policy = {}
    elif not isinstance(policy, dict):
        warnings.append("配置项 policy 必须是对象，已使用默认值。")
        policy = {}
    auto_scenes = policy.get("auto_scenes", ["smalltalk", "logistics"])
    if not isinstance(auto_scenes, list) or not all(isinstance(item, str) for item in auto_scenes):
        warnings.append("配置项 policy.auto_scenes 必须是字符串列表，已使用默认值。")
        auto_scenes = ["smalltalk", "logistics"]
    policy["auto_scenes"] = auto_scenes
    policy["max_auto_per_hour"] = int(
        _number(policy.get("max_auto_per_hour", 20), 20.0, "policy.max_auto_per_hour", warnings)
    )
    cfg["policy"] = policy
    return ConfigLoadResult(cfg, tuple(warnings))


def load_config() -> dict:
    return load_config_result().config


def save_user_settings(
    *,
    hotkey: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    capture: str | None = None,
    theme: str | None = None,
) -> None:
    data, warnings = _read_yaml(USER_CONFIG, "用户配置")
    if warnings:
        raise ValueError("用户配置当前无法安全读取，请先备份或修复原文件。")
    if hotkey is not None:
        data["hotkey"] = hotkey.strip() or "<ctrl>+<alt>+w"
    if capture is not None:
        data["capture"] = normalize_capture(capture)
    if theme is not None:
        data["theme"] = normalize_theme(theme)
    llm = data.get("llm")
    if llm is None:
        llm = {}
        data["llm"] = llm
    elif not isinstance(llm, dict):
        raise ValueError("用户配置中的 llm 不是对象，无法安全保存。")
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
