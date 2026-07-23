"""Image sourcing for slideshow formats.

Priority: operator images in assets/images/<slug>/ → OpenAI image generation
(if OPENAI_API_KEY) → styled color cards (never fails).
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

from ..config import project_root
from .base import IMAGE_KINDS, gather_media


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "topic"


def operator_images(topic: str) -> list[Path]:
    return gather_media(project_root() / "assets" / "images" / slugify(topic), IMAGE_KINDS)


def generate_image(prompt: str, target: Path, *, style_suffix: str = "") -> Path | None:
    """Generate one image with OpenAI if configured; None on any failure."""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        result = client.images.generate(
            model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            prompt=f"{prompt}{style_suffix}",
            size="1024x1536",
            n=1,
        )
        payload = result.data[0]
        raw = getattr(payload, "b64_json", None)
        if raw:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(raw))
            return target
        url = getattr(payload, "url", None)
        if url:
            import httpx

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(httpx.get(url, timeout=120).content)
            return target
    except Exception:
        return None
    return None
