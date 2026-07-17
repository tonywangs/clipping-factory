from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LicenseStatus(StrEnum):
    CAMPAIGN_LICENSED = "campaign_licensed"
    CLIPPING_ENCOURAGED = "clipping_encouraged"
    UNLICENSED = "unlicensed"


class SourceType(StrEnum):
    YOUTUBE_CHANNEL = "youtube_channel"
    YOUTUBE_PLAYLIST = "youtube_playlist"
    RSS = "rss"


class SourceConfig(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    type: SourceType
    url: str
    niches: list[str] = Field(min_length=1)
    license_status: LicenseStatus
    enabled: bool = True
    min_duration_minutes: int = Field(default=20, ge=1)


class SourcesConfig(BaseModel):
    sources: list[SourceConfig] = Field(default_factory=list)


class ClipLength(BaseModel):
    min: int = Field(ge=5, le=60)
    max: int = Field(ge=5, le=60)

    def model_post_init(self, __context: Any) -> None:
        if self.min > self.max:
            raise ValueError("clip_length_seconds.min cannot exceed max")


class CaptionStyle(StrEnum):
    HORMOZI = "hormozi"
    KARAOKE = "karaoke"


class NicheConfig(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    account_handle: str
    audience: str
    tone: str
    prioritize_topics: list[str] = Field(default_factory=list)
    skip_topics: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    clip_length_seconds: ClipLength
    clips_per_episode: int = Field(default=4, ge=1, le=10)
    min_score: int = Field(default=70, ge=0, le=100)
    caption_style: CaptionStyle = CaptionStyle.HORMOZI
    accent_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    hashtags_base: list[str] = Field(default_factory=list)
    example_hooks: list[str] = Field(default_factory=list)
    music: bool = True
    music_volume_db: float = -22.0


class Settings(BaseModel):
    storage_backend: str = "local"
    state_backend: str = "sqlite"
    max_new_episodes_per_run: int = Field(default=3, ge=1)
    download_max_height: int = Field(default=1080, ge=360, le=2160)
    whisper_model: str = "base"
    whisper_device: str = "auto"
    outbox_dir: str = "outbox"
    raw_dir: str = "raw"
    transcript_dir: str = "transcripts"
    work_dir: str = "work"
    feedback_dir: str = "feedback"
    music_volume_db: float = -22.0
    costs_per_million_tokens: dict[str, float] = Field(default_factory=dict)


class Episode(BaseModel):
    source_id: str
    external_id: str
    title: str
    url: str
    published_at: datetime | None = None
    duration_seconds: float | None = None
    video: bool = True
    license_status: LicenseStatus
    local_path: Path | None = None
    content_hash: str | None = None


class Word(BaseModel):
    word: str
    start: float
    end: float


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[Word] = Field(default_factory=list)


class Transcript(BaseModel):
    duration: float
    segments: list[TranscriptSegment]


class Candidate(BaseModel):
    start: float
    end: float
    score: int = Field(ge=0, le=100)
    title: str
    hook_sentence: str
    virality_reason: str
    suggested_caption: str = ""
    hashtags: list[str] = Field(default_factory=list)


class ClipMeta(BaseModel):
    niche: str
    source_id: str
    source_show: str
    episode_title: str
    episode_url: str
    license_status: LicenseStatus
    start: float
    end: float
    score: int
    title: str
    caption: str
    hashtags: list[str]
    hook_sentence: str
    virality_reason: str
    caption_style: CaptionStyle
    music_track: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ProducedClip(BaseModel):
    clip_id: str
    meta: ClipMeta
    directory: Path
    clip_path: Path
    cover_path: Path
    status: str = "outbox"
