from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from clipfactory.models import Candidate, CaptionStyle, ClipLength, Episode, LicenseStatus, NicheConfig, Transcript, TranscriptSegment, Word
from clipfactory.render.captions import write_ass
from clipfactory.render.service import _center_crop, _has_video


def _ffmpeg_has_subtitles() -> bool:
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], text=True, capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return " subtitles " in result.stdout


def test_center_crop_builds_vertical_clip(tmp_path: Path):
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=1280x720:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    assert _has_video(source)
    target = tmp_path / "vertical.mp4"
    _center_crop(source, target, 1.5)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(target),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert probe.stdout.strip() == "1080,1920"


@pytest.mark.skipif(not _ffmpeg_has_subtitles(), reason="host ffmpeg missing libass subtitles filter")
def test_ass_file_is_valid_for_burn(tmp_path: Path):
    ass = write_ass(
        [Word(word="HELLO", start=0.2, end=0.8), Word(word="WORLD", start=0.8, end=1.4)],
        0,
        2,
        CaptionStyle.HORMOZI,
        "#FFD400",
        tmp_path / "clip.ass",
    )
    assert "Dialogue" in ass.read_text()
