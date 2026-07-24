"""Thin local client for the deployed Modal Wan 2.2 app."""

from __future__ import annotations

from pathlib import Path

APP_NAME = "clipfactory-wan-video"
FUNCTIONS = {
    "wan-5b": "generate_wan_5b",
    "wan-a14b": "generate_wan_a14b",
}


def generate_modal_wan(
    *,
    image: Path,
    music: Path,
    prompt: str,
    target: Path,
    model: str = "wan-5b",
    seed: int = 0,
    seconds: float = 10.0,
    music_start: float = 0.0,
    music_db: float = -2.0,
) -> Path:
    """Generate and fully finish a scenery clip on Modal; write bytes locally."""
    if model not in FUNCTIONS:
        raise ValueError(f"Unknown Modal model {model!r}; use wan-5b or wan-a14b")
    try:
        import modal
    except ImportError as exc:
        raise RuntimeError(
            "Modal client is not installed. Run `make setup` and try again."
        ) from exc

    try:
        function = modal.Function.from_name(APP_NAME, FUNCTIONS[model])
        video_bytes = function.remote(
            image.read_bytes(),
            music.read_bytes(),
            prompt,
            seed,
            seconds,
            music_start,
            music_db,
        )
    except Exception as exc:
        raise RuntimeError(
            "Modal Wan generation failed. Make sure you ran `modal setup`, "
            "`modal run infra/modal_wan_video.py::download_wan_5b` (or "
            "`download_wan_a14b`), and `modal deploy infra/modal_wan_video.py`. "
            f"Original error: {exc}"
        ) from exc

    if not isinstance(video_bytes, bytes) or not video_bytes:
        raise RuntimeError("Modal returned an empty or invalid video payload")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(video_bytes)
    return target
