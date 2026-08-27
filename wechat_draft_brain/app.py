from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from wechat_draft_brain.config import load_config
from wechat_draft_brain.paths import LAST_SHOT, WEB_DIR
from wechat_draft_brain.pipeline import ingest_text, set_flags, snapshot, start_background
from wechat_draft_brain.store import get_draft, list_drafts, list_events, update_draft

app = FastAPI(title="wechat-draft-brain", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class DraftIn(BaseModel):
    text: str = Field(min_length=1)
    contact: str = ""


class ModeIn(BaseModel):
    mode: str
    auto_armed: bool | None = None
    dry_run: bool | None = None


class DraftDecision(BaseModel):
    status: str
    chosen_text: str = ""


@app.on_event("startup")
def _startup() -> None:
    start_background()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/state")
def api_state() -> dict:
    return {
        **snapshot(),
        "drafts": list_drafts(40),
        "events": list_events(30),
    }


@app.post("/api/mode")
def api_mode(body: ModeIn) -> dict:
    if body.mode not in {"copilot", "auto"}:
        raise HTTPException(400, "mode 只能是 copilot 或 auto")
    payload = {"mode": body.mode}
    if body.auto_armed is not None:
        payload["auto_armed"] = body.auto_armed
    if body.dry_run is not None:
        payload["dry_run"] = body.dry_run
    if body.mode == "copilot":
        payload["auto_armed"] = False
    return set_flags(**payload)


@app.post("/api/draft")
def api_draft(body: DraftIn) -> dict:
    return ingest_text(body.text, contact=body.contact, mode="copilot")


@app.post("/api/drafts/{draft_id}/decide")
def api_decide(draft_id: int, body: DraftDecision) -> dict:
    row = get_draft(draft_id)
    if not row:
        raise HTTPException(404, "草稿不存在")
    if body.status not in {"copied", "dismissed", "edited"}:
        raise HTTPException(400, "无效状态")
    update_draft(draft_id, status=body.status, chosen_text=body.chosen_text)
    return {"ok": True}


@app.get("/api/last-shot")
def api_last_shot() -> FileResponse:
    if not LAST_SHOT.exists():
        raise HTTPException(404, "还没有截屏")
    return FileResponse(LAST_SHOT, media_type="image/png")


def main() -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        "wechat_draft_brain.app:app",
        host=str(cfg.get("host") or "127.0.0.1"),
        port=int(cfg.get("port") or 8765),
        reload=False,
    )


if __name__ == "__main__":
    main()
