from __future__ import annotations

from dataclasses import dataclass, field

import httpx

SCENE_LABELS = {
    "smalltalk": "寒暄",
    "logistics": "事务确认",
    "favor": "请求帮忙",
    "money": "金钱",
    "emotion": "情绪/亲密",
    "work": "工作决策",
    "spam": "广告/无关",
    "unknown": "未分类",
}

_SCENE_HINTS = {
    "money": ("转账", "转我", "红包", "多少钱", "报销", "借钱", "打款", "收款", "工资"),
    "emotion": ("想你", "分手", "生气", "委屈", "哭", "抱抱", "想我"),
    "favor": ("帮我", "能不能", "可不可以", "求你", "麻烦你", "帮看一下"),
    "work": ("方案", "排期", "截止日期", "客户", "汇报", "合同", "上线"),
    "spam": ("优惠", "点击领取", "加微信领", "代理招商", "免费领取"),
    "logistics": ("收到", "地址", "几点", "到了", "定位", "会议室", "改到"),
    "smalltalk": ("在吗", "吃了吗", "晚安", "早安", "哈哈", "嗯嗯", "好的", "ok"),
}


@dataclass
class BrainResult:
    contact: str
    scene: str
    confidence: float
    action: str
    risks: list[str]
    drafts: list[str]
    reason: str
    source_text: str
    contact_guess: str = ""
    extra: dict = field(default_factory=dict)


def classify_scene(text: str) -> tuple[str, float]:
    blob = (text or "").strip().lower()
    if not blob:
        return "unknown", 0.2
    scores: dict[str, int] = {}
    for scene, words in _SCENE_HINTS.items():
        hit = sum(1 for w in words if w.lower() in blob)
        if hit:
            scores[scene] = hit
    if not scores:
        return "unknown", 0.4
    scene = max(scores, key=scores.get)
    conf = min(0.95, 0.55 + 0.12 * scores[scene])
    return scene, conf


def decide_action(
    scene: str,
    *,
    mode: str,
    dry_run: bool,
    auto_armed: bool,
    auto_scenes: list[str],
    sent_last_hour: int,
    max_auto_per_hour: int,
) -> tuple[str, list[str], str]:
    risks: list[str] = []
    if scene == "spam":
        return "ignore", ["疑似广告"], "默认忽略，不拟稿。"
    if scene in {"money", "emotion", "favor", "work"}:
        risks.append("必须你确认后再发")
        return "queue", risks, "高风险情景，即使全自动模式也只进待确认队列。"
    if scene not in auto_scenes and scene != "unknown":
        return "queue", risks, "当前情景不在自动白名单。"
    if mode != "auto":
        return "queue", risks, "快捷键拟稿模式：只出草稿，不发送。"
    if not auto_armed:
        return "queue", ["全自动未解除保险"], "模式是自动，但保险开关未打开。"
    if dry_run:
        return "queue", ["空跑中"], "dry_run 开启，不会真的点击发送。"
    if sent_last_hour >= max_auto_per_hour:
        return "queue", ["超过每小时自动发送上限"], "防止刷屏。"
    if scene == "unknown":
        return "queue", ["情景不确定"], "不确定时不自动发。"
    return "auto_send", risks, "低风险情景，允许自动发送。"


def _heuristic_drafts(scene: str, last_line: str) -> list[str]:
    last_line = last_line.strip()[:80]
    if scene == "smalltalk":
        return ["在的", "嗯嗯，怎么了", "刚看到"]
    if scene == "logistics":
        return ["收到", "好，我记下了", "行，到时候再说一声"]
    if scene == "favor":
        return ["我先看一下，回头回你", "这个我得想想，稍等", "现在不方便，晚点说"]
    if scene == "money":
        return ["我看一下，稍后回你", "这笔我核对下再回复"]
    if scene == "emotion":
        return ["我在，你说", "今晚有空细聊"]
    if scene == "work":
        return ["我先看材料，有结论再回你", "这条我下班前给你准信"]
    return [f"看到了：{last_line[:20]}", "刚忙完，什么事？", "稍后回你"]


def _last_incoming(source_text: str) -> str:
    lines = [ln.strip() for ln in (source_text or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith(("我:", "我：", "[会话]", "系统:", "系统：", "未知:", "未知：")):
            continue
        return ln.split(":", 1)[-1].split("：", 1)[-1].strip()
    return ""


def _llm_drafts(cfg: dict, scene: str, source_text: str) -> list[str] | None:
    llm = cfg.get("llm") or {}
    api_key = llm.get("api_key")
    if not api_key:
        return None
    prompt = (
        "你在帮用户拟微信回复。只根据对话写出3条短回复，像真人手机打字："
        "短、口语、不要排比、不要客服腔。每条一行，不要编号。\n"
        f"情景:{SCENE_LABELS.get(scene, scene)}\n"
        f"对话:\n{source_text[-2000:]}"
    )
    url = llm["base_url"].rstrip("/") + "/chat/completions"
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": llm.get("model") or "gpt-4o-mini",
                "temperature": 0.6,
                "messages": [
                    {"role": "system", "content": "只输出3行候选回复，不要解释。"},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=25,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return None
    lines = [ln.strip(" -•\t") for ln in text.splitlines() if ln.strip()]
    return lines[:3] or None


def run_brain(
    source_text: str,
    cfg: dict,
    *,
    mode: str,
    dry_run: bool,
    auto_armed: bool,
    contact: str = "",
    sent_last_hour: int = 0,
) -> BrainResult:
    scene, conf = classify_scene(source_text)
    policy = cfg.get("policy") or {}
    auto_scenes = policy.get("auto_scenes") or ["smalltalk", "logistics"]
    max_auto = int(policy.get("max_auto_per_hour") or 20)
    action, risks, reason = decide_action(
        scene,
        mode=mode,
        dry_run=dry_run,
        auto_armed=auto_armed,
        auto_scenes=auto_scenes,
        sent_last_hour=sent_last_hour,
        max_auto_per_hour=max_auto,
    )
    last_line = _last_incoming(source_text)
    drafts = _llm_drafts(cfg, scene, source_text) or _heuristic_drafts(scene, last_line)
    if action == "ignore":
        drafts = []
    return BrainResult(
        contact=contact or "未知会话",
        scene=scene,
        confidence=conf,
        action=action,
        risks=risks,
        drafts=drafts,
        reason=reason,
        source_text=source_text,
        contact_guess=contact,
    )
