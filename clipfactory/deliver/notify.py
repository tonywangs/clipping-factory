from __future__ import annotations

import os
from typing import Any

import httpx


def notify_summary(summary: dict[str, Any]) -> None:
    url = os.getenv("NOTIFY_WEBHOOK_URL")
    if not url:
        return
    clips = summary.get("clips", [])
    text = f"ClipFactory: {len(clips)} clip(s) produced. " + "; ".join(f"{item['title']} ({item['score']})" for item in clips[:5])
    response = httpx.post(url, json={"text": text, "content": text, "clipfactory": summary}, timeout=15)
    response.raise_for_status()
