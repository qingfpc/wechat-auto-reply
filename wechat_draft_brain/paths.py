from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "夜班台"


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    path = root / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def icon_path() -> Path:
    bundled = resource_root() / "icon.ico"
    if bundled.exists():
        return bundled
    return resource_root() / "packaging" / "icon.ico"


RESOURCE_ROOT = resource_root()
DATA_DIR = user_data_dir()
CONFIG_DIR = RESOURCE_ROOT / "config"
DEFAULT_CONFIG = CONFIG_DIR / "default.yaml"
USER_CONFIG = DATA_DIR / "user.yaml"
DB_PATH = DATA_DIR / "brain.sqlite3"
LAST_SHOT = DATA_DIR / "last_screen.png"
