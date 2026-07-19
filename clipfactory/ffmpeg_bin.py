"""Resolve a caption-capable ffmpeg binary (conda builds often lack libass)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from functools import lru_cache


def _candidate_bins(env_key: str, names: list[str]) -> list[str]:
    found: list[str] = []
    override = os.getenv(env_key, "").strip()
    if override:
        found.append(override)
    for path in (
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/home/linuxbrew/.linuxbrew/bin",
    ):
        for name in names:
            candidate = f"{path}/{name}"
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                found.append(candidate)
    for name in names:
        which = shutil.which(name)
        if which:
            found.append(which)
    # Dedupe, preserve order
    ordered: list[str] = []
    for item in found:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _has_subtitle_filter(ffmpeg_bin: str) -> bool:
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-filters"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    text = f"{result.stdout}\n{result.stderr}"
    return bool(re.search(r"(?m)^\s*\S*\s+subtitles\s+", text) or re.search(r"\bsubtitles\b", text))


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    for candidate in _candidate_bins("FFMPEG_BINARY", ["ffmpeg"]):
        if _has_subtitle_filter(candidate):
            return candidate
    # Last resort: whatever is on PATH, even if captions will fail later with a clear error.
    return shutil.which("ffmpeg") or "ffmpeg"


@lru_cache(maxsize=1)
def ffprobe_bin() -> str:
    ffmpeg = ffmpeg_bin()
    probe_override = os.getenv("FFPROBE_BINARY", "").strip()
    if probe_override:
        return probe_override
    sibling = str(PathLike(ffmpeg).with_name("ffprobe")) if False else None  # placeholder
    # Prefer ffprobe next to the chosen ffmpeg.
    from pathlib import Path

    neighbor = Path(ffmpeg).with_name("ffprobe")
    if neighbor.is_file() and os.access(neighbor, os.X_OK):
        return str(neighbor)
    for candidate in _candidate_bins("FFPROBE_BINARY", ["ffprobe"]):
        return candidate
    return shutil.which("ffprobe") or "ffprobe"


# Fix accidental dead code - rewrite cleanly
from pathlib import Path  # noqa: E402


@lru_cache(maxsize=1)
def ffprobe_bin() -> str:  # type: ignore[no-redef]
    probe_override = os.getenv("FFPROBE_BINARY", "").strip()
    if probe_override:
        return probe_override
    neighbor = Path(ffmpeg_bin()).with_name("ffprobe")
    if neighbor.is_file() and os.access(neighbor, os.X_OK):
        return str(neighbor)
    for candidate in _candidate_bins("FFPROBE_BINARY", ["ffprobe"]):
        return candidate
    return shutil.which("ffprobe") or "ffprobe"


def require_caption_ffmpeg() -> str:
    binary = ffmpeg_bin()
    if not _has_subtitle_filter(binary):
        raise RuntimeError(
            f"FFmpeg at {binary!r} lacks the libass 'subtitles' filter.\n"
            "Your conda/base ffmpeg is often the problem. Do this:\n"
            "  brew install ffmpeg\n"
            "  export PATH=\"/opt/homebrew/bin:$PATH\"\n"
            "  export FFMPEG_BINARY=/opt/homebrew/bin/ffmpeg\n"
            "  export FFPROBE_BINARY=/opt/homebrew/bin/ffprobe\n"
            "Then rerun the clipfactory command."
        )
    return binary
