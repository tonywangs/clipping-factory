# ClipFactory

ClipFactory finds long-form podcast episodes, transcribes them with word timings, ranks
high-retention moments, renders captioned vertical clips, and places them in a reviewable
outbox. Posting is intentionally manual.

## Local setup

```bash
cp .env.example .env
make setup
python -m clipfactory.run --episode "https://www.youtube.com/watch?v=VIDEO_ID" --niche startup
make dashboard
```

The output is `outbox/<niche>/<date>_<slug>/clip.mp4`, `cover.jpg`, and `meta.json`.
For scheduled sources, add rights-aware sources in `config/sources.yaml`, then run
`python -m clipfactory.run --once`. State tracks per-niche runs: completed niches are
skipped, while failed niches are retried on the next `--once`.

## Configuration

Everything account-specific belongs in `config/niches/*.yaml`: topic targeting, score,
length, caption style, colors, hashtags, hooks, and music. Add only royalty-free tracks
under `assets/music/<niche>/`; a missing folder skips music without failing a clip.

Set `LLM_PROVIDER=anthropic|openai|gemini` and its matching API key. Anthropic is the
default. Optional `YOUTUBE_API_KEY` uses the YouTube Data API for discovery (falls back to
yt-dlp). `WHISPER_DEVICE=cuda` enables a supported local CUDA worker; Cloud Run uses CPU
with `base` and int8 defaults.

## Review and feedback

Open `http://localhost:8000` after `make dashboard`. Approving moves a package into
`approved/`; rejecting requires a reason, moves it into `rejected/`, and appends feedback
used by later ranking prompts. The dashboard marks `unlicensed` clips clearly.

## Storage and cloud

`STORAGE_BACKEND=local` is the default. Cloud mode stores binary artifacts in GCS and uses
Firestore for state; it never mounts a SQLite database from GCS. Build the Docker image and
follow [infra/scheduler.md](infra/scheduler.md) for a 6am Pacific Cloud Scheduler job.

## yt-dlp failures

YouTube may reject data-center downloads. Configure `YTDLP_COOKIES_FILE` first, then
`YTDLP_PLAYER_CLIENTS`/PO-token support or `YTDLP_PROXY`. The pipeline records the failure
and continues other sources. A supported operating mode is local ingest followed by cloud
processing of the cached input.

## Rights and safety

Prioritize `campaign_licensed` and `clipping_encouraged` sources. `unlicensed` is processed
only at the operator's risk and remains stamped in metadata. ClipFactory deliberately has no
pitch shifting, mirroring, crop tricks, or other Content-ID evasion controls. It also does not
automate TikTok or other platform uploads.
