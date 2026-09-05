from PIL import Image

from wechat_draft_brain.config import normalize_capture, normalize_theme
from wechat_draft_brain.vision import (
    capture_context,
    chat_pane_box,
    detect_sidebar_split,
    guess_title,
    looks_like_timestamp,
    parse_chat,
    select_capture_text,
)


def _item(text: str, x: float, y: float, top: float | None = None) -> dict:
    return {
        "text": text,
        "score": 0.9,
        "x": x,
        "y": y,
        "left": x - 20,
        "top": top if top is not None else y - 8,
        "right": x + 40,
        "bottom": y + 8,
    }


def test_sidebar_box_excludes_session_list():
    left, _, _, _ = chat_pane_box(1200, 800, {"sidebar_px": 360}, dpi=1.0)
    assert left == 360
    sidebar_name = _item("张三", 90, 180)
    bubble = _item("晚上见", 520, 240)
    assert sidebar_name["x"] < left
    assert bubble["x"] > left


def test_high_dpi_widens_sidebar_cut():
    left, _, _, _ = chat_pane_box(1920, 1080, {"sidebar_px": 360}, dpi=1.5)
    assert left == 540


def test_parse_chat_drops_sidebar_names():
    left, top, right, bottom = chat_pane_box(1200, 800, {"sidebar_px": 360}, dpi=1.0)
    items = [
        _item("张三", 80, 120),
        _item("李四", 90, 180),
        _item("晚上还出不出来", 500, 260),
        _item("我看一下", 920, 320),
    ]
    pane = [it for it in items if left <= it["x"] <= right and top <= it["y"] <= bottom]
    shifted = [
        {
            **it,
            "x": it["x"] - left,
            "left": it["left"] - left,
            "right": it["right"] - left,
        }
        for it in pane
    ]
    text = parse_chat(shifted, right - left, 0.48, 0.52)
    assert "张三" not in text
    assert "李四" not in text
    assert "对方: 晚上还出不出来" in text
    assert "我: 我看一下" in text


def test_guess_title_uses_chat_header_not_sidebar():
    title = guess_title(
        [
            _item("同事群", 70, 24, top=10),
            _item("晚上见", 200, 200, top=190),
        ],
        width=840,
        height=800,
    )
    assert title == "同事群"


def test_capture_defaults_to_ocr_and_ignores_clipboard():
    assert normalize_capture(None) == "ocr"
    assert normalize_capture("CLIPBOARD") == "clipboard"
    assert normalize_capture("nope") == "ocr"
    clip = "剪贴板里的无关内容"
    ocr = "对方: 晚上见"
    assert select_capture_text(ocr=ocr, clipboard=clip, source="ocr") == ocr
    assert select_capture_text(ocr=ocr, clipboard=clip, source="clipboard") == clip
    assert select_capture_text(ocr="", clipboard=clip, source="both") == clip
    assert select_capture_text(ocr=ocr, clipboard=clip, source="both") == ocr


def test_theme_defaults_to_dark():
    assert normalize_theme(None) == "dark"
    assert normalize_theme("LIGHT") == "light"
    assert normalize_theme("nope") == "dark"


def _two_tone(width: int, height: int, split: int) -> Image.Image:
    """左侧会话列表比右侧聊天区亮一点，模拟微信深色模式的背景分界。"""
    image = Image.new("RGB", (width, height), (13, 13, 13))
    image.paste(Image.new("RGB", (split, height), (40, 40, 40)), (0, 0))
    return image


def test_detect_sidebar_split_finds_background_step():
    assert detect_sidebar_split(_two_tone(1000, 800, 280)) == 280
    assert detect_sidebar_split(_two_tone(1423, 745, 220)) == 220


def test_detect_sidebar_split_gives_up_without_contrast():
    assert detect_sidebar_split(Image.new("RGB", (1000, 800), (20, 20, 20))) is None


def test_detected_split_beats_configured_sidebar_px():
    left, _, _, _ = chat_pane_box(
        1423, 745, {"sidebar_px": 360}, dpi=1.0, sidebar_override=220
    )
    assert left == 220


def test_parse_chat_drops_title_band():
    items = [_item("老高", 40, 55), _item("马上要开了", 200, 146)]
    text = parse_chat(items, 1066, 0.48, 0.52, header_bottom=78)
    assert "老高" not in text
    assert "对方: 马上要开了" in text


def test_guess_title_skips_timestamp_and_reaches_left_edge():
    title = guess_title(
        [_item("18:47", 500, 60, top=50), _item("老高", 20, 70, top=60)],
        width=1066,
        height=670,
    )
    assert title == "老高"


def test_looks_like_timestamp():
    assert looks_like_timestamp("18:47")
    assert looks_like_timestamp("9：05")
    assert looks_like_timestamp("18:47:02")
    assert not looks_like_timestamp("老高")
    assert not looks_like_timestamp("3:2 拿下")


def test_capture_requires_an_incoming_message(monkeypatch):
    image = Image.new("RGB", (800, 500), (30, 30, 30))
    monkeypatch.setattr("wechat_draft_brain.vision.grab_foreground_window", lambda: (image, 1.0))
    monkeypatch.setattr("wechat_draft_brain.vision.crop_chat_pane", lambda value, layout, dpi: value)
    monkeypatch.setattr(
        "wechat_draft_brain.vision.ocr_image",
        lambda value: [_item("测试会话", 40, 50), _item("我刚发过了", 700, 140)],
    )
    result = capture_context("ocr", {"header_px": 78})
    assert result.text == ""
    assert result.image is image
    assert result.contact == "测试会话"


def test_capture_includes_title_when_there_is_an_incoming_message(monkeypatch):
    image = Image.new("RGB", (800, 500), (30, 30, 30))
    monkeypatch.setattr("wechat_draft_brain.vision.grab_foreground_window", lambda: (image, 1.0))
    monkeypatch.setattr("wechat_draft_brain.vision.crop_chat_pane", lambda value, layout, dpi: value)
    monkeypatch.setattr(
        "wechat_draft_brain.vision.ocr_image",
        lambda value: [_item("测试会话", 40, 50), _item("在吗", 100, 140)],
    )
    result = capture_context("ocr", {"header_px": 78})
    assert result.text == "[会话] 测试会话\n对方: 在吗"
    assert result.contact == "测试会话"
    assert [message.role for message in result.messages] == ["incoming"]

