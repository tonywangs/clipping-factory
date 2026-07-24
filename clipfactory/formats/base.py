"""Shared ffmpeg composition helpers for generated vertical content.

All formats produce 1080x1920 H.264/AAC clips. Helpers here never depend on a
specific format; they cover text cards, Ken Burns slideshows, clip sequencing
with transition SFX, music beds, and loudness normalization.
"""

from __future__ import annotations

import json
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import project_root
from ..ffmpeg_bin import ffmpeg_bin, ffprobe_bin

W, H = 1080, 1920
FPS = 30


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def media_duration(path: Path) -> float:
    result = run(
        [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def font_path() -> Path:
    configured = project_root() / "assets" / "fonts" / "Anton-Regular.ttf"
    if configured.exists():
        return configured
    # Repo-bundled fallback (e.g. when LOCAL_ROOT points at a bare workspace)
    return Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Anton-Regular.ttf"


def _esc_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\\u2019")  # swap straight quote for typographic to avoid quoting hell
        .replace("%", "\\%")
    )


def drawtext_filter(
    text: str,
    *,
    size: int = 88,
    y: str = "h*0.14",
    color: str = "white",
    border: int = 8,
    box: bool = False,
    enable: str | None = None,
) -> str:
    parts = [
        f"drawtext=fontfile='{font_path()}'",
        f"text='{_esc_drawtext(text)}'",
        f"fontsize={size}",
        f"fontcolor={color}",
        "x=(w-text_w)/2",
        f"y={y}",
        f"borderw={border}",
        "bordercolor=black",
    ]
    if box:
        parts += ["box=1", "boxcolor=black@0.55", "boxborderw=22"]
    if enable:
        parts.append(f"enable='{enable}'")
    return ":".join(parts)


def wrap_text(text: str, width: int = 18) -> str:
    """Greedy wrap for drawtext (newline separated)."""
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


@dataclass
class Panel:
    """One visual beat: an image (or None → styled color card) plus overlay text."""

    duration: float
    image: Path | None = None
    label: str | None = None
    sublabel: str | None = None
    bg_color: str = "0x101018"


def render_panel(panel: Panel, target: Path, *, accent: str = "#FFD400") -> Path:
    """Render a single panel to a 1080x1920 video segment with Ken Burns motion."""
    target.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(panel.duration * FPS))
    filters: list[str] = []
    if panel.image is not None:
        source = ["-loop", "1", "-t", f"{panel.duration:.3f}", "-i", str(panel.image)]
        filters.append(
            f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,"
            f"crop={W * 2}:{H * 2},"
            f"zoompan=z='min(zoom+0.0012,1.25)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}"
        )
    else:
        source = ["-f", "lavfi", "-t", f"{panel.duration:.3f}", "-i", f"color=c={panel.bg_color}:s={W}x{H}:r={FPS}"]
        filters.append("null")
    if panel.label:
        filters.append(drawtext_filter(wrap_text(panel.label.upper(), 14), size=104, y="h*0.12"))
    if panel.sublabel:
        filters.append(
            drawtext_filter(wrap_text(panel.sublabel, 26), size=54, y="h*0.80", color=accent.replace("#", "0x"), border=6)
        )
    vf = ",".join(filters) + ",format=yuv420p"
    run(
        [
            ffmpeg_bin(),
            "-y",
            *source,
            "-vf",
            vf,
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-an",
            str(target),
        ]
    )
    return target


def synth_boom_sfx(target: Path, kind: str = "boom") -> Path:
    """Synthesize a loud transition SFX with ffmpeg so zero assets are required."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if kind == "whoosh":
        graph = "anoisesrc=color=brown:d=0.45,afade=t=in:d=0.05,afade=t=out:st=0.2:d=0.25,volume=1.4"
    elif kind == "glitch":
        graph = "sine=f=880:d=0.12,volume=1.2,aecho=0.8:0.8:40:0.5"
    else:  # boom
        graph = "sine=f=52:d=0.5,afade=t=out:st=0.05:d=0.45,volume=2.2"
    run([ffmpeg_bin(), "-y", "-f", "lavfi", "-i", graph, "-c:a", "aac", "-b:a", "192k", str(target)])
    return target


def pick_sfx(work_dir: Path, kind: str = "boom") -> Path:
    """Operator SFX from assets/sfx/transitions/ if present, else synthesized."""
    directory = project_root() / "assets" / "sfx" / "transitions"
    candidates = [p for p in directory.glob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"}] if directory.exists() else []
    if candidates:
        return random.choice(candidates)
    return synth_boom_sfx(work_dir / f"sfx_{kind}.m4a", kind)


def to_vertical_segment(source: Path, target: Path, start: float, duration: float, *, mute: bool = False) -> Path:
    """Cut and center-crop any source clip into a 1080x1920 segment."""
    target.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"crop='if(gte(iw/ih,{W}/{H}),ih*{W}/{H},iw)':'if(gte(iw/ih,{W}/{H}),ih,iw*{H}/{W})':(iw-ow)/2:(ih-oh)/2,"
        f"scale={W}:{H},fps={FPS},format=yuv420p"
    )
    command = [
        ffmpeg_bin(),
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
    ]
    if mute:
        command += ["-an"]
    else:
        command += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]
    command.append(str(target))
    run(command)
    return target


def concat_segments(segments: list[Path], target: Path, *, with_audio: bool) -> Path:
    """Concat same-format segments via the concat demuxer."""
    target.parent.mkdir(parents=True, exist_ok=True)
    listing = target.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in segments))
    command = [ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
    if with_audio:
        command += ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k"]
    else:
        command += ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an"]
    command.append(str(target))
    run(command)
    listing.unlink(missing_ok=True)
    return target


def overlay_text(source: Path, target: Path, text: str, *, size: int = 92, y: str = "h*0.12", accent: str | None = None) -> Path:
    color = accent.replace("#", "0x") if accent else "white"
    run(
        [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(source),
            "-vf",
            drawtext_filter(wrap_text(text.upper(), 16), size=size, y=y, color=color) + ",format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-c:a",
            "copy",
            str(target),
        ]
    )
    return target


def sfx_between(segments: list[Path], sfx: Path, work_dir: Path) -> Path:
    """Concat video segments, dropping an SFX hit at every cut point."""
    video = concat_segments(segments, work_dir / "concat_video.mp4", with_audio=True)
    offsets: list[float] = []
    cursor = 0.0
    for segment in segments[:-1]:
        cursor += media_duration(segment)
        offsets.append(cursor)
    if not offsets:
        return video
    inputs = [ffmpeg_bin(), "-y", "-i", str(video)]
    for _ in offsets:
        inputs += ["-i", str(sfx)]
    delays = ";".join(
        f"[{index + 1}:a]adelay={int(offset * 1000)}|{int(offset * 1000)}[s{index}]" for index, offset in enumerate(offsets)
    )
    tags = "".join(f"[s{index}]" for index in range(len(offsets)))
    graph = f"{delays};[0:a]{tags}amix=inputs={len(offsets) + 1}:duration=first:normalize=0[audio]"
    target = work_dir / "concat_sfx.mp4"
    run(
        inputs
        + [
            "-filter_complex",
            graph,
            "-map",
            "0:v:0",
            "-map",
            "[audio]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(target),
        ]
    )
    return target


def mix_music(
    video: Path,
    music: Path,
    target: Path,
    *,
    music_db: float = -4.0,
    music_start: float = 0.0,
    duck_under_voice: bool = False,
    keep_video_audio: bool = True,
) -> Path:
    """Lay a music bed under (or as) the audio track, with fades and loudnorm."""
    duration = media_duration(video)
    fade_out = max(0.0, duration - 0.8)
    music_chain = f"[1:a]volume={music_db}dB,afade=t=in:d=0.6,afade=t=out:st={fade_out:.3f}:d=0.8[music]"
    if keep_video_audio:
        if duck_under_voice:
            graph = (
                f"{music_chain};[0:a]asplit=2[voice][sc];"
                f"[music][sc]sidechaincompress=threshold=0.03:ratio=10:attack=5:release=300[ducked];"
                f"[voice][ducked]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[audio]"
            )
        else:
            graph = f"{music_chain};[0:a][music]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[audio]"
    else:
        graph = f"{music_chain};[music]loudnorm=I=-14:TP=-1.5:LRA=11[audio]"
    run(
        [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(video),
            "-stream_loop",
            "-1",
            "-ss",
            f"{max(0.0, music_start):.3f}",
            "-i",
            str(music),
            "-filter_complex",
            graph,
            "-map",
            "0:v:0",
            "-map",
            "[audio]",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(target),
        ]
    )
    return target


def finalize(source: Path, target: Path, *, max_seconds: float = 60.0) -> Path:
    """Loudnorm + faststart + duration cap for the final deliverable."""
    duration = min(media_duration(source), max_seconds)
    probe = run(
        [ffprobe_bin(), "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(source)]
    )
    has_audio = "audio" in probe.stdout
    command = [ffmpeg_bin(), "-y", "-i", str(source), "-t", f"{duration:.3f}"]
    if has_audio:
        command += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k"]
    else:
        command += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        command = [ffmpeg_bin(), "-y", "-i", str(source), "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=r=44100:cl=stereo", "-shortest", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}"]
    command += [
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(target),
    ]
    run(command)
    return target


def gather_media(directory: Path, kinds: set[str]) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*") if p.suffix.lower() in kinds and p.is_file())


VIDEO_KINDS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
IMAGE_KINDS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_KINDS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
