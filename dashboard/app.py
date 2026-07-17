from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from clipfactory.config import load_settings, project_root
from clipfactory.state import build_state

app = FastAPI(title="ClipFactory Review")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
root, settings = project_root(), load_settings()
app.mount("/media", StaticFiles(directory=str(root)), name="media")


def _clips(niche: str | None = None) -> list[dict]:
    base = root / settings.outbox_dir
    clips = []
    for meta_file in base.glob("*/*/meta.json"):
        meta = json.loads(meta_file.read_text())
        if niche and meta["niche"] != niche:
            continue
        clips.append({"meta": meta, "directory": meta_file.parent, "clip_id": _clip_id(meta)})
    return sorted(clips, key=lambda item: item["meta"]["created_at"], reverse=True)


def _clip_id(meta: dict) -> str:
    import hashlib
    return hashlib.sha256(f"{meta['source_id']}:{meta['niche']}:{meta['start']:.3f}:{meta['end']:.3f}".encode()).hexdigest()[:16]


@app.get("/", response_class=HTMLResponse)
def index(request: Request, niche: str | None = None):
    clips = _clips(niche)
    return templates.TemplateResponse(request, "index.html", {"clips": clips, "niches": sorted({item['meta']['niche'] for item in clips}), "selected": niche, "root": root})


@app.post("/clips/{clip_id}/{decision}")
async def decide(clip_id: str, decision: str, request: Request):
    values = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    reason = values.get("reason", [""])[0]
    if decision not in {"approved", "rejected"} or (decision == "rejected" and not reason.strip()):
        raise HTTPException(400, "Rejection reason is required")
    item = next((item for item in _clips() if item["clip_id"] == clip_id), None)
    if not item:
        raise HTTPException(404, "Clip not found")
    target = root / decision / item["meta"]["niche"] / item["directory"].name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(item["directory"]), str(target))
    state = build_state(settings.state_backend)
    state.transition_clip(clip_id, decision, reason.strip() or None)
    if decision == "rejected":
        feedback = root / settings.feedback_dir / f"{item['meta']['niche']}.jsonl"
        feedback.parent.mkdir(parents=True, exist_ok=True)
        with feedback.open("a") as file:
            file.write(json.dumps({"clip_id": clip_id, "reason": reason.strip()}) + "\n")
    return {"status": decision}
