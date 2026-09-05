from PIL import Image

from wechat_draft_brain.chat_parser import parse_chat, parse_chat_items


def _line(
    text: str,
    left: float,
    top: float,
    right: float,
    bottom: float,
    score: float = 0.99,
) -> dict:
    return {
        "text": text,
        "score": score,
        "x": (left + right) / 2,
        "y": (top + bottom) / 2,
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
    }


def test_merges_same_row_fragments_and_long_outgoing_bubble():
    items = [
        _line("第一段", 300, 100, 500, 120),
        _line("第二段", 550, 101, 900, 121),
        _line("继续说明", 301, 123, 850, 143),
        _line("最后一行", 302, 145, 700, 165),
    ]
    assert parse_chat(items, 1000, 0.48, 0.52) == "我: 第一段第二段继续说明最后一行"


def test_merges_slightly_overlapping_fragments_on_the_same_row():
    items = [
        _line("正文", 300, 100, 700, 120),
        _line("表情", 690, 101, 760, 121),
    ]
    assert parse_chat(items, 1000, 0.48, 0.52) == "我: 正文表情"


def test_keeps_nearby_separate_bubbles_apart():
    items = [
        _line("第一条", 80, 100, 240, 120),
        _line("第二条", 80, 160, 240, 180),
    ]
    assert parse_chat(items, 1000, 0.48, 0.52).splitlines() == [
        "对方: 第一条",
        "对方: 第二条",
    ]


def test_group_author_is_attached_to_next_incoming_bubble():
    items = [
        _line("拉面", 68, 80, 120, 100),
        _line("这两个都挺好看的", 82, 109, 340, 129),
    ]
    assert parse_chat(items, 1000, 0.48, 0.52, is_group=True) == (
        "对方(拉面): 这两个都挺好看的"
    )


def test_low_confidence_text_becomes_one_placeholder():
    items = [
        _line("garbled one", 700, 100, 900, 120, score=0.50),
        _line("garbled two", 701, 122, 900, 142, score=0.60),
    ]
    assert parse_chat(items, 1000, 0.48, 0.52) == "我: [文字识别不清]"


def test_partial_low_confidence_text_is_marked_in_place():
    items = [
        _line("前半句", 80, 100, 260, 120),
        _line("garbled", 81, 122, 250, 142, score=0.50),
    ]
    assert parse_chat(items, 1000, 0.48, 0.52) == (
        "对方: 前半句[部分文字识别不清]"
    )


def test_noise_is_dropped_and_system_message_is_kept():
    items = [
        _line("18:47", 480, 90, 520, 108),
        _line("56条新消息", 800, 120, 920, 140),
        _line("由微信提供翻译支持", 300, 150, 520, 170),
        _line("小明撤回了一条消息", 400, 190, 600, 210),
    ]
    assert parse_chat(items, 1000, 0.48, 0.52) == "系统: 小明撤回了一条消息"


def test_real_message_containing_send_is_not_treated_as_toolbar_noise():
    items = [_line("请把文件发送给我", 80, 100, 300, 120)]
    assert parse_chat(items, 1000, 0.48, 0.52) == "对方: 请把文件发送给我"


def test_date_separators_are_dropped():
    items = [
        _line("昨天 18:47", 450, 80, 550, 100),
        _line("9月5日 09:30", 440, 120, 560, 140),
        _line("早上好", 80, 160, 180, 180),
    ]
    assert parse_chat(items, 1000, 0.48, 0.52) == "对方: 早上好"


def test_voice_duration_becomes_placeholder():
    items = [_line('3”', 80, 100, 125, 120, score=0.55)]
    messages = parse_chat_items(items, 1000, 0.48, 0.52)
    assert messages[0].kind == "voice"
    assert messages[0].text == "[语音 3秒]"
    assert messages[0].role == "incoming"


def test_voice_is_not_merged_with_the_following_text_bubble():
    items = [
        _line('3”', 80, 100, 125, 120, score=0.55),
        _line("看起来挺细腻", 80, 140, 260, 160),
    ]
    assert parse_chat(items, 1000, 0.48, 0.52).splitlines() == [
        "对方: [语音 3秒]",
        "对方: 看起来挺细腻",
    ]


def test_detects_media_without_text_and_does_not_duplicate_text_bubble():
    image = Image.new("RGB", (1000, 600), (30, 30, 30))
    image.paste(Image.new("RGB", (160, 120), (130, 80, 40)), (760, 120))
    image.paste(Image.new("RGB", (220, 90), (40, 180, 120)), (700, 300))
    items = [_line("这是文字气泡", 720, 325, 890, 350)]

    messages = parse_chat_items(items, 1000, 0.48, 0.52, image=image, header_bottom=78)
    media = [message for message in messages if message.kind == "media"]
    text = [message for message in messages if message.kind == "text"]
    assert len(media) == 1
    assert media[0].role == "outgoing"
    assert media[0].text == "[图片/视频]"
    assert len(text) == 1


def test_ambiguous_message_is_not_assigned_to_either_person():
    items = [_line("位置不确定", 450, 100, 550, 120)]
    assert parse_chat(items, 1000, 0.48, 0.52) == "未知: 位置不确定"
