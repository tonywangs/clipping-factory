"""Text-to-speech providers for narrated formats.

Priority: OPENAI_API_KEY → OpenAI TTS; else edge-tts (free, no key); else a
clear actionable error.
"""

from __future__ import annotations

import os
from pathlib import Path


class TTSUnavailableError(RuntimeError):
    pass


def _openai_tts(text: str, target: Path, voice: str) -> Path:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.audio.speech.create(
        model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        voice=voice or "onyx",
        input=text,
        response_format="mp3",
    )
    target.write_bytes(response.read())
    return target


def _edge_tts(text: str, target: Path, voice: str) -> Path:
    import asyncio

    import edge_tts

    async def synth() -> None:
        communicate = edge_tts.Communicate(text, voice or "en-US-ChristopherNeural")
        await communicate.save(str(target))

    asyncio.run(synth())
    return target


def synthesize(text: str, target: Path, *, voice: str = "") -> Path:
    """Write narration audio for `text` to `target` (mp3)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    if os.getenv("OPENAI_API_KEY"):
        try:
            return _openai_tts(text, target, voice)
        except Exception as exc:  # fall through to edge
            errors.append(f"openai tts: {exc}")
    try:
        return _edge_tts(text, target, voice if voice.count("-") >= 2 else "")
    except Exception as exc:
        errors.append(f"edge-tts: {exc}")
    raise TTSUnavailableError(
        "No TTS provider worked. Set OPENAI_API_KEY for OpenAI TTS, or install/allow "
        "edge-tts network access. Errors: " + " | ".join(errors)
    )
