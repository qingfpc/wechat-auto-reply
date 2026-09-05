"""临时 spike：对 tests/fixtures 里的真实截图跑 OCR 管道，核对基线。

不属于主包，验收完成后可删。

用法：
    python scripts/spike_ocr_baseline.py            # 走当前管道（自动检测分界）
    python scripts/spike_ocr_baseline.py legacy     # 强制固定 sidebar_px，复现旧行为
    python scripts/spike_ocr_baseline.py summary    # 只打印脱敏结构统计
    python scripts/spike_ocr_baseline.py live       # 端到端：把微信弹到前台真截一次
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wechat_draft_brain.config import load_config
from wechat_draft_brain.chat_parser import is_group_title, parse_chat_items, render_chat
from wechat_draft_brain.vision import (
    chat_pane_box,
    detect_sidebar_split,
    guess_title,
    ocr_image,
)

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def live() -> None:
    """真实路径：GetWindowRect 截的图带窗口边框，和手工截的客户区不一样。

    后台进程调 SetForegroundWindow 会被 Windows 拦掉，所以让用户自己切过去。
    """
    import ctypes
    import time

    from wechat_draft_brain.vision import (
        capture_context,
        detect_sidebar_split,
        grab_foreground_window,
    )

    for i in range(6, 0, -1):
        print(f"\r请在 {i} 秒内点到微信窗口…", end="", flush=True)
        time.sleep(1)
    print()

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    print(f"前台窗口 class={buf.value!r}")

    image, dpi = grab_foreground_window()
    if image is None:
        print("没抓到窗口。")
        return
    cfg = load_config()
    layout = cfg.get("layout") or {}
    print(f"原图 {image.size}  dpi={dpi}  检测分界={detect_sidebar_split(image, layout)}")

    text, shot = capture_context("ocr", layout)
    print(f"裁后尺寸 {shot.size if shot else None}")
    print("-" * 78)
    print(text or "(空)")


def run(dpi: float, legacy: bool, summary: bool = False) -> None:
    cfg = load_config()
    layout = dict(cfg.get("layout") or {})
    incoming = float(layout.get("incoming_max_x") or 0.48)
    outgoing = float(layout.get("outgoing_min_x") or 0.52)
    header = float(layout.get("header_px") or 78) * max(dpi, 0.75)
    mode = f"固定 sidebar_px={layout.get('sidebar_px')}" if legacy else "自动检测分界"
    print(f"模式={mode}  dpi={dpi}  header_bottom={header:.0f}\n")

    for path in sorted(FIXTURES.glob("*.png")):
        image = Image.open(path)
        split = None if legacy else detect_sidebar_split(image, layout)
        box = chat_pane_box(*image.size, layout, dpi, sidebar_override=split)
        pane = image.crop(box)
        items = ocr_image(pane)
        title = guess_title(items, pane.size[0], pane.size[1])
        messages = parse_chat_items(
            items,
            pane.size[0],
            incoming,
            outgoing,
            header_bottom=0.0 if legacy else header,
            image=None if legacy else pane,
            is_group=is_group_title(title),
            min_score=float(layout.get("ocr_min_score") or 0.75),
        )
        body = render_chat(messages)

        if summary:
            roles = {role: sum(message.role == role for message in messages) for role in ("incoming", "outgoing", "system", "unknown")}
            kinds = {kind: sum(message.kind == kind for message in messages) for kind in ("text", "voice", "media", "unknown")}
            print(
                f"{path.name}  分界={split}  标题={'有' if title else '无'}  "
                f"群聊={is_group_title(title)}  消息={len(messages)}  "
                f"昵称={sum(bool(message.author) for message in messages)}  "
                f"角色={roles}  类型={kinds}"
            )
        else:
            print("=" * 78)
            print(f"{path.name}  原图 {image.size[0]}x{image.size[1]}  "
                  f"检测分界={split}  裁剪框 {box}")
            print(f"guess_title -> {title!r}")
            print("-" * 78)
            print(body or "(空)")
            print()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if "live" in args:
        live()
    else:
        legacy = "legacy" in args
        summary = "summary" in args
        dpi = next((float(a) for a in args if a not in {"legacy", "summary"}), 1.0)
        run(dpi, legacy, summary)
