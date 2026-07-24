# Modal + Wan 2.2 video generation

Scenery generation runs remotely on Modal. Your Mac does **not** run the AI
video model, upscale, interpolation, or final music render.

## Why Wan 2.2

- Apache 2.0 weights; commercial use is permitted.
- Strong prompt adherence, scenery motion, and photorealism.
- Mature Hugging Face Diffusers integration.
- `wan-5b`: practical 720p model on one H100.
- `wan-a14b`: larger max-quality model on one H200.

LTX-2 was not selected because its weights use a custom community license.
Wan's Apache 2.0 terms are simpler for commercial content.

## One-time setup

From the repository:

```bash
git pull
make setup
```

Authenticate the Modal CLI. This opens a browser and connects the CLI to the
Modal account containing your credits:

```bash
uv run modal setup
```

Download the practical model weights into a persistent Modal Volume:

```bash
uv run modal run infra/modal_wan_video.py::download_wan_5b
```

This is a large one-time download and may take 10–45 minutes. Then deploy:

```bash
uv run modal deploy infra/modal_wan_video.py
```

You can now generate:

```bash
uv run python -m clipfactory.create scenery \
  --prompt "rainy moss forest, flowing waterfall, drifting fog, swaying leaves" \
  --campaign misty-calm-wisps \
  --artist "Kevin MacLeod"
```

## Max-quality A14B profile

Download the much larger model once:

```bash
uv run modal run infra/modal_wan_video.py::download_wan_a14b
uv run modal deploy infra/modal_wan_video.py
```

Generate with:

```bash
uv run python -m clipfactory.create scenery \
  --prompt "fantasy city at sunset, moving clouds, flags blowing, slow aerial camera" \
  --campaign dreamy-electronic-pamgaea \
  --artist "Kevin MacLeod" \
  --modal-model wan-a14b
```

## Profiles, runtime, and cost

| Profile | GPU | Model | Typical warm generation | Approx. GPU list-price cost |
|---|---|---|---|---|
| `wan-5b` (default) | H100 | Wan 2.2 TI2V-5B | ~2–6 min | ~$0.13–$0.40 |
| `wan-a14b` | H200 | Wan 2.2 I2V-A14B | ~5–20 min | ~$0.38–$1.51 |

Estimates use Modal's July 2026 list rates (H100 ~$3.95/hour, H200
~$4.54/hour). Cold model loading adds time. Check Modal's current pricing and
dashboard for actual spend.

The default produces 121 genuinely generated frames at 704×1280 and presents
them as a slow atmospheric 10-second shot. The max profile generates 81
higher-quality A14B frames and performs slow-motion interpolation remotely.
Both are upscaled, music-mixed, loudness-normalized, and encoded to 1080×1920
inside Modal.

## Monitoring and troubleshooting

Open the Modal dashboard:

```bash
uv run modal app logs clipfactory-wan-video
```

If the CLI says the app/function cannot be found, redeploy:

```bash
uv run modal deploy infra/modal_wan_video.py
```

If weights are missing, rerun the appropriate `download_wan_*` command.

Model weights persist in `clipfactory-wan-models` and may incur Volume storage
cost. Delete them only if you want to remove the deployment:

```bash
uv run modal app stop clipfactory-wan-video
uv run modal volume delete clipfactory-wan-models
```
