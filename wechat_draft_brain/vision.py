from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageGrab

from wechat_draft_brain.chat_parser import (
    ChatMessage,
    is_group_title,
    looks_like_timestamp,
    parse_chat,
    parse_chat_items,
    render_chat,
)
from wechat_draft_brain.config import normalize_capture

_ocr = None


@dataclass
class CaptureResult:
    text: str
    image: Image.Image | None
    contact: str = ""
    messages: list[ChatMessage] = field(default_factory=list)
    is_group: bool = False
    warnings: list[str] = field(default_factory=list)


def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr = RapidOCR()
    return _ocr


def ocr_image(image: Image.Image) -> list[dict[str, Any]]:
    arr = np.array(image.convert("RGB"))
    result, _ = get_ocr()(arr)
    items = []
    if not result:
        return items
    for box, text, score in result:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append(
            {
                "text": str(text).strip(),
                "score": float(score),
                "x": float(sum(xs) / 4),
                "y": float(sum(ys) / 4),
                "left": float(min(xs)),
                "top": float(min(ys)),
                "right": float(max(xs)),
                "bottom": float(max(ys)),
            }
        )
    items.sort(key=lambda it: (it["y"], it["x"]))
    return items


def find_text(items: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    for it in items:
        if needle in it["text"]:
            return it
    return None


def find_red_badges(image: Image.Image, region: tuple[float, float, float, float]) -> list[tuple[int, int]]:
    import cv2

    w, h = image.size
    l, t, r, b = region
    x1, y1, x2, y2 = int(w * l), int(h * t), int(w * r), int(h * b)
    crop = np.array(image.convert("RGB"))[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    m1 = cv2.inRange(hsv, (0, 80, 90), (10, 255, 255))
    m2 = cv2.inRange(hsv, (160, 80, 90), (180, 255, 255))
    mask = cv2.bitwise_or(m1, m2)
    mask = cv2.medianBlur(mask, 5)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    points = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 18 or area > 900:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(c)
        if radius < 3 or radius > 22:
            continue
        points.append((x1 + int(cx), y1 + int(cy)))
    points.sort(key=lambda p: p[1])
    return points


def detect_sidebar_split(image: Image.Image, layout: dict | None = None) -> int | None:
    """找会话列表和聊天区之间的背景色分界，返回聊天区左边界。

    列表宽度会随用户拖动和窗口大小变化，固定像素值靠不住。按列取中位数颜色再看
    相邻列的跳变，气泡只占部分高度，取中位数就能把它们压掉。跳变不明显时返回
    None，由调用方回落到配置里的 sidebar_px。
    """
    layout = layout or {}
    arr = np.asarray(image.convert("RGB"), dtype=np.int16)
    height, width = arr.shape[0], arr.shape[1]
    lo = int(layout.get("sidebar_min_px", 150))
    hi = min(int(width * float(layout.get("sidebar_max_ratio", 0.42))), width - 1)
    if hi - lo < 8:
        return None
    band = arr[int(height * 0.12) : int(height * 0.85), :, :]
    if band.shape[0] < 8:
        return None
    columns = np.median(band, axis=0)
    steps = np.abs(np.diff(columns, axis=0)).sum(axis=1)
    window = steps[lo:hi]
    if float(window.max()) < float(layout.get("sidebar_min_contrast", 30)):
        return None
    return lo + int(np.argmax(window)) + 1


def chat_pane_box(
    width: int,
    height: int,
    layout: dict | None = None,
    dpi: float = 1.0,
    sidebar_override: int | None = None,
) -> tuple[int, int, int, int]:
    """微信 PC 左侧是图标栏+会话列表，只保留右侧聊天区。"""
    layout = layout or {}
    if sidebar_override is not None:
        left = int(sidebar_override)
    else:
        sidebar_px = float(layout.get("sidebar_px", 360))
        left = int(round(sidebar_px * max(float(dpi) or 1.0, 0.75)))
    max_left = int(width * float(layout.get("sidebar_max_ratio", 0.42)))
    left = min(max(left, 0), max_left, max(width - 80, 0))
    top = int(height * float(layout.get("chat_top", 0.0)))
    right = int(width * float(layout.get("chat_right", 1.0)))
    bottom = int(height * float(layout.get("chat_bottom", 0.90)))
    if right - left < 80:
        right = width
    if bottom - top < 80:
        bottom = height
    return left, top, right, min(bottom, height)


def crop_chat_pane(
    image: Image.Image,
    layout: dict | None = None,
    dpi: float = 1.0,
) -> Image.Image:
    split = detect_sidebar_split(image, layout)
    left, top, right, bottom = chat_pane_box(
        image.size[0], image.size[1], layout, dpi, sidebar_override=split
    )
    if left <= 0 and top <= 0 and right >= image.size[0] and bottom >= image.size[1]:
        return image
    return image.crop((left, top, right, bottom))


def guess_title(items: list[dict[str, Any]], width: int, height: int) -> str:
    skip = {"微信", "搜索", "聊天", "通讯录"}
    for it in items:
        if it["top"] >= height * 0.14:
            continue
        # 裁剪准确时标题会紧贴聊天区左边缘，下限不能按会话列表还在的时候设
        if not (0.005 * width < it["x"] < 0.62 * width):
            continue
        text = it["text"]
        if text in skip or looks_like_timestamp(text) or not (1 < len(text) < 20):
            continue
        return text
    return ""


def clipboard_text() -> str:
    try:
        import pyperclip

        return (pyperclip.paste() or "").strip()
    except Exception:
        return ""


def _window_dpi(hwnd: int) -> float:
    try:
        dpi = int(ctypes.windll.user32.GetDpiForWindow(hwnd))
        if dpi > 0:
            return dpi / 96.0
    except Exception:
        pass
    return 1.0


def grab_foreground_window() -> tuple[Image.Image | None, float]:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, 1.0
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None, 1.0
    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    if bbox[2] - bbox[0] < 80 or bbox[3] - bbox[1] < 80:
        return None, 1.0
    return ImageGrab.grab(bbox=bbox), _window_dpi(int(hwnd))


def select_capture_text(*, ocr: str, clipboard: str, source: str) -> str:
    source = normalize_capture(source)
    ocr = (ocr or "").strip()
    clipboard = (clipboard or "").strip()
    if source == "clipboard":
        return clipboard
    if source == "both":
        return ocr or clipboard
    return ocr


def capture_context(
    source: str = "ocr",
    layout: dict | None = None,
) -> CaptureResult:
    source = normalize_capture(source)
    image, dpi = grab_foreground_window()
    ocr_text = ""
    pane = None
    title = ""
    messages: list[ChatMessage] = []
    group_chat = False
    if source in {"ocr", "both"} and image is not None:
        pane = crop_chat_pane(image, layout, dpi)
        items = ocr_image(pane)
        title = guess_title(items, pane.size[0], pane.size[1])
        group_chat = is_group_title(title)
        incoming = float((layout or {}).get("incoming_max_x") or 0.48)
        outgoing = float((layout or {}).get("outgoing_min_x") or 0.52)
        header = float((layout or {}).get("header_px") or 78) * max(float(dpi) or 1.0, 0.75)
        messages = parse_chat_items(
            items,
            pane.size[0],
            incoming,
            outgoing,
            header_bottom=header,
            image=pane,
            is_group=group_chat,
            min_score=float((layout or {}).get("ocr_min_score") or 0.75),
        )
        body = render_chat(messages)
        has_reply_target = any(message.role == "incoming" for message in messages)
        if body and has_reply_target:
            ocr_text = f"[会话] {title}\n{body}" if title else body
    clip = clipboard_text() if source in {"clipboard", "both"} else ""
    text = select_capture_text(ocr=ocr_text, clipboard=clip, source=source)
    shot = pane if source != "clipboard" else image
    return CaptureResult(
        text=text,
        image=shot or image,
        contact=title,
        messages=messages,
        is_group=group_chat,
    )
