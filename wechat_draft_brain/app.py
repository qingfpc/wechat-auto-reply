from __future__ import annotations


def main() -> None:
    try:
        from wechat_draft_brain.ui.main_window import run
    except ImportError as e:
        raise SystemExit("请先安装 PySide6：pip install PySide6") from e
    raise SystemExit(run())


if __name__ == "__main__":
    main()
