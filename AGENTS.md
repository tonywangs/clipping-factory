# AGENTS

## Cursor Cloud specific instructions

ClipFactory is a local-first Python pipeline that discovers podcast episodes, transcribes
them, ranks viral moments with an LLM, renders captioned vertical clips into a reviewable
`outbox/`, and serves a FastAPI review dashboard. Standard commands live in `README.md` and
the `Makefile` (`make setup|test|lint|dashboard|run`); prefer those. Notes below are the
non-obvious caveats.

### Environment
- Package manager is `uv` (already installed; the startup update script runs
  `uv sync --extra local --extra test`). Run all commands via `uv run ...` or the Makefile.
- `ffmpeg`/`ffprobe` with the libass `subtitles` filter are required for rendering and are
  present in the base image, so `FFMPEG_BINARY`/`FFPROBE_BINARY` overrides are not needed here.
- Copy `.env.example` to `.env` before running (dotenv is loaded at startup).

### Running / testing services
- Lint: `make lint` (bytecode `compileall`, not a style linter). Tests: `make test`
  (pytest; 20 pass, 1 skipped by default).
- Dashboard: `make dashboard` serves the review UI on port `8000`.
- Pipeline entrypoint: `python -m clipfactory.run --episode "<url|local path>" --niche startup`,
  or `make run` (`--once`).

### Non-obvious caveats
- Real ranking calls an external LLM and needs a provider key (`ANTHROPIC_API_KEY` by default,
  or `OPENAI_API_KEY`/`GEMINI_API_KEY` with `LLM_PROVIDER`). Without a key the rank step fails;
  the test suite injects fakes so no key is needed for tests.
- `--once` discovers nothing out of the box: `config/sources.yaml` ships `sources: []`. To
  exercise the pipeline without live sources or network, pass a local media file to `--episode`
  (a local path bypasses yt-dlp download).
- YouTube downloads are frequently blocked from data-center IPs; prefer a local file for
  offline/end-to-end runs, or configure `YTDLP_COOKIES_FILE`/`YTDLP_PROXY`.
- `faster-whisper` downloads model weights on first transcription (needs egress); the default
  model is `base` on CPU int8.
- The dashboard loads htmx from the unpkg CDN, so Approve/Reject buttons require browser egress
  to `unpkg.com`; if that is blocked the page renders but the buttons do nothing (the backend
  endpoints still work, e.g. `POST /clips/<clip_id>/approved`).
- Runtime output and state live under gitignored dirs: `outbox/`, `approved/`, `rejected/`,
  `work/`, `raw/`, `transcripts/`, `feedback/`, and SQLite state at `data/clipfactory.sqlite3`.
- The opt-in golden e2e smoke test runs only with `CLIPFACTORY_E2E=1`.
