"""Format 5 — fancam edits: iconic scenes + goofy loud transitions.

"maddie ziegler attitude" / "kourtney attitude" style: N short iconic moments
cut from a source video, big text overlay, loud boom/whoosh SFX slammed on
every cut.

Moment sources, in priority order:
1. --moments "12.5-16,42-45.5,..." (operator-picked timestamps — best quality)
2. transcript + LLM (finds sassy/iconic dialogue moments automatically)

These edits use others' footage: license_status is stamped `unlicensed` and
the dashboard shows the warning. Post at your own risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..llm import LLMUsage, call_llm, extract_json
from ..models import Transcript
from ..progress import Progress
from .base import (
    finalize,
    media_duration,
    overlay_text,
    pick_sfx,
    sfx_between,
    to_vertical_segment,
)


@dataclass
class FancamPlan:
    overlay: str
    caption: str
    hashtags: list[str] = field(default_factory=list)
    moments: list[tuple[float, float]] = field(default_factory=list)


MOMENT_PROMPT = """You edit goofy fancam TikToks ("{subject} attitude" style edits with loud
transition booms). From this transcript, pick the {count} most ICONIC short moments:
sassy one-liners, dramatic reactions, confident/rude/funny bursts. 2-6 seconds each.
Also write the on-screen text (e.g. "{subject} attitude \u2728"), a caption, and hashtags.
Return JSON only:
{{"moments":[{{"start":number,"end":number}}], "overlay": string,
"caption": string, "hashtags":[string]}}

Transcript:
{transcript}"""


def parse_moments(raw: str) -> list[tuple[float, float]]:
    """Parse '12.5-16,42-45.5' into [(12.5,16.0),(42.0,45.5)]."""
    moments: list[tuple[float, float]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        start_raw, _, end_raw = part.partition("-")
        start, end = float(start_raw), float(end_raw)
        if end > start:
            moments.append((start, end))
    return moments


def plan_from_transcript(transcript: Transcript, subject: str, count: int = 6) -> tuple[FancamPlan, LLMUsage]:
    text = "\n".join(f"[{segment.start:.1f}s] {segment.text}" for segment in transcript.segments)
    raw, usage = call_llm(MOMENT_PROMPT.format(subject=subject, count=count, transcript=text))
    data = extract_json(raw)
    moments = [
        (float(item["start"]), float(item["end"]))
        for item in data.get("moments", [])
        if isinstance(item, dict) and float(item.get("end", 0)) > float(item.get("start", 0))
    ]
    return (
        FancamPlan(
            overlay=str(data.get("overlay") or f"{subject} attitude"),
            caption=str(data.get("caption") or f"{subject} edit"),
            hashtags=[str(t) for t in data.get("hashtags", [])] or ["#edit", "#fyp"],
            moments=moments,
        ),
        usage,
    )


def build_fancam_video(
    source: Path,
    plan: FancamPlan,
    work: Path,
    *,
    sfx_kind: str = "boom",
    max_moment_seconds: float = 6.0,
) -> Path:
    progress = Progress("fancam")
    work.mkdir(parents=True, exist_ok=True)
    if not plan.moments:
        raise ValueError("Fancam plan has no moments — pass --moments or a transcript-rankable source")
    source_duration = media_duration(source)
    progress.emit(
        f"Source is {source_duration:.1f}s; rendering {min(len(plan.moments), 10)} iconic moment(s)"
    )
    segments: list[Path] = []
    for index, (start, end) in enumerate(plan.moments[:10]):
        start = max(0.0, min(start, source_duration - 0.5))
        cut = min(end - start, max_moment_seconds, source_duration - start)
        progress.step(
            index + 1,
            min(len(plan.moments), 10),
            f"Cutting {start:.1f}–{start + cut:.1f}s",
        )
        segments.append(to_vertical_segment(source, work / f"moment_{index:02d}.mp4", start, cut))
    progress.emit(f"Preparing {sfx_kind} transition SFX…")
    sfx = pick_sfx(work, sfx_kind)
    progress.emit("Combining moments and slamming SFX on each cut…")
    assembled = sfx_between(segments, sfx, work)
    progress.emit("Adding title overlay…")
    labeled = overlay_text(assembled, work / "labeled.mp4", plan.overlay, size=88, y="h*0.10")
    progress.emit("Finalizing video…")
    final = finalize(labeled, work / "final.mp4", max_seconds=60)
    progress.done("Fancam ready")
    return final
