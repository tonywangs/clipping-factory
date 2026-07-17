"""Opt-in golden-path smoke.

Set CLIPFACTORY_E2E=1 and provide ANTHROPIC_API_KEY (or another configured
provider) plus network access to exercise a short CC media URL end-to-end.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.e2e
@pytest.mark.skipif(os.getenv("CLIPFACTORY_E2E") != "1", reason="set CLIPFACTORY_E2E=1 to run")
def test_golden_path_local_media(tmp_path: Path, monkeypatch):
    import subprocess

    media = tmp_path / "talk.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=1280x720:d=35",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=35",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(media),
        ],
        check=True,
        capture_output=True,
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    # Copy niche config into the temp project root.
    niche_dir = tmp_path / "config" / "niches"
    niche_dir.mkdir(parents=True)
    (tmp_path / "config" / "settings.yaml").write_text(
        Path("/workspace/config/settings.yaml").read_text()
    )
    (niche_dir / "startup.yaml").write_text(Path("/workspace/config/niches/startup.yaml").read_text())
    (tmp_path / "config" / "sources.yaml").write_text("sources: []\n")
    fonts = tmp_path / "assets" / "fonts"
    fonts.mkdir(parents=True)
    for name in ("Anton-Regular.ttf", "OFL.txt"):
        src = Path("/workspace/assets/fonts") / name
        if src.exists():
            (fonts / name).write_bytes(src.read_bytes())

    from clipfactory.rank.service import Candidate, RankResult, TokenUsage
    from unittest.mock import patch

    fake = RankResult(
        candidates=[
            Candidate(
                start=5,
                end=30,
                score=90,
                title="Synthetic hook",
                hook_sentence="Listen to this",
                virality_reason="clear punchline",
                suggested_caption="Synthetic clip",
                hashtags=["#startup"],
            )
        ],
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )

    with patch("clipfactory.run.rank_candidates", return_value=fake):
        with patch("clipfactory.run.transcribe") as transcribe:
            from clipfactory.models import Transcript, TranscriptSegment, Word

            words = [Word(word=w, start=float(i), end=float(i) + 0.8) for i, w in enumerate("this is a synthetic spoken line for captions".split(), start=5)]
            transcribe.return_value = Transcript(
                duration=35,
                segments=[TranscriptSegment(start=5, end=30, text=" ".join(w.word for w in words), words=words)],
            )
            from clipfactory.run import main

            if not _has_subtitles():
                pytest.skip("ffmpeg missing subtitles filter")
            main(["--episode", str(media), "--niche", "startup"])
    outbox = list((tmp_path / "outbox" / "startup").glob("*/meta.json"))
    assert outbox


def _has_subtitles() -> bool:
    import subprocess

    result = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], text=True, capture_output=True)
    return " subtitles " in result.stdout
