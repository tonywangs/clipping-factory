"""Package generated (non-podcast) content into the same outbox/meta shape."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..config import project_root
from ..ffmpeg_bin import ffmpeg_bin
from ..ids import make_clip_id
from ..models import CaptionStyle, ClipMeta, LicenseStatus, ProducedClip


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "clip"


def package_generated(
    video: Path,
    *,
    format_name: str,
    niche: str,
    run_id: str,
    title: str,
    caption: str,
    hashtags: list[str],
    hook_sentence: str,
    reason: str,
    score: int,
    license_status: LicenseStatus,
    tags: list[str],
    source_ref: str = "generated",
) -> ProducedClip:
    root = project_root()
    outbox = root / "outbox" / niche / run_id / f"generated_{_slug(title)}"
    outbox.mkdir(parents=True, exist_ok=True)
    clip_path = outbox / "clip.mp4"
    video.replace(clip_path)
    cover = outbox / "cover.jpg"
    subprocess.run(
        [ffmpeg_bin(), "-y", "-ss", "0.5", "-i", str(clip_path), "-frames:v", "1", "-q:v", "2", str(cover)],
        check=True,
        capture_output=True,
    )
    clip_id = make_clip_id(format_name, _slug(title), niche, 0.0, 0.0)
    meta = ClipMeta(
        clip_id=clip_id,
        run_id=run_id,
        niche=niche,
        source_id=format_name,
        external_id=_slug(title),
        source_show=format_name,
        episode_title=title,
        episode_url=source_ref,
        license_status=license_status,
        start=0.0,
        end=0.0,
        score=score,
        title=title,
        caption=caption,
        hashtags=hashtags[:8],
        hook_sentence=hook_sentence,
        virality_reason=reason,
        caption_style=CaptionStyle.HORMOZI,
        music_track=None,
        tags=[format_name, *tags],
    )
    (outbox / "meta.json").write_text(meta.model_dump_json(indent=2))
    return ProducedClip(clip_id=clip_id, meta=meta, directory=outbox, clip_path=clip_path, cover_path=cover)
