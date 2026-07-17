from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

import feedparser
import httpx
from yt_dlp import YoutubeDL

from ..models import Episode, SourceConfig, SourceType
from ..state import StateRepository

logger = logging.getLogger(__name__)


def _parse_upload_date(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value)
    try:
        if len(text) == 8 and text.isdigit():
            return datetime(int(text[:4]), int(text[4:6]), int(text[6:8]), tzinfo=timezone.utc)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _channel_or_playlist_id(url: str, source_type: SourceType) -> tuple[str, str] | None:
    """Return (api_resource, id) for search.list / playlistItems.list when possible."""
    if "list=" in url:
        match = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url)
        if match:
            return "playlist", match.group(1)
    if source_type == SourceType.YOUTUBE_PLAYLIST:
        return None
    # @handle — resolve via channels.list later
    handle = re.search(r"youtube\.com/@([^/?#]+)", url)
    if handle:
        return "handle", handle.group(1)
    channel = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_-]+)", url)
    if channel:
        return "channel", channel.group(1)
    return None


def _youtube_api(source: SourceConfig, cap: int, api_key: str) -> list[Episode] | None:
    """Optional YouTube Data API discovery. Returns None to fall back to yt-dlp."""
    parsed = _channel_or_playlist_id(source.url, source.type)
    if not parsed:
        return None
    kind, value = parsed
    try:
        if kind == "handle":
            response = httpx.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "id", "forHandle": value, "key": api_key},
                timeout=30,
            )
            response.raise_for_status()
            items = response.json().get("items") or []
            if not items:
                return None
            channel_id = items[0]["id"]
            search = httpx.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "channelId": channel_id,
                    "order": "date",
                    "type": "video",
                    "maxResults": min(max(cap * 5, 10), 50),
                    "key": api_key,
                },
                timeout=30,
            )
            search.raise_for_status()
            video_ids = [item["id"]["videoId"] for item in search.json().get("items", []) if item.get("id", {}).get("videoId")]
        elif kind == "channel":
            search = httpx.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "channelId": value,
                    "order": "date",
                    "type": "video",
                    "maxResults": min(max(cap * 5, 10), 50),
                    "key": api_key,
                },
                timeout=30,
            )
            search.raise_for_status()
            video_ids = [item["id"]["videoId"] for item in search.json().get("items", []) if item.get("id", {}).get("videoId")]
        else:
            playlist = httpx.get(
                "https://www.googleapis.com/youtube/v3/playlistItems",
                params={
                    "part": "contentDetails,snippet",
                    "playlistId": value,
                    "maxResults": min(max(cap * 5, 10), 50),
                    "key": api_key,
                },
                timeout=30,
            )
            playlist.raise_for_status()
            video_ids = [
                item.get("contentDetails", {}).get("videoId")
                for item in playlist.json().get("items", [])
                if item.get("contentDetails", {}).get("videoId")
            ]
        if not video_ids:
            return []
        details = httpx.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "contentDetails,snippet", "id": ",".join(video_ids), "key": api_key},
            timeout=30,
        )
        details.raise_for_status()
        result: list[Episode] = []
        for item in details.json().get("items", []):
            duration = _iso8601_duration(item.get("contentDetails", {}).get("duration"))
            if duration is not None and duration < source.min_duration_minutes * 60:
                continue
            published = _parse_upload_date(item.get("snippet", {}).get("publishedAt"))
            result.append(
                Episode(
                    source_id=source.id,
                    external_id=item["id"],
                    title=str(item.get("snippet", {}).get("title") or item["id"]),
                    url=f"https://www.youtube.com/watch?v={item['id']}",
                    published_at=published,
                    duration_seconds=duration,
                    video=True,
                    license_status=source.license_status,
                )
            )
        return result
    except Exception as exc:
        logger.warning("YouTube Data API discovery failed for %s (%s); falling back to yt-dlp", source.id, exc)
        return None


def _iso8601_duration(value: object) -> float | None:
    if not value or not isinstance(value, str):
        return None
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if not match:
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return float(hours * 3600 + minutes * 60 + seconds)


def _youtube_ytdlp(source: SourceConfig, cap: int) -> list[Episode]:
    options = {
        "quiet": True,
        "extract_flat": "discard_in_playlist",
        "skip_download": True,
        "playlistend": max(cap * 5, 25),
    }
    with YoutubeDL(options) as ydl:
        data = ydl.extract_info(source.url, download=False)
    entries = data.get("entries", []) if isinstance(data, dict) else []
    result: list[Episode] = []
    for item in entries:
        if not item or not item.get("id"):
            continue
        duration = float(item.get("duration") or 0)
        if duration and duration < source.min_duration_minutes * 60:
            continue
        published = _parse_upload_date(item.get("upload_date") or item.get("release_timestamp"))
        if published is None and isinstance(item.get("timestamp"), (int, float)):
            published = datetime.fromtimestamp(float(item["timestamp"]), tz=timezone.utc)
        result.append(
            Episode(
                source_id=source.id,
                external_id=str(item["id"]),
                title=str(item.get("title") or item["id"]),
                url=item.get("url") or f"https://www.youtube.com/watch?v={item['id']}",
                published_at=published,
                duration_seconds=duration or None,
                video=True,
                license_status=source.license_status,
            )
        )
    return result


def _youtube(source: SourceConfig, cap: int) -> list[Episode]:
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if api_key:
        api_result = _youtube_api(source, cap, api_key)
        if api_result is not None:
            return api_result
    return _youtube_ytdlp(source, cap)


def _rss(source: SourceConfig, cap: int) -> list[Episode]:
    feed = feedparser.parse(source.url)
    result: list[Episode] = []
    for item in feed.entries[: max(cap * 5, 25)]:
        enclosure = next((x.get("href") for x in item.get("enclosures", []) if x.get("href")), None)
        url = enclosure or item.get("link")
        external_id = item.get("id") or url
        if not url or not external_id:
            continue
        duration = _duration(item.get("itunes_duration"))
        if duration and duration < source.min_duration_minutes * 60:
            continue
        parsed = item.get("published_parsed")
        published = datetime(*parsed[:6], tzinfo=timezone.utc) if parsed else None
        result.append(
            Episode(
                source_id=source.id,
                external_id=str(external_id),
                title=str(item.get("title") or external_id),
                url=url,
                published_at=published,
                duration_seconds=duration,
                video=False,
                license_status=source.license_status,
            )
        )
    return result


def _duration(value: object) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        parts = [float(part) for part in str(value).split(":")]
        return sum(part * 60**index for index, part in enumerate(reversed(parts)))
    except ValueError:
        return None


def discover_sources(sources: list[SourceConfig], state: StateRepository, cap: int) -> list[Episode]:
    """Return episodes that still need at least one niche run.

    Dedup is per-niche via niche_runs: completed niches are skipped by claim,
    failed/missing niches remain pending and are rediscovered. Episodes with
    known publish dates are preferred newest-first so the per-run cap favors
    fresh uploads.
    """
    discovered: list[Episode] = []
    for source in sources:
        if not source.enabled:
            continue
        try:
            episodes = _rss(source, cap) if source.type == SourceType.RSS else _youtube(source, cap)
        except Exception as exc:
            logger.error("Discovery failed for source %s: %s", source.id, exc)
            continue
        episodes = sorted(
            episodes,
            key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        for episode in episodes:
            if not state.has_pending_niche_work(episode.source_id, episode.external_id, source.niches):
                continue
            discovered.append(episode)
            if len(discovered) >= cap:
                return discovered
    return discovered
