from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from ..models import Candidate, Episode, NicheConfig, Transcript
from .captions import write_ass


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def _has_video(path: Path) -> bool:
    result = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(path)])
    return "video" in result.stdout


def _center_crop(source: Path, target: Path, duration: float) -> None:
    vf = "crop='if(gte(iw/ih,9/16),ih*9/16,iw)':'if(gte(iw/ih,9/16),ih,iw*16/9)':(iw-ow)/2:(ih-oh)/2,scale=1080:1920"
    _run(["ffmpeg", "-y", "-ss", "0", "-i", str(source), "-t", f"{duration:.3f}", "-vf", vf, "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-crf", "20", "-preset", "fast", "-c:a", "aac", "-b:a", "192k", str(target)])


def _audio_visual(source: Path, target: Path, duration: float, accent: str) -> None:
    color = accent.removeprefix("#")
    graph = f"color=c=0x{color}:s=1080x1920:d={duration}[bg];[0:a]showwaves=s=920x350:mode=line:colors=white[wave];[bg][wave]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
    _run(["ffmpeg", "-y", "-i", str(source), "-filter_complex", graph, "-map", "[v]", "-map", "0:a", "-t", f"{duration:.3f}", "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-b:a", "192k", str(target)])


def _reframe(episode: Episode, candidate: Candidate, target: Path, accent: str) -> None:
    duration = candidate.end - candidate.start
    if not episode.local_path:
        raise ValueError("Episode is missing downloaded media")
    if not episode.video or not _has_video(episode.local_path):
        _audio_visual(episode.local_path, target, duration, accent)
        return
    try:
        from engine.local.clipper import crop_clip_local
        crop_clip_local(str(episode.local_path), candidate.start, candidate.end, "9:16", str(target))
        # The engine crop retains source dimensions; normalize after face tracking.
        normalized = target.with_suffix(".normalized.mp4")
        _run(["ffmpeg", "-y", "-i", str(target), "-vf", "scale=1080:1920", "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-b:a", "192k", str(normalized)])
        normalized.replace(target)
    except Exception:
        cut = target.with_suffix(".cut.mp4")
        _run(["ffmpeg", "-y", "-ss", f"{candidate.start:.3f}", "-i", str(episode.local_path), "-t", f"{duration:.3f}", "-c:v", "libx264", "-crf", "20", "-c:a", "aac", str(cut)])
        _center_crop(cut, target, duration)
        cut.unlink(missing_ok=True)


def _loudnorm_measure(source: Path) -> str | None:
    result = subprocess.run(["ffmpeg", "-i", str(source), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], text=True, capture_output=True)
    try:
        payload = result.stderr[result.stderr.rfind("{"):result.stderr.rfind("}") + 1]
        data = json.loads(payload)
        return "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={input_i}:measured_LRA={input_lra}:measured_TP={input_tp}:measured_thresh={input_thresh}:offset={target_offset}:linear=true".format(**data)
    except (ValueError, KeyError):
        return "loudnorm=I=-14:TP=-1.5:LRA=11"


def _music_track(niche: NicheConfig) -> Path | None:
    if not niche.music:
        return None
    directory = Path("assets/music") / niche.name
    tracks = [path for path in directory.glob("*") if path.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"}]
    return random.choice(tracks) if tracks else None


def _burn_and_mix(source: Path, ass: Path, target: Path, niche: NicheConfig, duration: float, music: Path | None) -> None:
    filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], text=True, capture_output=True, check=True).stdout
    if " subtitles " not in filters:
        raise RuntimeError("FFmpeg was built without libass/subtitles support. Install an FFmpeg build with libass or use the supplied Docker image.")
    font_dir = Path("assets/fonts").resolve()
    vf = f"subtitles='{ass.resolve()}':fontsdir='{font_dir}'"
    norm = _loudnorm_measure(source) or "loudnorm=I=-14:TP=-1.5:LRA=11"
    command = ["ffmpeg", "-y", "-i", str(source)]
    if music:
        command += ["-stream_loop", "-1", "-i", str(music)]
        music_base = f"[1:a]volume={niche.music_volume_db}dB,afade=t=in:d=0.5,afade=t=out:st={max(0, duration - .5):.3f}:d=0.5[music]"
        filters = [
            f"{music_base};[0:a][music]sidechaincompress=threshold=0.02:ratio=8[ducked];[ducked][music]amix=inputs=2:duration=first:dropout_transition=0,{norm}[audio]",
            f"{music_base};[0:a][music]amix=inputs=2:duration=first:dropout_transition=0,{norm}[audio]",
        ]
        for index, music_filter in enumerate(filters):
            render_command = command + ["-filter_complex", music_filter, "-vf", vf, "-map", "0:v:0", "-map", "[audio]"]
            render_command += ["-t", f"{min(duration, 60):.3f}", "-c:v", "libx264", "-profile:v", "high", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target)]
            try:
                _run(render_command)
                return
            except subprocess.CalledProcessError:
                target.unlink(missing_ok=True)
                if index == len(filters) - 1:
                    raise
        return
    else:
        command += ["-vf", vf, "-af", norm, "-map", "0:v:0", "-map", "0:a:0?"]
    command += ["-t", f"{min(duration, 60):.3f}", "-c:v", "libx264", "-profile:v", "high", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target)]
    _run(command)


def render_clip(episode: Episode, candidate: Candidate, transcript: Transcript, niche: NicheConfig, work_dir: Path, output: Path) -> str | None:
    work_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    reframed, ass = work_dir / f"{output.stem}.base.mp4", work_dir / f"{output.stem}.ass"
    _reframe(episode, candidate, reframed, niche.accent_color)
    words = [word for segment in transcript.segments for word in segment.words]
    write_ass(words, candidate.start, candidate.end, niche.caption_style, niche.accent_color, ass)
    music = _music_track(niche)
    _burn_and_mix(reframed, ass, output, niche, candidate.end - candidate.start, music)
    return music.name if music else None
