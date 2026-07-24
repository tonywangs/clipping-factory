# Music promotion campaigns

Put one paid-promotion track (or licensed preview) in a campaign folder:

```text
assets/music/promotions/artist-july/track.mp3
```

Then run:

```bash
uv run python -m clipfactory.create scenery \
  --prompt "misty waterfall in an ancient forest" \
  --campaign artist-july \
  --artist "Artist Name" \
  --music-start 18.5
```

`--music-start` selects the strongest hook in the track. You can also bypass
this folder entirely with `--music /absolute/path/to/track.mp3`.

Only use music you are authorized to promote. ClipFactory records the campaign,
artist, and track as tags in `meta.json`.

## Ready-to-use demo campaigns

The repository includes three one-minute CC BY 4.0 excerpts that permit
commercial use **with attribution**:

- `misty-calm-wisps` — calm ambient
- `dreamy-electronic-pamgaea` — relaxed electronic
- `fantasy-river-of-io` — mysterious/fantasy

The generator automatically appends each track's required credit to the post
caption. See `DEMO_TRACKS_LICENSES.md` for sources and terms.
