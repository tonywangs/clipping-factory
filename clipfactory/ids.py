"""Shared clip identity helpers so packaging, state, and the dashboard agree."""

from __future__ import annotations

import hashlib


def make_clip_id(source_id: str, external_id: str, niche: str, start: float, end: float) -> str:
    payload = f"{source_id}:{external_id}:{niche}:{start:.3f}:{end:.3f}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
