from __future__ import annotations

from datetime import datetime, timezone

import feedparser
from yt_dlp import YoutubeDL

from ..models import Episode, SourceConfig, SourceType
from ..state import StateRepository


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


def _youtube(source: SourceConfig, cap: int) -> list[Episode]:
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
        episodes = _rss(source, cap) if source.type == SourceType.RSS else _youtube(source, cap)
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
