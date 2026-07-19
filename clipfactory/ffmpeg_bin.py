"""Resolve a caption-capable ffmpeg binary.

Homebrew's default `ffmpeg` bottle is often built without libass, so the
`subtitles` filter is missing. Prefer `ffmpeg-full` keg paths and explicit
FFMPEG_BINARY overrides.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


def _candidate_bins(env_key: str, names: list[str]) -> list[str]:
    found: list[str] = []
    override = os.getenv(env_key, "").strip()
    if override:
        found.append(override)
    for directory in (
        "/opt/homebrew/opt/ffmpeg-full/bin",
        "/usr/local/opt/ffmpeg-full/bin",
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/home/linuxbrew/.linuxbrew/bin",
    ):
        for name in names:
            candidate = f"{directory}/{name}"
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                found.append(candidate)
    for name in names:
        which = shutil.which(name)
        if which:
            found.append(which)
    ordered: list[str] = []
    for item in found:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _has_subtitle_filter(ffmpeg_path: str) -> bool:
    try:
        help_result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-h", "filter=subtitles"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    help_text = f"{help_result.stdout}\n{help_result.stderr}"
    if re.search(r"Unknown filter|not found", help_text, re.I):
        return False
    if "subtitles AVOptions" in help_text or "Filter subtitles" in help_text:
        return True
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-filters"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    text = f"{result.stdout}\n{result.stderr}"
    return bool(re.search(r"(?m)^\s*\S*\s+subtitles\s+", text))


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    for candidate in _candidate_bins("FFMPEG_BINARY", ["ffmpeg"]):
        if _has_subtitle_filter(candidate):
            return candidate
    return shutil.which("ffmpeg") or "ffmpeg"


@lru_cache(maxsize=1)
def ffprobe_bin() -> str:
    override = os.getenv("FFPROBE_BINARY", "").strip()
    if override:
        return override
    neighbor = Path(ffmpeg_bin()).with_name("ffprobe")
    if neighbor.is_file() and os.access(neighbor, os.X_OK):
        return str(neighbor)
    for candidate in _candidate_bins("FFPROBE_BINARY", ["ffprobe"]):
        return candidate
    return shutil.which("ffprobe") or "ffprobe"


def require_caption_ffmpeg() -> str:
    ffmpeg_bin.cache_clear()
    ffprobe_bin.cache_clear()
    binary = ffmpeg_bin()
    if not _has_subtitle_filter(binary):
        raise RuntimeError(
            f"FFmpeg at {binary!r} lacks the libass 'subtitles' filter.\n"
            "On modern Homebrew, plain `ffmpeg` is a lite build. Install the full one:\n"
            "  brew install ffmpeg-full\n"
            "  export FFMPEG_BINARY=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg\n"
            "  export FFPROBE_BINARY=/opt/homebrew/opt/ffmpeg-full/bin/ffprobe\n"
            "Then rerun the clipfactory command."
        )
    return binary
