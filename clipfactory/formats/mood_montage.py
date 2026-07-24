"""Format 4 — mood montage: sad music over scenery b-roll (NYC rain etc.).

Operator drops scenery clips into assets/broll/<collection>/ and mood tracks
into assets/music/moods/<mood>/. The build sequences slow cuts with an LLM
one-liner overlay. Music is the content here, so the bed plays at full level.

Music rights are the operator's responsibility — commercial tracks (e.g.
Taylor Swift) will get flagged/muted by TikTok unless added from TikTok's own
sound library at post time. Recommended flow: render silent-ready montage,
add the trending sound inside TikTok. Use --no-music for that.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from ..config import project_root
from ..llm import LLMUsage, call_llm, extract_json
from ..progress import Progress
from .base import (
    AUDIO_KINDS,
    VIDEO_KINDS,
    concat_segments,
    finalize,
    gather_media,
    media_duration,
    mix_music,
    overlay_text,
    to_vertical_segment,
)


@dataclass
class MontagePlan:
    overlay: str
    caption: str
    hashtags: list[str] = field(default_factory=list)


MONTAGE_PROMPT = """You caption aesthetic mood-montage TikToks.
Scenery collection: {collection}; mood: {mood}.
Return JSON only:
{{"overlay": string (one lowercase melancholy/aesthetic line for on-screen text,
e.g. "nyc in the rain just hits different"),
"caption": string (short, relatable), "hashtags":[string] (6-8)}}"""


def plan_montage(collection: str, mood: str) -> tuple[MontagePlan, LLMUsage]:
    raw, usage = call_llm(MONTAGE_PROMPT.format(collection=collection, mood=mood))
    data = extract_json(raw)
    return (
        MontagePlan(
            overlay=str(data.get("overlay") or f"{collection} {mood} hits different"),
            caption=str(data.get("caption") or collection),
            hashtags=[str(t) for t in data.get("hashtags", [])] or ["#aesthetic", "#fyp"],
        ),
        usage,
    )


def build_montage_video(
    collection: str,
    work: Path,
    *,
    mood: str = "sad",
    target_seconds: float = 30.0,
    min_cut: float = 3.0,
    max_cut: float = 5.0,
    use_music: bool = True,
) -> tuple[Path, MontagePlan, LLMUsage]:
    progress = Progress("montage")
    work.mkdir(parents=True, exist_ok=True)
    source_dir = project_root() / "assets" / "broll" / collection
    progress.emit(f"Scanning b-roll in {source_dir}")
    clips = gather_media(source_dir, VIDEO_KINDS)
    if not clips:
        raise FileNotFoundError(
            f"No b-roll in {source_dir}. Drop scenery clips (e.g. NYC rain footage you have "
            "rights to) into that folder, then re-run."
        )
    progress.emit(f"Found {len(clips)} b-roll clip(s); generating overlay and caption…")
    plan, usage = plan_montage(collection, mood)
    rng = random.Random(f"{collection}:{mood}")
    ordered = clips[:]
    rng.shuffle(ordered)
    segments: list[Path] = []
    total, index = 0.0, 0
    while total < target_seconds:
        clip = ordered[index % len(ordered)]
        duration = media_duration(clip)
        cut = min(rng.uniform(min_cut, max_cut), max(1.0, duration - 0.1))
        start = 0.0 if duration <= cut + 0.2 else rng.uniform(0, duration - cut - 0.1)
        progress.emit(
            f"Cut {index + 1}: {clip.name} @ {start:.1f}s for {cut:.1f}s "
            f"({total:.1f}/{target_seconds:.1f}s assembled)"
        )
        segments.append(to_vertical_segment(clip, work / f"cut_{index:02d}.mp4", start, cut, mute=True))
        total += cut
        index += 1
        if index > 30:
            break
    progress.emit(f"Combining {len(segments)} scenery cuts…")
    assembled = concat_segments(segments, work / "assembled.mp4", with_audio=False)
    progress.emit("Adding mood text overlay…")
    labeled = overlay_text(assembled, work / "labeled.mp4", plan.overlay, size=64, y="h*0.45")
    tracks = gather_media(project_root() / "assets" / "music" / "moods" / mood, AUDIO_KINDS)
    if use_music and tracks:
        selected_track = rng.choice(tracks)
        progress.emit(f"Mixing {mood} music track: {selected_track.name}")
        labeled = mix_music(labeled, selected_track, work / "with_music.mp4", music_db=-2, keep_video_audio=False)
    elif use_music:
        progress.emit(f"No music found in assets/music/moods/{mood}; continuing silently")
    else:
        progress.emit("Music disabled; add the trending sound inside TikTok")
    progress.emit("Finalizing video…")
    final = finalize(labeled, work / "final.mp4", max_seconds=60)
    progress.done("Montage ready")
    return final, plan, usage
