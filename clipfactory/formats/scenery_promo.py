"""10-second atmospheric scenery videos for music-promotion campaigns.

This intentionally mirrors the very simple high-performing format:
one striking vertical visual, subtle motion, one music hook, no text.

Visual source priority:
1. --source existing image/video
2. OpenAI image generation
3. Gemini image generation

Music source:
1. --music file or folder
2. assets/music/promotions/<campaign>/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import project_root
from ..ffmpeg_bin import ffmpeg_bin
from ..llm import LLMUsage, call_llm, extract_json
from ..progress import Progress
from .base import (
    AUDIO_KINDS,
    H,
    IMAGE_KINDS,
    VIDEO_KINDS,
    W,
    Panel,
    finalize,
    gather_media,
    mix_music,
    render_panel,
    run,
)
from .images import generate_image


@dataclass
class SceneryPlan:
    title: str
    image_prompt: str
    caption: str
    hashtags: list[str] = field(default_factory=list)


PLAN_PROMPT = """You package atmospheric scenery TikToks used for music promotion.
Concept: {concept}
Music campaign: {campaign}
Artist: {artist}

The video itself has NO text; it is one mesmerizing 10-second visual with music.
Return JSON only:
{{"title": string (short internal title),
"image_prompt": string (extremely vivid vertical 9:16 cinematic scenery prompt;
no people, no text, no logos; describe lighting, weather, depth, atmosphere),
"caption": string (very short aesthetic caption; no fake claims),
"hashtags": [string] (5-8 scenery/aesthetic/discovery tags)}}"""


def plan_scenery(
    concept: str,
    *,
    campaign: str = "",
    artist: str = "",
) -> tuple[SceneryPlan, LLMUsage]:
    raw, usage = call_llm(
        PLAN_PROMPT.format(
            concept=concept,
            campaign=campaign or "unspecified",
            artist=artist or "unspecified",
        )
    )
    data = extract_json(raw)
    return (
        SceneryPlan(
            title=str(data.get("title") or concept).strip(),
            image_prompt=str(data.get("image_prompt") or concept).strip(),
            caption=str(data.get("caption") or concept).strip(),
            hashtags=[str(tag) for tag in data.get("hashtags", [])]
            or ["#scenery", "#aesthetic", "#nature", "#fyp"],
        ),
        usage,
    )


def resolve_promo_music(
    music: str | Path | None,
    campaign: str,
) -> Path:
    if music:
        path = Path(music).expanduser()
        if path.is_file() and path.suffix.lower() in AUDIO_KINDS:
            return path.resolve()
        if path.is_dir():
            tracks = gather_media(path, AUDIO_KINDS)
            if tracks:
                return tracks[0].resolve()
        raise FileNotFoundError(f"No supported music file found at {path}")

    campaign_dir = project_root() / "assets" / "music" / "promotions" / campaign
    tracks = gather_media(campaign_dir, AUDIO_KINDS)
    if tracks:
        return tracks[0].resolve()
    raise FileNotFoundError(
        "No promotion music found. Pass --music /path/to/track.mp3, or put the "
        f"campaign track in {campaign_dir}/"
    )


def track_attribution(track: Path) -> str | None:
    """Read the required caption credit bundled beside a licensed track."""
    path = track.parent / "ATTRIBUTION.txt"
    if not path.exists():
        return None
    credit = " ".join(line.strip() for line in path.read_text().splitlines() if line.strip())
    return credit or None


def _render_source_video(source: Path, target: Path, seconds: float) -> Path:
    """Loop/crop an existing AI-generated scenery clip to exact duration."""
    vf = (
        f"crop='if(gte(iw/ih,{W}/{H}),ih*{W}/{H},iw)':"
        f"'if(gte(iw/ih,{W}/{H}),ih,iw*{H}/{W})':"
        "(iw-ow)/2:(ih-oh)/2,"
        f"scale={W}:{H},fps=30,format=yuv420p"
    )
    run(
        [
            ffmpeg_bin(),
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(source),
            "-t",
            f"{seconds:.3f}",
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            str(target),
        ]
    )
    return target


def _resolve_visual(
    plan: SceneryPlan,
    work: Path,
    *,
    source: Path | None,
    image_provider: str,
    seconds: float,
    progress: Progress,
) -> tuple[Path, str]:
    if source is not None:
        source = source.expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Scenery source not found: {source}")
        if source.suffix.lower() in IMAGE_KINDS:
            progress.emit(f"Animating supplied image: {source.name}")
            return (
                render_panel(Panel(duration=seconds, image=source), work / "visual.mp4"),
                str(source),
            )
        if source.suffix.lower() in VIDEO_KINDS:
            progress.emit(f"Looping/cropping supplied video: {source.name}")
            return _render_source_video(source, work / "visual.mp4", seconds), str(source)
        raise ValueError(f"Unsupported scenery source type: {source.suffix}")

    progress.emit(f"Generating scenery image ({image_provider} provider)…")
    image = generate_image(
        plan.image_prompt,
        work / "scenery.png",
        provider=image_provider,
        style_suffix=(
            ", cinematic atmospheric photography, immense depth, subtle volumetric "
            "lighting, ultra detailed, vertical 9:16 composition, no people, no text, "
            "no watermark, no logo"
        ),
    )
    if image is None:
        raise RuntimeError(
            "Scenery image generation failed. Verify OPENAI_API_KEY or GEMINI_API_KEY, "
            "try --image-provider openai|gemini, or pass --source /path/to/image-or-video."
        )
    progress.emit("Animating generated image with a subtle cinematic push-in…")
    return render_panel(Panel(duration=seconds, image=image), work / "visual.mp4"), image_provider


def build_scenery_promo(
    concept: str,
    work: Path,
    *,
    music: str | Path | None,
    campaign: str = "default",
    artist: str = "",
    source: Path | None = None,
    image_provider: str = "auto",
    seconds: float = 10.0,
    music_start: float = 0.0,
    music_db: float = -2.0,
) -> tuple[Path, SceneryPlan, LLMUsage, Path, str]:
    if seconds < 3 or seconds > 60:
        raise ValueError("--seconds must be between 3 and 60")

    progress = Progress("scenery")
    work.mkdir(parents=True, exist_ok=True)
    progress.emit("Creating scenery concept and post metadata with the LLM…")
    plan, usage = plan_scenery(concept, campaign=campaign, artist=artist)
    progress.emit(f"Plan ready: {plan.title}")

    visual, visual_source = _resolve_visual(
        plan,
        work,
        source=source,
        image_provider=image_provider,
        seconds=seconds,
        progress=progress,
    )
    track = resolve_promo_music(music, campaign)
    attribution = track_attribution(track)
    if attribution:
        plan.caption = f"{plan.caption}\n\n{attribution}"
        progress.emit("Required CC attribution added to the TikTok caption")
    progress.emit(
        f"Adding music: {track.name} (hook starts at {music_start:.1f}s)"
    )
    with_music = mix_music(
        visual,
        track,
        work / "with_music.mp4",
        music_db=music_db,
        music_start=music_start,
        keep_video_audio=False,
    )
    progress.emit("Finalizing 1080x1920 deliverable…")
    final = finalize(with_music, work / "final.mp4", max_seconds=seconds)
    progress.done("Scenery promo ready")
    return final, plan, usage, track, visual_source
