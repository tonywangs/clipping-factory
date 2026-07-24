"""Format 2 — fantasy-object ASMR (glass fruit cutting etc.).

TikTok "glass fruit" videos are AI-video-generated. Video generation APIs are
operator-supplied: drop generated clips (Sora/Veo/Runway exports) into
assets/broll/asmr/<collection>/. This module sequences them into a satisfying
cut rhythm, keeps/boosts the crisp original audio, and labels each cut.

If a collection folder is empty the build fails with instructions rather than
producing a blank video.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from ..config import project_root
from ..llm import LLMUsage, call_llm, extract_json
from ..progress import Progress
from .base import (
    VIDEO_KINDS,
    concat_segments,
    finalize,
    gather_media,
    media_duration,
    overlay_text,
    to_vertical_segment,
)


@dataclass
class AsmrPlan:
    title: str
    caption: str
    hashtags: list[str]
    label: str


IDEA_PROMPT = """You caption viral ASMR TikToks of AI-generated "impossible material" videos
(e.g. cutting glass fruit, slicing frozen honey planets).
Collection: {collection}
Return JSON only:
{{"title": string (short, e.g. "cutting glass mango"),
"label": string (2-4 word on-screen text with 1 emoji),
"caption": string (short, curiosity + ask viewers which was most satisfying),
"hashtags": [string] (6-8, include #asmr #satisfying)}}"""


def plan_asmr(collection: str) -> tuple[AsmrPlan, LLMUsage]:
    raw, usage = call_llm(IDEA_PROMPT.format(collection=collection))
    data = extract_json(raw)
    return (
        AsmrPlan(
            title=str(data.get("title") or f"{collection} asmr"),
            caption=str(data.get("caption") or "which cut was the most satisfying?"),
            hashtags=[str(t) for t in data.get("hashtags", [])] or ["#asmr", "#satisfying", "#fyp"],
            label=str(data.get("label") or collection),
        ),
        usage,
    )


def build_asmr_video(
    collection: str,
    work: Path,
    *,
    target_seconds: float = 34.0,
    min_cut: float = 2.0,
    max_cut: float = 4.5,
) -> tuple[Path, AsmrPlan, LLMUsage]:
    progress = Progress("asmr")
    work.mkdir(parents=True, exist_ok=True)
    source_dir = project_root() / "assets" / "broll" / "asmr" / collection
    progress.emit(f"Scanning source clips in {source_dir}")
    clips = gather_media(source_dir, VIDEO_KINDS)
    if not clips:
        raise FileNotFoundError(
            f"No ASMR source clips in {source_dir}. Export AI-generated clips (Sora/Veo/Runway "
            "glass-fruit renders, etc.) into that folder, then re-run. Any mp4/mov works."
        )
    progress.emit(f"Found {len(clips)} source clip(s); generating title and caption…")
    plan, usage = plan_asmr(collection)
    rng = random.Random(collection)
    segments: list[Path] = []
    total = 0.0
    index = 0
    ordered = clips[:]
    rng.shuffle(ordered)
    while total < target_seconds:
        clip = ordered[index % len(ordered)]
        duration = media_duration(clip)
        cut = min(rng.uniform(min_cut, max_cut), max(0.8, duration - 0.1))
        start = 0.0 if duration <= cut + 0.2 else rng.uniform(0, duration - cut - 0.1)
        progress.emit(
            f"Cut {index + 1}: {clip.name} @ {start:.1f}s for {cut:.1f}s "
            f"({total:.1f}/{target_seconds:.1f}s assembled)"
        )
        segment = to_vertical_segment(clip, work / f"cut_{index:02d}.mp4", start, cut)
        segments.append(segment)
        total += cut
        index += 1
        if index > 40:
            break
    progress.emit(f"Combining {len(segments)} cuts…")
    assembled = concat_segments(segments, work / "assembled.mp4", with_audio=True)
    progress.emit("Adding on-screen label…")
    labeled = overlay_text(assembled, work / "labeled.mp4", plan.label, size=80, y="h*0.08")
    progress.emit("Finalizing video…")
    final = finalize(labeled, work / "final.mp4", max_seconds=60)
    progress.done("ASMR video ready")
    return final, plan, usage
