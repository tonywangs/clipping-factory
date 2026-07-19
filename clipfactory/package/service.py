from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from ..ffmpeg_bin import ffmpeg_bin
from ..ids import make_clip_id
from ..models import Candidate, ClipMeta, Episode, NicheConfig, ProducedClip, utcnow


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "clip"


def package_clip(
    source: Path,
    episode: Episode,
    candidate: Candidate,
    niche: NicheConfig,
    outbox: Path,
    music_track: str | None,
    *,
    run_id: str,
    tags: list[str] | None = None,
) -> ProducedClip:
    date = episode.published_at.strftime("%Y-%m-%d") if episode.published_at else "undated"
    # outbox/<niche>/<run_id>/<date>_<slug>/
    directory = outbox / niche.name / run_id / f"{date}_{_slug(candidate.title)}"
    directory.mkdir(parents=True, exist_ok=True)
    clip_path = directory / "clip.mp4"
    source.replace(clip_path)
    cover_path = directory / "cover.jpg"
    hook_offset = min(1.0, max(0.0, (candidate.end - candidate.start) * 0.15))
    subprocess.run(
        [ffmpeg_bin(), "-y", "-ss", f"{hook_offset:.3f}", "-i", str(clip_path), "-frames:v", "1", "-q:v", "2", str(cover_path)],
        check=True,
        capture_output=True,
    )
    hashtags = list(dict.fromkeys([*niche.hashtags_base, *candidate.hashtags]))[:8]
    clip_id = make_clip_id(episode.source_id, episode.external_id, niche.name, candidate.start, candidate.end)
    meta = ClipMeta(
        clip_id=clip_id,
        run_id=run_id,
        niche=niche.name,
        source_id=episode.source_id,
        external_id=episode.external_id,
        source_show=episode.source_id,
        episode_title=episode.title,
        episode_url=episode.url,
        license_status=episode.license_status,
        start=candidate.start,
        end=candidate.end,
        score=candidate.score,
        title=candidate.title,
        caption=candidate.suggested_caption,
        hashtags=hashtags,
        hook_sentence=candidate.hook_sentence,
        virality_reason=candidate.virality_reason,
        caption_style=niche.caption_style,
        music_track=music_track,
        tags=list(tags or []),
    )
    (directory / "meta.json").write_text(meta.model_dump_json(indent=2))
    return ProducedClip(clip_id=clip_id, meta=meta, directory=directory, clip_path=clip_path, cover_path=cover_path)


def write_run_manifest(outbox: Path, niche: str, run_id: str, summary: dict) -> Path:
    directory = outbox / niche / run_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "run.json"
    payload = {"run_id": run_id, "niche": niche, "created_at": utcnow().isoformat(), **summary}
    path.write_text(json.dumps(payload, indent=2))
    return path
