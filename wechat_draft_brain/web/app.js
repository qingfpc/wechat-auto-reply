const $ = (id) => document.getElementById(id);

const SCENE = {
  smalltalk: "寒暄",
  logistics: "事务确认",
  favor: "请求帮忙",
  money: "金钱",
  emotion: "情绪/亲密",
  work: "工作决策",
  spam: "广告/无关",
  unknown: "未分类",
};

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderState(s) {
  document.body.classList.toggle("is-auto", s.mode === "auto");
  document.querySelectorAll("#modeSwitch button").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.mode === s.mode);
  });
  $("modeLabel").textContent = s.mode === "auto" ? "全自动 OCR+ADB" : "快捷键拟稿";
  $("modeHint").textContent =
    s.mode === "auto"
      ? `每 ${s.poll_seconds} 秒扫一次手机未读。高风险情景仍会停在队列。`
      : `${s.hotkey} 抓当前微信窗口或剪贴板，只出草稿不发送。`;
  $("adbLine").textContent = s.adb?.ok ? `在线 ${s.adb.device}` : s.adb?.error || "未连接";
  $("llmLine").textContent = s.llm_ready ? s.model : "未配置 API Key，走规则拟稿";
  $("dryRun").checked = !!s.dry_run;
  $("armed").checked = !!s.auto_armed;

  const q = $("queue");
  q.innerHTML = "";
  (s.drafts || []).forEach((d) => {
    const el = document.createElement("article");
    el.className = "card";
    const drafts = (d.drafts || [])
      .map(
        (t) =>
          `<button data-copy="${encodeURIComponent(t)}" data-id="${d.id}">${escapeHtml(t)}</button>`
      )
      .join("");
    el.innerHTML = `
      <div class="meta">#${d.id} · ${escapeHtml(d.contact || "未知")} · ${SCENE[d.scene] || d.scene} · ${d.action} · ${d.status}</div>
      <div class="${d.risks?.length ? "risk" : ""}">${escapeHtml(d.reason || "")}</div>
      <pre style="white-space:pre-wrap;color:var(--mute);font-size:12px">${escapeHtml((d.source_text || "").slice(0, 280))}</pre>
      <div class="candidates">${drafts}</div>
      <button data-dismiss="${d.id}">丢掉</button>
    `;
    q.appendChild(el);
  });

  const log = $("log");
  log.innerHTML = "";
  (s.events || []).forEach((e) => {
    const li = document.createElement("li");
    const t = new Date(e.created_at * 1000).toLocaleTimeString();
    li.textContent = `${t}  ${e.message}`;
    log.appendChild(li);
  });

  if (s.last_shot) {
    $("shot").src = `/api/last-shot?t=${Date.now()}`;
    $("shot").classList.add("show");
  }
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function refresh() {
  const s = await api("/api/state");
  renderState(s);
}

document.querySelectorAll("#modeSwitch button").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const mode = btn.dataset.mode;
    if (mode === "auto") {
      const ok = confirm(
        "切换到 OCR+ADB 全自动会定时截手机屏并尝试点开发送。\n默认仍是空跑。只有同时关闭「空跑」并打开「解除保险」才会真的发出去。\n个人微信有封号风险，确定吗？"
      );
      if (!ok) return;
    }
    await api("/api/mode", { method: "POST", body: JSON.stringify({ mode }) });
    refresh();
  });
});

$("dryRun").addEventListener("change", async (e) => {
  await api("/api/mode", {
    method: "POST",
    body: JSON.stringify({ mode: document.body.classList.contains("is-auto") ? "auto" : "copilot", dry_run: e.target.checked }),
  });
  refresh();
});

$("armed").addEventListener("change", async (e) => {
  if (e.target.checked) {
    const ok = confirm("解除保险后，全自动模式里的寒暄/事务确认可能会被真的发出去。确定？");
    if (!ok) {
      e.target.checked = false;
      return;
    }
  }
  await api("/api/mode", {
    method: "POST",
    body: JSON.stringify({
      mode: document.body.classList.contains("is-auto") ? "auto" : "copilot",
      auto_armed: e.target.checked,
    }),
  });
  refresh();
});

$("draftBtn").addEventListener("click", async () => {
  const text = $("source").value.trim();
  if (!text) return;
  await api("/api/draft", {
    method: "POST",
    body: JSON.stringify({ text, contact: $("contact").value.trim() }),
  });
  $("source").value = "";
  refresh();
});

$("queue").addEventListener("click", async (e) => {
  const t = e.target;
  if (t.dataset.copy) {
    const text = decodeURIComponent(t.dataset.copy);
    await navigator.clipboard.writeText(text);
    await api(`/api/drafts/${t.dataset.id}/decide`, {
      method: "POST",
      body: JSON.stringify({ status: "copied", chosen_text: text }),
    });
    refresh();
  }
  if (t.dataset.dismiss) {
    await api(`/api/drafts/${t.dataset.dismiss}/decide`, {
      method: "POST",
      body: JSON.stringify({ status: "dismissed" }),
    });
    refresh();
  }
});

refresh();
setInterval(refresh, 2500);
