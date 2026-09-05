"""临时 spike：实测每张截图里「会话列表 / 聊天区」的真实分界 x。

用来验证「侧栏宽度自适应」是否可行，以及现有 sidebar_px=360 偏了多少。

用法：
    python scripts/spike_sidebar.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
SEARCH_MIN = 120
SEARCH_MAX = 520


def detect_split(image: Image.Image) -> tuple[int, float]:
    """按列取中位数颜色，找相邻列颜色跳变最大的位置。"""
    arr = np.asarray(image.convert("RGB"), dtype=np.int16)
    # 掐掉顶部标题栏和底部输入区，只看中段，避免气泡和按钮干扰
    h = arr.shape[0]
    mid = arr[int(h * 0.12) : int(h * 0.85), :, :]
    col = np.median(mid, axis=0)                      # (width, 3)
    diff = np.abs(np.diff(col, axis=0)).sum(axis=1)   # (width-1,)
    lo, hi = SEARCH_MIN, min(SEARCH_MAX, len(diff))
    window = diff[lo:hi]
    x = int(lo + int(np.argmax(window)))
    return x + 1, float(window.max())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{'文件':<40} {'宽':>6} {'实测分界':>8} {'跳变强度':>8} {'代码用的360':>12}")
    for path in sorted(FIXTURES.glob("*.png")):
        image = Image.open(path)
        x, strength = detect_split(image)
        print(f"{path.name:<40} {image.size[0]:>6} {x:>8} {strength:>8.1f} {360 - x:>+12}")
