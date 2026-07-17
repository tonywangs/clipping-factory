from __future__ import annotations

import argparse
import json
import os
import traceback
from pathlib import Path

from dotenv import load_dotenv

from .config import load_all_niches, load_niche, load_settings, load_sources, project_root
from .deliver import notify_summary
from .discover import discover_sources
from .ingest import ingest_episode
from .models import Episode
from .package import package_clip
from .rank import rank_candidates
from .render import render_clip
from .state import build_state
from .storage import build_storage
from .transcribe import transcribe


def process_episode(episode: Episode, niche_name: str, settings, state) -> list[dict]:
    niche = load_niche(niche_name)
    if not state.claim_niche_run(episode.source_id, episode.external_id, niche.name):
        return []
    root = project_root()
    storage = build_storage(settings.storage_backend, os.getenv("GCS_BUCKET"))
    def artifact_key(path: Path, fallback_prefix: str = "raw") -> str:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return f"{fallback_prefix}/{path.name}"
    try:
        episode = ingest_episode(episode, root / settings.raw_dir, settings.download_max_height)
        storage.put_file(episode.local_path, artifact_key(episode.local_path))
        state.upsert_episode(episode)
        transcript = transcribe(episode.local_path, root / settings.transcript_dir, settings.whisper_model, settings.whisper_device)
        transcript_path = root / settings.transcript_dir / f"{episode.local_path.stem}.json"
        storage.put_file(transcript_path, str(transcript_path.relative_to(root)))
        candidates = rank_candidates(transcript, niche, state.recent_feedback(niche.name))
        produced: list[dict] = []
        for candidate in candidates:
            temporary = root / settings.work_dir / f"{episode.source_id}_{episode.external_id}_{candidate.start:.3f}.mp4"
            music = render_clip(episode, candidate, transcript, niche, root / settings.work_dir, temporary)
            package = package_clip(temporary, episode, candidate, niche, root / settings.outbox_dir, music)
            for artifact in (package.clip_path, package.cover_path, package.directory / "meta.json"):
                storage.put_file(artifact, str(artifact.relative_to(root)))
            state.add_clip(package.clip_id, episode.source_id, episode.external_id, niche.name, str(package.directory), package.meta.model_dump(mode="json"))
            produced.append({"clip_id": package.clip_id, "title": package.meta.title, "score": package.meta.score, "path": str(package.directory)})
        state.finish_niche_run(episode.source_id, episode.external_id, niche.name, "completed")
        return produced
    except Exception as exc:
        state.finish_niche_run(episode.source_id, episode.external_id, niche.name, "failed", str(exc))
        raise


def run_once(settings, state) -> dict:
    sources = load_sources().sources
    episodes = discover_sources(sources, state, settings.max_new_episodes_per_run)
    clips, errors = [], []
    for episode in episodes:
        for niche in next(source.niches for source in sources if source.id == episode.source_id):
            try:
                clips.extend(process_episode(episode, niche, settings, state))
            except Exception as exc:
                errors.append({"source_id": episode.source_id, "episode": episode.title, "error": str(exc)})
    summary = {"episodes_discovered": len(episodes), "clips": clips, "errors": errors, "cost_estimate_usd": None}
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
    episode = Episode(source_id="manual", external_id=local.stem if local.exists() else args.episode.rsplit("=", 1)[-1], title=local.stem if local.exists() else args.episode,
        url=args.episode, video=local.suffix.lower() not in {".mp3", ".wav", ".m4a"}, license_status="unlicensed", local_path=local if local.exists() else None)
    if local.exists():
        import hashlib
        episode.content_hash = hashlib.sha256(local.read_bytes()).hexdigest()
    clips = process_episode(episode, args.niche, settings, state)
    print(json.dumps({"clips": clips}, indent=2))


if __name__ == "__main__":
    main()
