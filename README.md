# ClipFactory

ClipFactory is a viral short-form content factory. It started as a podcast clipper —
find episodes, transcribe with word timings, rank high-retention moments, render
captioned vertical clips — and now also generates original TikTok formats end to end.
Posting is intentionally manual.

## Content formats (`python -m clipfactory.create ...`)

| Format | Command | Needs |
|---|---|---|
| AI history POV ("day in the life of a victorian child") | `create history --topic "..."` | LLM key; TTS (OpenAI key or free edge-tts); images auto-generate with OpenAI/Gemini, else styled cards |
| Glass-fruit ASMR | `create asmr --collection glass-fruit` | AI video clips you export into `assets/broll/asmr/glass-fruit/` |
| "Which bedroom would you sleep in the hardest" polls | `create poll --topic "..."` | LLM key; images same as history |
| Sad-music scenery montage (NYC rain) | `create montage --collection nyc-rain --mood sad` | b-roll in `assets/broll/nyc-rain/`, tracks in `assets/music/moods/sad/` (or `--no-music`, add sound in TikTok) |
| Fancam edits ("maddie ziegler attitude", loud booms) | `create fancam --source ep.mp4 --subject "maddie ziegler"` | a source video; moments auto-found via transcript or `--moments "12-15,40-44"` |
| 10-second scenery music promos | `create scenery --prompt "aurora over a black-sand beach" --music track.mp3` | Modal account + Wan 2.2 deployment; OpenAI/Gemini generates the starting keyframe |

All formats land in the same `outbox/<niche>/<run_id>/` structure with `meta.json`,
so the review dashboard, run filters, and approve/reject flow work unchanged.
Generated content is stamped `license_status: original`; scenery promotions are
`campaign_licensed`; fancam/montage using others' footage or commercial music is
stamped `unlicensed` and flagged in the dashboard.

### Scenery music-promotion workflow

This format intentionally stays simple: one strong vertical shot, one music hook,
approximately 10 seconds, and no on-screen text. The default is now **real Wan
2.2 AI video generation on Modal**—not a zoomed still. Your laptop only sends a
keyframe/prompt/music and downloads the finished clip.

One-time Modal setup: follow [`infra/modal.md`](infra/modal.md).

```bash
# Generate a starting keyframe, then animate it into real video with Wan 2.2 on Modal:
uv run python -m clipfactory.create scenery \
  --prompt "rainy moss forest, ancient stone bridge, blue-hour fog" \
  --music ~/Downloads/artist-track.mp3 \
  --campaign artist-july \
  --artist "Artist Name" \
  --music-start 18.5

# Force Gemini image generation:
uv run python -m clipfactory.create scenery \
  --prompt "aurora above a frozen black-sand beach" \
  --music ~/Downloads/track.mp3 \
  --image-provider gemini

# Use a supplied keyframe instead of generating one:
uv run python -m clipfactory.create scenery \
  --prompt "fantasy Arabian city at sunset" \
  --source ~/Downloads/cityscape.png \
  --music ~/Downloads/track.mp3

# Max-quality A14B profile (H200; slower and more expensive):
uv run python -m clipfactory.create scenery \
  --prompt "misty fantasy waterfall, real flowing water and drifting fog" \
  --campaign misty-calm-wisps \
  --modal-model wan-a14b
```

Instead of `--music`, put a campaign track in
`assets/music/promotions/<campaign>/`. Outputs are tagged with campaign, artist,
and track in `meta.json` and appear in the normal review dashboard.

The old image-zoom implementation remains only as an explicit fallback:
`--video-provider image`.

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

Open `http://localhost:8000` after `make dashboard`. The dashboard **defaults to the
latest run** so older experiments do not clutter review. Filter by niche/run, or choose
**all runs**. Approving moves a package into `approved/`; rejecting requires a reason,
moves it into `rejected/`, and appends feedback used by later ranking prompts.

Clips land in `outbox/<niche>/<run_id>/<slug>/` with `run_id` + optional tags in
`meta.json`. Tag a run when you launch it:

```bash
uv run python -m clipfactory.run --episode URL --niche startup --force \
  --run-label framing-v2 --tag framing-v2 --tag context-fix
```

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
