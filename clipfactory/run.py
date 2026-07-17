from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .config import load_niche, load_settings, load_sources, project_root
from .deliver import notify_summary
from .discover import discover_sources
from .ingest import ingest_episode
from .models import Episode, LicenseStatus
from .package import package_clip
from .rank import TokenUsage, estimate_cost_usd, rank_candidates
from .render import render_clip
from .state import build_state
from .storage import build_storage
from .transcribe import transcribe
from .transcribe.service import media_content_hash


def process_episode(episode: Episode, niche_name: str, settings, state) -> tuple[list[dict], dict]:
    niche = load_niche(niche_name)
    if not state.claim_niche_run(episode.source_id, episode.external_id, niche.name):
        return [], {"input_tokens": 0, "output_tokens": 0}
    root = project_root()
    storage = build_storage(settings.storage_backend, os.getenv("GCS_BUCKET"))

    def artifact_key(path: Path, fallback_prefix: str = "raw") -> str:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return f"{fallback_prefix}/{path.name}"

    usage = {"input_tokens": 0, "output_tokens": 0}
    try:
        episode = ingest_episode(episode, root / settings.raw_dir, settings.download_max_height)
        if episode.local_path is None:
            raise FileNotFoundError("Ingest did not produce a local media path")
        if not episode.content_hash:
            episode.content_hash = media_content_hash(episode.local_path)
        storage.put_file(episode.local_path, artifact_key(episode.local_path))
        state.upsert_episode(episode)
        transcript = transcribe(
            episode.local_path,
            root / settings.transcript_dir,
            settings.whisper_model,
            settings.whisper_device,
            content_hash=episode.content_hash,
        )
        transcript_path = root / settings.transcript_dir / f"{episode.content_hash}.json"
        if transcript_path.exists():
            storage.put_file(transcript_path, str(transcript_path.relative_to(root)))
        ranked = rank_candidates(transcript, niche, state.recent_feedback(niche.name))
        usage = {"input_tokens": ranked.usage.input_tokens, "output_tokens": ranked.usage.output_tokens}
        produced: list[dict] = []
        for candidate in ranked.candidates:
            temporary = root / settings.work_dir / f"{episode.source_id}_{episode.external_id}_{candidate.start:.3f}.mp4"
            music = render_clip(episode, candidate, transcript, niche, root / settings.work_dir, temporary)
            package = package_clip(temporary, episode, candidate, niche, root / settings.outbox_dir, music)
            for artifact in (package.clip_path, package.cover_path, package.directory / "meta.json"):
                storage.put_file(artifact, str(artifact.relative_to(root)))
            state.add_clip(
                package.clip_id,
                episode.source_id,
                episode.external_id,
                niche.name,
                str(package.directory),
                package.meta.model_dump(mode="json"),
            )
            produced.append(
                {
                    "clip_id": package.clip_id,
                    "title": package.meta.title,
                    "score": package.meta.score,
                    "path": str(package.directory),
                }
            )
        state.finish_niche_run(episode.source_id, episode.external_id, niche.name, "completed")
        return produced, usage
    except Exception as exc:
        state.finish_niche_run(episode.source_id, episode.external_id, niche.name, "failed", str(exc))
        raise


def run_once(settings, state) -> dict:
    sources = load_sources().sources
    source_by_id = {source.id: source for source in sources}
    episodes = discover_sources(sources, state, settings.max_new_episodes_per_run)
    clips, errors = [], []
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    for episode in episodes:
        source = source_by_id[episode.source_id]
        for niche in source.niches:
            try:
                produced, usage = process_episode(episode, niche, settings, state)
                clips.extend(produced)
                total_usage["input_tokens"] += usage["input_tokens"]
                total_usage["output_tokens"] += usage["output_tokens"]
            except Exception as exc:
                errors.append({"source_id": episode.source_id, "episode": episode.title, "niche": niche, "error": str(exc)})
    cost = estimate_cost_usd(TokenUsage(**total_usage), settings.costs_per_million_tokens)
    summary = {
        "episodes_discovered": len(episodes),
        "clips": clips,
        "errors": errors,
        "token_usage": total_usage,
        "cost_estimate_usd": cost,
    }
    state.record_run(summary)
    notify_summary(summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="ClipFactory local-first clipping pipeline")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Discover and process new configured episodes")
    mode.add_argument("--episode", help="YouTube URL or local media path")
    parser.add_argument("--niche", help="Niche required with --episode")
    args = parser.parse_args(argv)
    settings = load_settings()
    state = build_state(settings.state_backend, os.getenv("FIRESTORE_PROJECT"))
    if args.once:
        print(json.dumps(run_once(settings, state), indent=2))
        return
    if not args.niche:
        parser.error("--niche is required with --episode")
    local = Path(args.episode).expanduser()
    if local.exists():
        episode = Episode(
            source_id="manual",
            external_id=local.stem,
            title=local.stem,
            url=str(local),
            video=local.suffix.lower() not in {".mp3", ".wav", ".m4a"},
            license_status=LicenseStatus.UNLICENSED,
            local_path=local,
            content_hash=media_content_hash(local),
        )
    else:
        external_id = args.episode.rsplit("=", 1)[-1].rsplit("/", 1)[-1]
        episode = Episode(
            source_id="manual",
            external_id=external_id,
            title=args.episode,
            url=args.episode,
            video=True,
            license_status=LicenseStatus.UNLICENSED,
        )
    clips, usage = process_episode(episode, args.niche, settings, state)
    cost = estimate_cost_usd(TokenUsage(**usage), settings.costs_per_million_tokens)
    print(json.dumps({"clips": clips, "token_usage": usage, "cost_estimate_usd": cost}, indent=2))


if __name__ == "__main__":
    main()
