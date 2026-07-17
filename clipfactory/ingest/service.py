from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from yt_dlp import YoutubeDL

from ..models import Episode


class IngestBlockedError(RuntimeError):
    pass


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _yt_options(output: Path, max_height: int) -> dict:
    options: dict = {
        "outtmpl": str(output), "quiet": True, "noplaylist": True,
        "format": f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]",
        "merge_output_format": "mp4", "retries": 3,
    }
    if cookies := os.getenv("YTDLP_COOKIES_FILE"):
        options["cookiefile"] = cookies
    if proxy := os.getenv("YTDLP_PROXY"):
        options["proxy"] = proxy
    if clients := os.getenv("YTDLP_PLAYER_CLIENTS"):
        options["extractor_args"] = {"youtube": {"player_client": clients.split(",")}}
    return options


def ingest_episode(episode: Episode, raw_dir: Path, max_height: int = 1080) -> Episode:
    if episode.local_path and episode.local_path.exists():
        episode.content_hash = episode.content_hash or _hash_file(episode.local_path)
        return episode
    raw_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".mp3" if not episode.video else ".mp4"
    cached = raw_dir / f"{episode.source_id}_{episode.external_id}{suffix}"
    if cached.exists():
        episode.local_path, episode.content_hash = cached, _hash_file(cached)
        return episode
    if episode.video:
        target = raw_dir / f"{episode.source_id}_{episode.external_id}.%(ext)s"
        try:
            with YoutubeDL(_yt_options(target, max_height)) as ydl:
                ydl.download([episode.url])
        except Exception as exc:
            message = str(exc)
            if "confirm you're not a bot" in message.lower() or "sign in" in message.lower():
                raise IngestBlockedError("YouTube blocked ingest. Mount YTDLP_COOKIES_FILE first; then configure YTDLP_PLAYER_CLIENTS/PO token support or YTDLP_PROXY. Local ingest plus cloud processing is supported.") from exc
            raise
        files = sorted(raw_dir.glob(f"{episode.source_id}_{episode.external_id}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            raise FileNotFoundError(f"yt-dlp did not create output for {episode.url}")
        files[0].replace(cached)
    else:
        subprocess.run(["yt-dlp", "--no-playlist", "-x", "--audio-format", "mp3", "-o", str(cached), episode.url], check=True)
    episode.local_path, episode.content_hash = cached, _hash_file(cached)
    return episode
