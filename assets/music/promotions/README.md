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
