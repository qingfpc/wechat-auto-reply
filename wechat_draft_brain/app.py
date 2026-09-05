from __future__ import annotations


def main() -> None:
    try:
        from wechat_draft_brain.ui.main_window import run
    except ImportError as e:
        raise SystemExit(f"启动组件加载失败：{e}") from e
    raise SystemExit(run())


if __name__ == "__main__":
    main()
