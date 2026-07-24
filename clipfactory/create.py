"""ClipFactory content creation CLI — beyond podcast clipping.

Formats:
  history  — AI "day in the life" history POV (script → TTS → slideshow)
  asmr     — fantasy-object ASMR sequencing (glass fruit etc., operator clips)
  poll     — "which X would you pick" ranked slideshow
  montage  — mood montage (music over scenery b-roll)
  fancam   — iconic-moments edit with loud transitions
  scenery  — 10-second AI scenery + music-promotion track

Examples:
  python -m clipfactory.create history --topic "day in the life of a victorian child"
  python -m clipfactory.create asmr --collection glass-fruit
  python -m clipfactory.create poll --topic "which bedroom would you sleep in the hardest"
  python -m clipfactory.create montage --collection nyc-rain --mood sad
  python -m clipfactory.create fancam --source dance_moms_s2e3.mp4 --subject "maddie ziegler"
  python -m clipfactory.create scenery --prompt "aurora over a black-sand beach" --music track.mp3
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

from .config import load_settings, project_root
from .formats import (
    build_asmr_video,
    build_fancam_video,
    build_history_video,
    build_montage_video,
    build_poll_video,
    build_scenery_promo,
    package_generated,
    parse_moments,
    plan_from_transcript,
)
from .formats.fancam import FancamPlan
from .ids import make_run_id
from .models import LicenseStatus
from .progress import Progress
from .state import build_state


def _finish(video: Path, *, args, format_name: str, run_id: str, title: str, caption: str, hashtags: list[str], hook: str, reason: str, license_status: LicenseStatus, source_ref: str = "generated", music_track: str | None = None) -> dict:
    progress = Progress("package")
    settings = load_settings()
    state = build_state(settings.state_backend, os.getenv("FIRESTORE_PROJECT"))
    progress.emit("Writing clip.mp4, cover.jpg, and meta.json to the outbox…")
    package = package_generated(
        video,
        format_name=format_name,
        niche=args.niche or format_name,
        run_id=run_id,
        title=title,
        caption=caption,
        hashtags=hashtags,
        hook_sentence=hook,
        reason=reason,
        score=75,
        license_status=license_status,
        tags=list(args.tag or []),
        source_ref=source_ref,
        music_track=music_track,
    )
    progress.emit("Recording clip in the review state database…")
    state.add_clip(
        package.clip_id,
        format_name,
        package.meta.external_id,
        package.meta.niche,
        str(package.directory),
        package.meta.model_dump(mode="json"),
    )
    progress.done(f"Packaged at {package.directory}")
    return {
        "clip_id": package.clip_id,
        "run_id": run_id,
        "title": title,
        "path": str(package.directory),
    }


def cmd_history(args, run_id: str, work: Path) -> dict:
    video, script, usage = build_history_video(args.topic, work, music_mood=args.music_mood, voice=args.voice)
    result = _finish(
        video,
        args=args,
        format_name="history",
        run_id=run_id,
        title=args.topic,
        caption=script.caption,
        hashtags=script.hashtags or ["#history", "#pov", "#fyp"],
        hook=script.hook,
        reason="AI history POV",
        license_status=LicenseStatus.ORIGINAL,
    )
    result["token_usage"] = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    return result


def cmd_asmr(args, run_id: str, work: Path) -> dict:
    video, plan, usage = build_asmr_video(args.collection, work, target_seconds=args.seconds)
    result = _finish(
        video,
        args=args,
        format_name="asmr",
        run_id=run_id,
        title=plan.title,
        caption=plan.caption,
        hashtags=plan.hashtags,
        hook=plan.label,
        reason="ASMR sequence",
        license_status=LicenseStatus.ORIGINAL,
    )
    result["token_usage"] = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    return result


def cmd_poll(args, run_id: str, work: Path) -> dict:
    video, plan, usage = build_poll_video(args.topic, work, options=args.options, music_mood=args.music_mood)
    result = _finish(
        video,
        args=args,
        format_name="poll",
        run_id=run_id,
        title=args.topic,
        caption=plan.caption,
        hashtags=plan.hashtags or ["#wouldyourather", "#fyp"],
        hook=plan.intro,
        reason="ranked poll slideshow",
        license_status=LicenseStatus.ORIGINAL,
    )
    result["token_usage"] = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    return result


def cmd_montage(args, run_id: str, work: Path) -> dict:
    video, plan, usage = build_montage_video(
        args.collection,
        work,
        mood=args.mood,
        target_seconds=args.seconds,
        use_music=not args.no_music,
    )
    result = _finish(
        video,
        args=args,
        format_name="montage",
        run_id=run_id,
        title=plan.overlay,
        caption=plan.caption,
        hashtags=plan.hashtags,
        hook=plan.overlay,
        reason="mood montage",
        license_status=LicenseStatus.UNLICENSED if not args.no_music else LicenseStatus.ORIGINAL,
    )
    result["token_usage"] = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    return result


def cmd_fancam(args, run_id: str, work: Path) -> dict:
    source = Path(args.source).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Source video not found: {source}")
    usage_tokens = {"input_tokens": 0, "output_tokens": 0}
    if args.moments:
        plan = FancamPlan(
            overlay=args.overlay or f"{args.subject} attitude",
            caption=args.caption or f"{args.subject} edit \U0001f60d",
            hashtags=["#edit", "#fancam", "#fyp"],
            moments=parse_moments(args.moments),
        )
    else:
        progress = Progress("fancam")
        progress.emit("No manual moments supplied; transcribing source video…")
        settings = load_settings()
        from .transcribe import transcribe
        from .transcribe.service import media_content_hash

        transcript = transcribe(
            source,
            project_root() / settings.transcript_dir,
            settings.whisper_model,
            settings.whisper_device,
            content_hash=media_content_hash(source),
        )
        progress.emit("Transcript ready; asking the LLM for iconic moments…")
        plan, usage = plan_from_transcript(transcript, args.subject)
        progress.emit(f"Selected {len(plan.moments)} moment(s)")
        usage_tokens = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
        if args.overlay:
            plan.overlay = args.overlay
    video = build_fancam_video(source, plan, work, sfx_kind=args.sfx)
    result = _finish(
        video,
        args=args,
        format_name="fancam",
        run_id=run_id,
        title=plan.overlay,
        caption=plan.caption,
        hashtags=plan.hashtags,
        hook=plan.overlay,
        reason="fancam edit",
        license_status=LicenseStatus.UNLICENSED,
        source_ref=str(source),
    )
    result["token_usage"] = usage_tokens
    return result


def cmd_scenery(args, run_id: str, work: Path) -> dict:
    source = Path(args.source).expanduser() if args.source else None
    video, plan, usage, track, visual_source = build_scenery_promo(
        args.prompt,
        work,
        music=args.music,
        campaign=args.campaign,
        artist=args.artist,
        source=source,
        image_provider=args.image_provider,
        seconds=args.seconds,
        music_start=args.music_start,
        music_db=args.music_db,
        video_provider=args.video_provider,
        modal_model=args.modal_model,
        seed=args.seed,
    )
    campaign_tags = [
        f"campaign:{args.campaign}",
        f"track:{track.stem}",
    ]
    if args.artist:
        campaign_tags.append(f"artist:{args.artist}")
    args.tag = [*list(args.tag or []), *campaign_tags]
    result = _finish(
        video,
        args=args,
        format_name="scenery",
        run_id=run_id,
        title=plan.title,
        caption=plan.caption,
        hashtags=plan.hashtags,
        hook=args.prompt,
        reason="atmospheric scenery music promotion",
        license_status=LicenseStatus.CAMPAIGN_LICENSED,
        source_ref=visual_source,
        music_track=track.name,
    )
    result["music_track"] = str(track)
    result["campaign"] = args.campaign
    result["token_usage"] = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }
    return result


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="ClipFactory viral content creation suite")
    sub = parser.add_subparsers(dest="format", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--niche", default=None, help="Outbox niche folder (default: format name)")
        p.add_argument("--run-label", default=None)
        p.add_argument("--tag", action="append", default=[])
        p.add_argument("--keep-work", action="store_true", help="Keep intermediate render files")

    p_history = sub.add_parser("history", help="AI day-in-the-life history POV")
    p_history.add_argument("--topic", required=True, help='e.g. "day in the life of a victorian child"')
    p_history.add_argument("--music-mood", default="cinematic")
    p_history.add_argument("--voice", default="", help="TTS voice override")
    common(p_history)

    p_asmr = sub.add_parser("asmr", help="Fantasy-object ASMR from assets/broll/asmr/<collection>")
    p_asmr.add_argument("--collection", required=True, help='e.g. "glass-fruit"')
    p_asmr.add_argument("--seconds", type=float, default=34.0)
    common(p_asmr)

    p_poll = sub.add_parser("poll", help='"which one would you pick" slideshow')
    p_poll.add_argument("--topic", required=True, help='e.g. "which bedroom would you sleep in the hardest"')
    p_poll.add_argument("--options", type=int, default=6)
    p_poll.add_argument("--music-mood", default="suspense")
    common(p_poll)

    p_montage = sub.add_parser("montage", help="Mood montage from assets/broll/<collection>")
    p_montage.add_argument("--collection", required=True, help='e.g. "nyc-rain"')
    p_montage.add_argument("--mood", default="sad", help="assets/music/moods/<mood>/")
    p_montage.add_argument("--seconds", type=float, default=30.0)
    p_montage.add_argument("--no-music", action="store_true", help="Render silent; add trending sound in TikTok")
    common(p_montage)

    p_fancam = sub.add_parser("fancam", help="Iconic-moments edit with loud transitions")
    p_fancam.add_argument("--source", required=True, help="Local video file")
    p_fancam.add_argument("--subject", required=True, help='e.g. "maddie ziegler"')
    p_fancam.add_argument("--moments", default=None, help='Manual timestamps: "12.5-16,42-45.5"')
    p_fancam.add_argument("--overlay", default=None, help="On-screen text override")
    p_fancam.add_argument("--caption", default=None)
    p_fancam.add_argument("--sfx", default="boom", choices=["boom", "whoosh", "glitch"])
    common(p_fancam)

    p_scenery = sub.add_parser(
        "scenery",
        help="10-second AI scenery video for a music-promotion campaign",
    )
    p_scenery.add_argument(
        "--prompt",
        required=True,
        help='e.g. "rainy moss forest with a stone bridge at blue hour"',
    )
    p_scenery.add_argument(
        "--music",
        default=None,
        help="Promotion track file/folder; otherwise assets/music/promotions/<campaign>/",
    )
    p_scenery.add_argument(
        "--campaign",
        default="default",
        help="Campaign name used for music folder and dashboard tags",
    )
    p_scenery.add_argument("--artist", default="", help="Artist/brand for dashboard tags")
    p_scenery.add_argument(
        "--source",
        default=None,
        help="Optional existing AI-generated image/video instead of generating one",
    )
    p_scenery.add_argument(
        "--image-provider",
        choices=["auto", "openai", "gemini"],
        default="auto",
    )
    p_scenery.add_argument(
        "--video-provider",
        choices=["modal-wan", "image"],
        default="modal-wan",
        help="Real Wan 2.2 video on Modal (default), or legacy image zoom",
    )
    p_scenery.add_argument(
        "--modal-model",
        choices=["wan-5b", "wan-a14b"],
        default="wan-5b",
        help="wan-5b: practical H100; wan-a14b: slow max-quality H200",
    )
    p_scenery.add_argument("--seed", type=int, default=0)
    p_scenery.add_argument("--seconds", type=float, default=10.0)
    p_scenery.add_argument(
        "--music-start",
        type=float,
        default=0.0,
        help="Seconds into the track where its hook begins",
    )
    p_scenery.add_argument("--music-db", type=float, default=-2.0)
    common(p_scenery)

    args = parser.parse_args(argv)
    run_id = make_run_id(args.run_label or args.format)
    work = project_root() / "work" / f"{args.format}_{run_id}"
    progress = Progress("create")
    progress.emit(f"Starting {args.format} run {run_id}")
    progress.emit(f"Intermediate files: {work}")
    handlers = {
        "history": cmd_history,
        "asmr": cmd_asmr,
        "poll": cmd_poll,
        "montage": cmd_montage,
        "fancam": cmd_fancam,
        "scenery": cmd_scenery,
    }
    try:
        result = handlers[args.format](args, run_id, work)
    finally:
        if not args.keep_work and work.exists():
            progress.emit("Cleaning intermediate render files…")
            shutil.rmtree(work, ignore_errors=True)
    progress.done(f"Output ready: {result['path']}")
    print(json.dumps({"format": args.format, **result}, indent=2))


if __name__ == "__main__":
    main()
