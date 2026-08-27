from wechat_draft_brain.config import normalize_capture, normalize_theme
from wechat_draft_brain.vision import chat_pane_box, guess_title, parse_chat, select_capture_text


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
    shifted = [{**it, "x": it["x"] - left} for it in pane]
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

