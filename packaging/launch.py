from __future__ import annotations

import os
import traceback
from pathlib import Path


def _write_startup_error() -> None:
    try:
        appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        log_dir = appdata / "夜班台"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
    except Exception:
        pass

if __name__ == "__main__":
    try:
        from wechat_draft_brain.app import main

        main()
    except Exception:
        _write_startup_error()
        raise
