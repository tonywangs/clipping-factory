"""Image sourcing for generated formats.

Priority: operator images in assets/images/<slug>/ → OpenAI/Gemini generation
→ styled color cards in formats that support them.
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


def _generate_openai(prompt: str, target: Path) -> Path | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        result = client.images.generate(
            model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            prompt=prompt,
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


def _generate_gemini(prompt: str, target: Path) -> Path | None:
    if not os.getenv("GEMINI_API_KEY"):
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        response = client.models.generate_content(
            model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
            contents=[prompt],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None)
                if data:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    return target
    except Exception:
        return None
    return None


def generate_image(
    prompt: str,
    target: Path,
    *,
    style_suffix: str = "",
    provider: str = "auto",
) -> Path | None:
    """Generate one image. `auto` tries OpenAI, then Gemini."""
    full_prompt = f"{prompt}{style_suffix}"
    if provider == "openai":
        return _generate_openai(full_prompt, target)
    if provider == "gemini":
        return _generate_gemini(full_prompt, target)
    if provider != "auto":
        raise ValueError("image provider must be auto, openai, or gemini")
    return _generate_openai(full_prompt, target) or _generate_gemini(full_prompt, target)
