from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from clipfactory.config import load_settings, project_root
from clipfactory.ids import make_clip_id
from clipfactory.state import build_state

app = FastAPI(title="ClipFactory Review")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
root, settings = project_root(), load_settings()
app.mount("/media", StaticFiles(directory=str(root)), name="media")


def _resolve_clip_id(meta: dict) -> str:
    if meta.get("clip_id"):
        return str(meta["clip_id"])
    return make_clip_id(
        str(meta["source_id"]),
        str(meta.get("external_id") or meta["source_id"]),
        str(meta["niche"]),
        float(meta["start"]),
        float(meta["end"]),
    )


def _infer_run_id(meta: dict, directory: Path) -> str:
    if meta.get("run_id"):
        return str(meta["run_id"])
    parts = directory.parts
    try:
        outbox_index = parts.index(settings.outbox_dir)
        if len(parts) >= outbox_index + 4:
            return parts[outbox_index + 2]
    except ValueError:
        pass
    return "legacy"


def _clips(niche: str | None = None, run_id: str | None = None) -> list[dict]:
    base = root / settings.outbox_dir
    clips = []
    patterns = ("*/*/meta.json", "*/*/*/meta.json")
    seen: set[Path] = set()
    for pattern in patterns:
        for meta_file in base.glob(pattern):
            if meta_file in seen:
                continue
            seen.add(meta_file)
            meta = json.loads(meta_file.read_text())
            if niche and meta.get("niche") != niche:
                continue
            resolved_run = _infer_run_id(meta, meta_file.parent)
            meta = {**meta, "run_id": resolved_run, "tags": meta.get("tags") or []}
            if run_id and run_id != "all" and resolved_run != run_id:
                continue
            clips.append(
                {
                    "meta": meta,
                    "directory": meta_file.parent,
                    "clip_id": _resolve_clip_id(meta),
                    "run_id": resolved_run,
                }
            )
    return sorted(
        clips,
        key=lambda item: (item["run_id"], item["meta"].get("created_at", "")),
        reverse=True,
    )


def _runs(clips: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for clip in clips:
        counts[clip["run_id"]] = counts.get(clip["run_id"], 0) + 1
    return [{"run_id": key, "count": counts[key]} for key in sorted(counts.keys(), reverse=True)]


@app.get("/", response_class=HTMLResponse)
def index(request: Request, niche: str | None = None, run: str | None = None):
    all_for_filters = _clips(niche=niche)
    runs = _runs(all_for_filters)
    if run == "all":
        selected_run = "all"
        clips = all_for_filters
    elif run:
        selected_run = run
        clips = _clips(niche=niche, run_id=run)
    elif runs:
        selected_run = runs[0]["run_id"]
        clips = _clips(niche=niche, run_id=selected_run)
    else:
        selected_run = None
        clips = []
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "clips": clips,
            "niches": sorted({item["meta"]["niche"] for item in all_for_filters}),
            "runs": runs,
            "selected_niche": niche,
            "selected_run": selected_run,
            "root": root,
        },
    )


@app.post("/clips/{clip_id}/{decision}")
async def decide(clip_id: str, decision: str, request: Request):
    values = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    reason = values.get("reason", [""])[0]
    if decision not in {"approved", "rejected"} or (decision == "rejected" and not reason.strip()):
        raise HTTPException(400, "Rejection reason is required")
    item = next((item for item in _clips() if item["clip_id"] == clip_id), None)
    if not item:
        raise HTTPException(404, "Clip not found")
    run_id = item["run_id"]
    target = root / decision / item["meta"]["niche"] / run_id / item["directory"].name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(item["directory"]), str(target))
    state = build_state(settings.state_backend)
    state.transition_clip(clip_id, decision, reason.strip() or None)
    if decision == "rejected":
        feedback = root / settings.feedback_dir / f"{item['meta']['niche']}.jsonl"
        feedback.parent.mkdir(parents=True, exist_ok=True)
        with feedback.open("a") as file:
            file.write(json.dumps({"clip_id": clip_id, "run_id": run_id, "reason": reason.strip()}) + "\n")
    return HTMLResponse("")
