"""Shared clip/run identity helpers so packaging, state, and the dashboard agree."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone


def make_clip_id(source_id: str, external_id: str, niche: str, start: float, end: float) -> str:
    payload = f"{source_id}:{external_id}:{niche}:{start:.3f}:{end:.3f}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def make_run_id(label: str | None = None) -> str:
    """Human-sortable run id, e.g. 20260719_021545_a3f2 or with optional label."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(2)
    if label:
        clean = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label.strip())[:24].strip("-_")
        if clean:
            return f"{stamp}_{clean}_{suffix}"
    return f"{stamp}_{suffix}"
