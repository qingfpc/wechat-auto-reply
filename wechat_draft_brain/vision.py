from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

import numpy as np
from PIL import Image, ImageGrab

_ocr = None


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


def parse_chat(items: list[dict[str, Any]], width: int, incoming_max_x: float, outgoing_min_x: float) -> str:
    lines = []
    skip = ("发送", "按住 说话", "搜一搜", "视频通话", "语音通话")
    for it in items:
        text = it["text"]
        if not text or any(s in text for s in skip):
            continue
        if len(text) <= 5 and ":" in text and text.replace(":", "").replace("：", "").isdigit():
            continue
        ratio = it["x"] / max(width, 1)
        if ratio <= incoming_max_x:
            lines.append(f"对方: {text}")
        elif ratio >= outgoing_min_x:
            lines.append(f"我: {text}")
        else:
            lines.append(text)
    return "\n".join(lines).strip()


def guess_title(items: list[dict[str, Any]], width: int, height: int) -> str:
    for it in items:
        if it["top"] < height * 0.12 and 0.18 * width < it["x"] < 0.82 * width:
            if 1 < len(it["text"]) < 20:
                return it["text"]
    return ""


def clipboard_text() -> str:
    try:
        import pyperclip

        return (pyperclip.paste() or "").strip()
    except Exception:
        return ""


def grab_foreground_window() -> Image.Image | None:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    if bbox[2] - bbox[0] < 80 or bbox[3] - bbox[1] < 80:
        return None
    return ImageGrab.grab(bbox=bbox)


def capture_context(prefer_clipboard: bool = True) -> tuple[str, Image.Image | None]:
    clip = clipboard_text() if prefer_clipboard else ""
    image = grab_foreground_window()
    if clip and len(clip) >= 2:
        return clip, image
    if image is None:
        return "", None
    items = ocr_image(image)
    title = guess_title(items, image.size[0], image.size[1])
    body = parse_chat(items, image.size[0], 0.48, 0.52)
    if title and body:
        return f"[会话] {title}\n{body}", image
    return body or title, image
