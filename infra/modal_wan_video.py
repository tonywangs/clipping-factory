"""Modal deployment for real Wan 2.2 scenery video generation.

Deploy:
    modal run infra/modal_wan_video.py::download_wan_5b
    modal deploy infra/modal_wan_video.py

Optional max-quality weights:
    modal run infra/modal_wan_video.py::download_wan_a14b

The 5B function runs on one H100. The A14B function runs on one H200.
Both return a finished 1080x1920 video with the supplied music already mixed,
so the user's laptop does no video rendering.
"""

from __future__ import annotations

import modal

APP_NAME = "clipfactory-wan-video"
MODEL_VOLUME_NAME = "clipfactory-wan-models"
MODEL_ROOT = "/models"

WAN_5B_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
WAN_A14B_ID = "Wan-AI/Wan2.2-I2V-A14B-Diffusers"

app = modal.App(APP_NAME)
model_volume = modal.Volume.from_name(MODEL_VOLUME_NAME, create_if_missing=True)

wan_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "git")
    .uv_pip_install(
        "accelerate",
        "ftfy",
        "huggingface-hub[hf-xet]",
        "imageio",
        "imageio-ffmpeg",
        "numpy",
        "pillow",
        "safetensors",
        "sentencepiece",
        "torch",
        "torchvision",
        "transformers",
    )
    # Wan 2.2 I2V/TI2V support is currently on diffusers main.
    .pip_install("git+https://github.com/huggingface/diffusers.git")
    .env(
        {
            "HF_HOME": MODEL_ROOT,
            "HF_HUB_CACHE": MODEL_ROOT,
            "HF_XET_HIGH_PERFORMANCE": "1",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        }
    )
)


def _model_path(model_id: str) -> str:
    return f"{MODEL_ROOT}/{model_id.replace('/', '--')}"


def _download(model_id: str) -> str:
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        model_id,
        local_dir=_model_path(model_id),
    )
    model_volume.commit()
    return path


@app.function(
    image=wan_image,
    volumes={MODEL_ROOT: model_volume},
    timeout=2 * 60 * 60,
)
def download_wan_5b() -> str:
    """Pre-download practical Wan 2.2 5B weights to the persistent Volume."""
    return _download(WAN_5B_ID)


@app.function(
    image=wan_image,
    volumes={MODEL_ROOT: model_volume},
    timeout=2 * 60 * 60,
)
def download_wan_a14b() -> str:
    """Pre-download max-quality Wan 2.2 A14B weights to the Volume."""
    return _download(WAN_A14B_ID)


NEGATIVE_PROMPT = (
    "static image, frozen motion, camera shake, flicker, jitter, text, subtitles, "
    "watermark, logo, people, low quality, blurry details, oversaturated, deformed "
    "geometry, sudden cut, time lapse, fast motion"
)


def _load_pipeline(model_id: str):
    import torch
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline

    path = _model_path(model_id)
    vae = AutoencoderKLWan.from_pretrained(
        path,
        subfolder="vae",
        torch_dtype=torch.float32,
        local_files_only=True,
    )
    pipe = WanImageToVideoPipeline.from_pretrained(
        path,
        vae=vae,
        torch_dtype=torch.bfloat16,
        local_files_only=True,
    )
    pipe.to("cuda")
    return pipe


def _generate_and_finish(
    *,
    pipe,
    image_bytes: bytes,
    music_bytes: bytes,
    prompt: str,
    seed: int,
    width: int,
    height: int,
    frames: int,
    steps: int,
    raw_fps: int,
    seconds: float,
    music_start: float,
    music_db: float,
    slow_factor: float,
) -> bytes:
    import io
    import subprocess
    import tempfile
    from pathlib import Path

    import torch
    from diffusers.utils import export_to_video
    from PIL import Image, ImageOps

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
    generator = torch.Generator(device="cuda").manual_seed(seed)

    output = pipe(
        image=image,
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        height=height,
        width=width,
        num_frames=frames,
        guidance_scale=5.0,
        num_inference_steps=steps,
        generator=generator,
    ).frames[0]

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        raw_video = temp_dir / "wan_raw.mp4"
        music_path = temp_dir / "music_input"
        final_path = temp_dir / "final.mp4"
        export_to_video(output, str(raw_video), fps=raw_fps)
        music_path.write_bytes(music_bytes)

        video_filters = []
        if slow_factor != 1.0:
            video_filters += [
                f"setpts={slow_factor}*PTS",
                "minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc:me_mode=bidir",
            ]
        video_filters += ["scale=1080:1920:flags=lanczos", "format=yuv420p"]
        vf = ",".join(video_filters)
        fade_out = max(0.0, seconds - 0.6)
        audio_filter = (
            f"volume={music_db}dB,"
            "afade=t=in:d=0.4,"
            f"afade=t=out:st={fade_out:.3f}:d=0.6,"
            "loudnorm=I=-14:TP=-1.5:LRA=11"
        )

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(raw_video),
                "-stream_loop",
                "-1",
                "-ss",
                f"{max(0.0, music_start):.3f}",
                "-i",
                str(music_path),
                "-t",
                f"{seconds:.3f}",
                "-vf",
                vf,
                "-af",
                audio_filter,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-profile:v",
                "high",
                "-preset",
                "medium",
                "-crf",
                "19",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(final_path),
            ],
            check=True,
        )

        result = final_path.read_bytes()

    del output
    torch.cuda.empty_cache()
    return result


_PIPE_5B = None


@app.function(
    image=wan_image,
    gpu="H100",
    volumes={MODEL_ROOT: model_volume},
    timeout=60 * 60,
    scaledown_window=5 * 60,
    max_containers=1,
)
def generate_wan_5b(
    image_bytes: bytes,
    music_bytes: bytes,
    prompt: str,
    seed: int,
    seconds: float,
    music_start: float,
    music_db: float,
) -> bytes:
    """Practical profile: Wan 2.2 TI2V-5B, 704x1280, H100."""
    global _PIPE_5B
    if _PIPE_5B is None:
        _PIPE_5B = _load_pipeline(WAN_5B_ID)
    # 121 AI-generated frames. Exporting at 12 fps produces ~10 seconds of
    # slow, atmospheric motion without duplicating a still frame.
    return _generate_and_finish(
        pipe=_PIPE_5B,
        image_bytes=image_bytes,
        music_bytes=music_bytes,
        prompt=prompt,
        seed=seed,
        width=704,
        height=1280,
        frames=121,
        steps=50,
        raw_fps=12,
        seconds=seconds,
        music_start=music_start,
        music_db=music_db,
        slow_factor=1.0,
    )


_PIPE_A14B = None


@app.function(
    image=wan_image,
    gpu="H200",
    volumes={MODEL_ROOT: model_volume},
    timeout=60 * 60,
    scaledown_window=5 * 60,
    max_containers=1,
)
def generate_wan_a14b(
    image_bytes: bytes,
    music_bytes: bytes,
    prompt: str,
    seed: int,
    seconds: float,
    music_start: float,
    music_db: float,
) -> bytes:
    """Max-quality profile: Wan 2.2 I2V-A14B, 720x1280, H200."""
    global _PIPE_A14B
    if _PIPE_A14B is None:
        _PIPE_A14B = _load_pipeline(WAN_A14B_ID)
    # A14B's clean 81-frame window is ~5 seconds at 16 fps. Slow + motion
    # interpolation turns it into a smooth 10-second scenery shot remotely.
    return _generate_and_finish(
        pipe=_PIPE_A14B,
        image_bytes=image_bytes,
        music_bytes=music_bytes,
        prompt=prompt,
        seed=seed,
        width=720,
        height=1280,
        frames=81,
        steps=40,
        raw_fps=16,
        seconds=seconds,
        music_start=music_start,
        music_db=music_db,
        slow_factor=max(1.0, seconds / (81 / 16)),
    )
