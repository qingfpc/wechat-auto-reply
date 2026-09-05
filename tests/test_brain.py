from wechat_draft_brain.brain import _last_incoming, classify_scene, decide_action, run_brain


def test_money_is_queued():
    scene, _ = classify_scene("你先转我三百")
    assert scene == "money"
    action, risks, _ = decide_action(
        scene,
        mode="auto",
        dry_run=False,
        auto_armed=True,
        auto_scenes=["smalltalk", "logistics"],
        sent_last_hour=0,
        max_auto_per_hour=20,
    )
    assert action == "queue"
    assert risks


def test_smalltalk_can_autosend():
    scene, _ = classify_scene("在吗")
    assert scene == "smalltalk"
    action, _, _ = decide_action(
        scene,
        mode="auto",
        dry_run=False,
        auto_armed=True,
        auto_scenes=["smalltalk", "logistics"],
        sent_last_hour=0,
        max_auto_per_hour=20,
    )
    assert action == "auto_send"


def test_copilot_never_autosends():
    r = run_brain("在吗", {"llm": {}, "policy": {}}, mode="copilot", dry_run=True, auto_armed=True)
    assert r.action == "queue"
    assert r.drafts


def test_last_incoming_skips_metadata_system_unknown_and_own_messages():
    source = "\n".join(
        [
            "[会话] 测试群(3)",
            "对方(小明): 在吗",
            "我: 在的",
            "系统: 小明撤回了一条消息",
            "未知: [文字识别不清]",
        ]
    )
    assert _last_incoming(source) == "在吗"


def test_run_brain_classifies_only_latest_incoming_message():
    source = "\n".join(
        [
            "[会话] 老高",
            "对方: 你先转我三百",
            "我: 我核对一下",
            "对方: 在吗",
        ]
    )

    result = run_brain(
        source,
        {"llm": {}, "policy": {}},
        mode="copilot",
        dry_run=True,
        auto_armed=False,
    )

    assert result.scene == "smalltalk"
    assert result.risks == []


def test_run_brain_keeps_risk_when_latest_incoming_message_is_money():
    source = "\n".join(
        [
            "[会话] 老高",
            "对方: 在吗",
            "我: 在的",
            "对方: 你先转我三百",
        ]
    )

    result = run_brain(
        source,
        {"llm": {}, "policy": {}},
        mode="copilot",
        dry_run=True,
        auto_armed=False,
    )

    assert result.scene == "money"
    assert result.risks == ["必须你确认后再发"]
