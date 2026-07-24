# Decisions

## 2026-07-16: engine boundary
`engine/` vendors the MIT-licensed SamurAIGPT generator at
`063f9e950f331fdf4a5dd787be4390fe3a960148`. We reuse its local downloader,
highlight chunking/dedupe, and OpenCV crop concept while ClipFactory owns the
pipeline, state, packaging, and review workflow.

## 2026-07-16: captions
Caption rendering is an original `pysubs2` + libass implementation informed by
brainrotinator's documented SRT/ASS approach. No brainrotinator source is copied
because its license disallows commercial cloud-service use.

## 2026-07-16: podcli boundary
Podcli's public caption-style, knowledge-base, and tracking ideas informed the
product shape only. No code is copied because podcli is AGPL-3.0.

## 2026-07-16: secondary references
Cliper-AI, hotclip, and ai-clipping-generator were evaluated at a high level.
None offered a caption renderer or detector that justified a dependency over the
MIT engine plus our own renderer.

## 2026-07-16: cloud state
Cloud Run uses Firestore for coordination and GCS for binary artifacts. SQLite is
local-only; a SQLite file on a GCS mount is not a supported state store.

## 2026-07-17: discovery dedupe is per-niche
`--once` rediscovers an episode while any configured niche run is missing or
`failed`. Completed niches stay blocked by `claim_niche_run`; episode-level
presence alone is not enough to skip unfinished niches.

## 2026-07-17: clip identity
`clip_id` is `sha256(source_id:external_id:niche:start:end)[:16]` and is written
into `meta.json` so the dashboard approve/reject path updates the same state row
the ranker reads for rejection feedback.

## 2026-07-17: YouTube discovery
When `YOUTUBE_API_KEY` is set, discovery prefers the YouTube Data API for channel
handles, channel IDs, and playlists, then falls back to yt-dlp flat playlists.

## 2026-07-23: content creation suite
`clipfactory/formats/` initially added five generated formats (history POV, ASMR
sequencer, ranked polls, mood montages, fancam edits) behind
`python -m clipfactory.create`; scenery promotions were added as the sixth.
Shared ffmpeg helpers live in `formats/base.py`; all formats reuse the podcast
outbox/meta/dashboard pipeline. TTS prefers OpenAI then free edge-tts. Image
generation prefers operator folders, then OpenAI/Gemini images, then styled text
cards so builds never hard-fail. ASMR/montage source media is operator-supplied
(AI-video exports / rights-cleared b-roll); no copyrighted music is downloaded,
and fancam/montage outputs are stamped `unlicensed` where third-party media is
involved. Transition SFX is synthesized with ffmpeg when no assets exist.

## 2026-07-24: scenery music-promotion format
`create scenery` produces the deliberately minimal format seen on high-volume
scenery accounts: one generated/supplied atmospheric visual, subtle Ken Burns
motion (or a looped AI-video export), one campaign music hook, no text, ~10
seconds. Image generation tries OpenAI then Gemini and can be pinned with
`--image-provider`; operator media remains supported through `--source`.
Promotion music is never downloaded: it comes from `--music` or
`assets/music/promotions/<campaign>/`. Outputs are stamped
`campaign_licensed` and tagged with campaign/artist/track for dashboard review.

## 2026-07-19: self-contained clips + dual framing
Ranker prompt requires zero-prior-context openings and pulls start back to a nearby
host question when present. Reframing detects stable left/right two-face layouts and
uses a stacked 9:16 split; otherwise single-face tracking uses a snap cooldown so
the crop does not thrash between host and guest.
