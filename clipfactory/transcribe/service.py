from __future__ import annotations

import json
from pathlib import Path

from ..models import Transcript, TranscriptSegment, Word


def _srt_time(seconds: float) -> str:
    millis = round(max(seconds, 0) * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def _write_srt(transcript: Transcript, path: Path) -> None:
    lines: list[str] = []
    for index, segment in enumerate(transcript.segments, 1):
        lines += [str(index), f"{_srt_time(segment.start)} --> {_srt_time(segment.end)}", segment.text, ""]
    path.write_text("\n".join(lines))


def transcribe(media_path: Path, cache_dir: Path, model_name: str = "base", device: str = "auto") -> Transcript:
    cache_dir.mkdir(parents=True, exist_ok=True)
    json_path = cache_dir / f"{media_path.stem}.json"
    srt_path = cache_dir / f"{media_path.stem}.srt"
    if json_path.exists() and json_path.stat().st_mtime >= media_path.stat().st_mtime:
        return Transcript.model_validate_json(json_path.read_text())
    from faster_whisper import WhisperModel
    resolved_device = "cuda" if device == "cuda" else "cpu" if device == "cpu" else "cpu"
    compute_type = "float16" if resolved_device == "cuda" else "int8"
    model = WhisperModel(model_name, device=resolved_device, compute_type=compute_type)
    raw_segments, info = model.transcribe(str(media_path), beam_size=5, word_timestamps=True, vad_filter=True, condition_on_previous_text=False)
    segments = []
    for item in raw_segments:
        words = [Word(word=(word.word or "").strip(), start=float(word.start), end=float(word.end)) for word in (item.words or []) if word.word]
        segments.append(TranscriptSegment(start=float(item.start), end=float(item.end), text=(item.text or "").strip(), words=words))
    transcript = Transcript(duration=float(info.duration or (segments[-1].end if segments else 0)), segments=segments)
    json_path.write_text(transcript.model_dump_json(indent=2))
    _write_srt(transcript, srt_path)
    return transcript
