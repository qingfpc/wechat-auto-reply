from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

from wechat_draft_brain.paths import DEFAULT_CONFIG


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> dict:
    cfg = _read_yaml(DEFAULT_CONFIG)
    llm = cfg.setdefault("llm", {})
    llm["base_url"] = (
        llm.get("base_url")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    llm["api_key"] = llm.get("api_key") or os.environ.get("OPENAI_API_KEY") or ""
    llm["model"] = os.environ.get("DRAFT_MODEL") or llm.get("model") or "gpt-4o-mini"
    adb_env = os.environ.get("ADB_PATH")
    if adb_env:
        cfg.setdefault("adb", {})["path"] = adb_env
    return cfg


def deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out
