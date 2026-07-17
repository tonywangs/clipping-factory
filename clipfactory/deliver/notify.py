from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def notify_summary(summary: dict[str, Any]) -> None:
    url = os.getenv("NOTIFY_WEBHOOK_URL")
    if not url:
        return
    clips = summary.get("clips", [])
    errors = summary.get("errors", [])
    lines = [f"ClipFactory produced {len(clips)} clip(s)."]
    for item in clips[:5]:
        lines.append(f"• {item.get('title')} ({item.get('score')}/100) — {item.get('path', '')}")
    if errors:
        lines.append(f"{len(errors)} error(s): " + "; ".join(str(err.get("error", err))[:120] for err in errors[:3]))
    if summary.get("cost_estimate_usd") is not None:
        lines.append(f"Est. LLM cost: ${summary['cost_estimate_usd']}")
    text = "\n".join(lines)
    payload = {"text": text, "content": text, "clipfactory": summary}
    try:
        response = httpx.post(url, json=payload, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        # Never fail a successful clip run because Slack/Discord was down.
        logger.warning("notify webhook failed: %s", exc)
