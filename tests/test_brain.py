from wechat_draft_brain.brain import classify_scene, decide_action, run_brain


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
