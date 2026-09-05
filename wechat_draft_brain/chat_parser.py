from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import Any, Literal, TypedDict

import numpy as np
from PIL import Image

Role = Literal["incoming", "outgoing", "system", "unknown"]
Kind = Literal["text", "voice", "media", "unknown"]
Box = tuple[float, float, float, float]


class OcrLine(TypedDict):
    text: str
    score: float
    x: float
    y: float
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    kind: Kind
    text: str
    author: str = ""
    confidence: float = 1.0
    box: Box = (0.0, 0.0, 0.0, 0.0)


@dataclass
class _Row:
    text: str
    score: float
    left: float
    top: float
    right: float
    bottom: float

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, 1.0)

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2


_TIME_LIKE = re.compile(r"^\d{1,2}[:：]\d{2}([:：]\d{2})?$")
_DATE_LIKE = re.compile(
    r"^(?:(?:昨天|今天|星期[一二三四五六日天]|周[一二三四五六日天])(?:\s+\d{1,2}[:：]\d{2})?|"
    r"\d{1,2}月\d{1,2}日(?:\s+\d{1,2}[:：]\d{2})?)$"
)
_GROUP_TITLE = re.compile(r"[（(]\s*\d+\s*[）)]$")
_NEW_MESSAGES = re.compile(r"^\d+\s*条新消息$")
_VOICE_LIKE = re.compile(r"^[()（）]?\s*(\d{1,3})\s*(?:秒|s|S|[\"'”″])\s*$")
_ONLY_SYMBOLS = re.compile(r"^[\s.…·+＋_—\-|｜/\\()（）\[\]【】'\"“”]+$")
_SYSTEM_HINTS = ("撤回了一条消息", "以下为新消息", "你已添加了", "已成为好友")
_NOISE_TEXTS = {
    "发送",
    "按住 说话",
    "搜一搜",
    "视频通话",
    "语音通话",
    "由微信提供翻译支持",
}


def looks_like_timestamp(text: str) -> bool:
    return bool(_TIME_LIKE.match((text or "").strip()))


def is_group_title(title: str) -> bool:
    return bool(_GROUP_TITLE.search((title or "").strip()))


def _normalize(item: dict[str, Any]) -> _Row | None:
    text = str(item.get("text") or "").strip()
    if not text:
        return None
    left = float(item.get("left", item.get("x", 0.0)))
    right = float(item.get("right", item.get("x", left)))
    top = float(item.get("top", item.get("y", 0.0)))
    bottom = float(item.get("bottom", item.get("y", top)))
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top
    return _Row(text, float(item.get("score", 1.0)), left, top, right, bottom)


def _is_noise(text: str) -> bool:
    value = (text or "").strip()
    if not value or looks_like_timestamp(value) or _DATE_LIKE.match(value) or _NEW_MESSAGES.match(value):
        return True
    if value in _NOISE_TEXTS:
        return True
    return len(value) <= 4 and bool(_ONLY_SYMBOLS.match(value))


def _is_system(text: str) -> bool:
    return any(hint in text for hint in _SYSTEM_HINTS)


def _join_fragments(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    a, b = left[-1], right[0]
    if a.isspace() or b.isspace():
        return left + right
    if "\u4e00" <= a <= "\u9fff" or "\u4e00" <= b <= "\u9fff":
        return left + right
    if a in "，。！？；：、,.!?;:(（[【" or b in "，。！？；：、,.!?;:)）]】":
        return left + right
    return left + " " + right


def _vertical_overlap(a: _Row, b: _Row) -> float:
    overlap = max(0.0, min(a.bottom, b.bottom) - max(a.top, b.top))
    return overlap / max(min(a.height, b.height), 1.0)


def _merge_same_visual_rows(rows: list[_Row], width: int) -> list[_Row]:
    if not rows:
        return []
    result: list[_Row] = []
    for row in sorted(rows, key=lambda value: (value.top, value.left)):
        if not result:
            result.append(row)
            continue
        current = result[-1]
        gap = row.left - current.right
        max_gap = max(1.5 * max(current.height, row.height), width * 0.08)
        if _vertical_overlap(current, row) >= 0.60 and -max(current.height, row.height) <= gap <= max_gap:
            total = max(len(current.text) + len(row.text), 1)
            score = (current.score * len(current.text) + row.score * len(row.text)) / total
            result[-1] = _Row(
                _join_fragments(current.text, row.text),
                score,
                min(current.left, row.left),
                min(current.top, row.top),
                max(current.right, row.right),
                max(current.bottom, row.bottom),
            )
        else:
            result.append(row)
    return result


def _role_for_box(box: Box, width: int, incoming_max_x: float, outgoing_min_x: float) -> Role:
    center = (box[0] + box[2]) / 2 / max(width, 1)
    if center <= incoming_max_x:
        return "incoming"
    if center >= outgoing_min_x:
        return "outgoing"
    return "unknown"


def _looks_like_author(row: _Row, next_row: _Row, width: int, line_height: float) -> bool:
    gap = next_row.top - row.bottom
    if not (line_height * 0.20 <= gap <= line_height * 1.80):
        return False
    left_offset = next_row.left - row.left
    if not (max(4.0, width * 0.005) <= left_offset <= width * 0.06):
        return False
    if not (1 <= len(row.text) <= 20) or row.right - row.left > width * 0.32:
        return False
    if re.search(r"[。！？!?，,：:]$", row.text):
        return False
    return True


def _message_box(rows: list[_Row]) -> Box:
    return (
        min(row.left for row in rows),
        min(row.top for row in rows),
        max(row.right for row in rows),
        max(row.bottom for row in rows),
    )


def _can_merge(rows: list[_Row], row: _Row, width: int, line_height: float) -> bool:
    previous = rows[-1]
    gap = row.top - previous.bottom
    if gap < -line_height * 0.35 or gap > line_height * 1.50:
        return False
    box = _message_box(rows)
    tolerance = max(12.0, width * 0.025)
    aligned_left = abs(box[0] - row.left) <= tolerance
    aligned_right = abs(box[2] - row.right) <= tolerance
    return aligned_left or aligned_right


def _message_from_rows(
    rows: list[_Row],
    width: int,
    incoming_max_x: float,
    outgoing_min_x: float,
    min_score: float,
    author: str = "",
) -> ChatMessage:
    box = _message_box(rows)
    role = _role_for_box(box, width, incoming_max_x, outgoing_min_x)
    scores = [row.score for row in rows]
    voice = _VOICE_LIKE.match(rows[0].text) if len(rows) == 1 else None
    if voice:
        seconds = voice.group(1)
        return ChatMessage(role, "voice", f"[语音 {seconds}秒]", author, scores[0], box)

    if all(score < min_score for score in scores):
        text = "[文字识别不清]"
        kind: Kind = "unknown"
    else:
        text = ""
        for row in rows:
            part = row.text if row.score >= min_score else "[部分文字识别不清]"
            if part == "[部分文字识别不清]" and text.endswith(part):
                continue
            text = _join_fragments(text, part)
        kind = "text"
    confidence = sum(scores) / max(len(scores), 1)
    return ChatMessage(role, kind, text, author, confidence, box)


def _overlaps_text(box: Box, messages: list[ChatMessage]) -> bool:
    left, top, right, bottom = box
    for message in messages:
        ml, mt, mr, mb = message.box
        if min(right, mr) > max(left, ml) and min(bottom, mb) > max(top, mt):
            return True
    return False


def _detect_media_messages(
    image: Image.Image,
    messages: list[ChatMessage],
    header_bottom: float,
    incoming_max_x: float,
    outgoing_min_x: float,
) -> list[ChatMessage]:
    try:
        import cv2
    except ImportError:
        return []

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    top = max(int(header_bottom), 0)
    bottom = min(int(height * 0.82), height)
    if bottom - top < 80:
        return []
    band = rgb[top:bottom]
    background = np.median(band.reshape(-1, 3), axis=0)
    distance = np.max(np.abs(band.astype(np.int16) - background.astype(np.int16)), axis=2)
    mask = (distance > 22).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates: list[ChatMessage] = []
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        y += top
        if box_width < 60 or box_height < 60:
            continue
        if box_width > width * 0.55 or box_height > height * 0.55:
            continue
        aspect = box_width / max(box_height, 1)
        if not 0.45 <= aspect <= 2.8:
            continue
        box = (float(x), float(y), float(x + box_width), float(y + box_height))
        if _overlaps_text(box, messages):
            continue
        region = rgb[y : y + box_height, x : x + box_width]
        if not region.size or float(region.std()) < 18:
            continue
        role = _role_for_box(box, width, incoming_max_x, outgoing_min_x)
        if role == "unknown":
            continue
        candidates.append(ChatMessage(role, "media", "[图片/视频]", confidence=0.8, box=box))

    candidates.sort(key=lambda message: (-(message.box[2] - message.box[0]) * (message.box[3] - message.box[1])))
    selected: list[ChatMessage] = []
    for candidate in candidates:
        if _overlaps_text(candidate.box, selected):
            continue
        selected.append(candidate)
    return selected


def parse_chat_items(
    items: list[dict[str, Any]],
    width: int,
    incoming_max_x: float,
    outgoing_min_x: float,
    header_bottom: float = 0.0,
    *,
    image: Image.Image | None = None,
    is_group: bool = False,
    min_score: float = 0.75,
) -> list[ChatMessage]:
    rows = []
    for item in items:
        row = _normalize(item)
        if row is None or (header_bottom and row.bottom <= header_bottom) or _is_noise(row.text):
            continue
        rows.append(row)
    rows = _merge_same_visual_rows(rows, width)
    line_height = float(median(row.height for row in rows)) if rows else 18.0

    authors: dict[int, str] = {}
    author_rows: set[int] = set()
    if is_group:
        for index in range(len(rows) - 1):
            row, next_row = rows[index], rows[index + 1]
            next_role = _role_for_box(
                (next_row.left, next_row.top, next_row.right, next_row.bottom),
                width,
                incoming_max_x,
                outgoing_min_x,
            )
            if next_role == "incoming" and _looks_like_author(row, next_row, width, line_height):
                authors[index + 1] = row.text
                author_rows.add(index)

    messages: list[ChatMessage] = []
    group: list[_Row] = []
    group_author = ""
    for index, row in enumerate(rows):
        if index in author_rows:
            continue
        voice = _VOICE_LIKE.match(row.text)
        if voice:
            if group:
                messages.append(
                    _message_from_rows(
                        group, width, incoming_max_x, outgoing_min_x, min_score, group_author
                    )
                )
                group = []
                group_author = ""
            messages.append(
                _message_from_rows(
                    [row], width, incoming_max_x, outgoing_min_x, min_score, authors.get(index, "")
                )
            )
            continue
        if _is_system(row.text):
            if group:
                messages.append(
                    _message_from_rows(
                        group, width, incoming_max_x, outgoing_min_x, min_score, group_author
                    )
                )
                group = []
                group_author = ""
            messages.append(
                ChatMessage("system", "text", row.text, confidence=row.score, box=(row.left, row.top, row.right, row.bottom))
            )
            continue
        author = authors.get(index, "")
        if group and not author and _can_merge(group, row, width, line_height):
            group.append(row)
            continue
        if group:
            messages.append(
                _message_from_rows(
                    group, width, incoming_max_x, outgoing_min_x, min_score, group_author
                )
            )
        group = [row]
        group_author = author
    if group:
        messages.append(
            _message_from_rows(group, width, incoming_max_x, outgoing_min_x, min_score, group_author)
        )

    if image is not None:
        messages.extend(
            _detect_media_messages(
                image, messages, header_bottom, incoming_max_x, outgoing_min_x
            )
        )
    messages.sort(key=lambda message: (message.box[1], message.box[0]))
    return messages


def render_chat(messages: list[ChatMessage]) -> str:
    lines = []
    for message in messages:
        if message.role == "incoming":
            prefix = f"对方({message.author})" if message.author else "对方"
        elif message.role == "outgoing":
            prefix = "我"
        elif message.role == "system":
            prefix = "系统"
        else:
            prefix = "未知"
        lines.append(f"{prefix}: {message.text}")
    return "\n".join(lines).strip()


def parse_chat(
    items: list[dict[str, Any]],
    width: int,
    incoming_max_x: float,
    outgoing_min_x: float,
    header_bottom: float = 0.0,
    *,
    image: Image.Image | None = None,
    is_group: bool = False,
    min_score: float = 0.75,
) -> str:
    messages = parse_chat_items(
        items,
        width,
        incoming_max_x,
        outgoing_min_x,
        header_bottom,
        image=image,
        is_group=is_group,
        min_score=min_score,
    )
    return render_chat(messages)
