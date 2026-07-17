from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from ..models import Candidate, ClipMeta, Episode, NicheConfig, ProducedClip


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "clip"


def package_clip(source: Path, episode: Episode, candidate: Candidate, niche: NicheConfig, outbox: Path, music_track: str | None) -> ProducedClip:
    date = episode.published_at.strftime("%Y-%m-%d") if episode.published_at else "undated"
    directory = outbox / niche.name / f"{date}_{_slug(candidate.title)}"
    directory.mkdir(parents=True, exist_ok=True)
    clip_path = directory / "clip.mp4"
    source.replace(clip_path)
    cover_path = directory / "cover.jpg"
    hook_offset = min(max(0, candidate.start + 1 - candidate.start), candidate.end - candidate.start - .1)
    subprocess.run(["ffmpeg", "-y", "-ss", f"{hook_offset:.3f}", "-i", str(clip_path), "-frames:v", "1", "-q:v", "2", str(cover_path)], check=True, capture_output=True)
    hashtags = list(dict.fromkeys([*niche.hashtags_base, *candidate.hashtags]))[:8]
    meta = ClipMeta(niche=niche.name, source_id=episode.source_id, source_show=episode.source_id, episode_title=episode.title,
        episode_url=episode.url, license_status=episode.license_status, start=candidate.start, end=candidate.end, score=candidate.score,
        title=candidate.title, caption=candidate.suggested_caption, hashtags=hashtags, hook_sentence=candidate.hook_sentence,
        virality_reason=candidate.virality_reason, caption_style=niche.caption_style, music_track=music_track)
    (directory / "meta.json").write_text(meta.model_dump_json(indent=2))
    digest = hashlib.sha256(f"{episode.source_id}:{episode.external_id}:{niche.name}:{candidate.start:.3f}:{candidate.end:.3f}".encode()).hexdigest()[:16]
    return ProducedClip(clip_id=digest, meta=meta, directory=directory, clip_path=clip_path, cover_path=cover_path)
