from __future__ import annotations

from pathlib import Path

import pysubs2

from ..models import CaptionStyle, Word


def _ass_color(hex_color: str) -> str:
    value = hex_color.removeprefix("#")
    return f"&H00{value[4:6]}{value[2:4]}{value[:2]}&"


def _escape(word: str) -> str:
    return word.replace("{", "\\{").replace("}", "\\}").replace("\\", "\\\\")


def _groups(words: list[Word], size: int = 3) -> list[list[Word]]:
    return [words[index:index + size] for index in range(0, len(words), size)]


def write_ass(words: list[Word], start: float, end: float, style: CaptionStyle, accent: str, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subs = pysubs2.SSAFile()
    subs.info["PlayResX"], subs.info["PlayResY"] = "1080", "1920"
    base = pysubs2.SSAStyle(fontname="Anton", fontsize=110, bold=True, alignment=2, marginv=650, outline=9, shadow=4)
    subs.styles["Caption"] = base
    visible = [word for word in words if word.end >= start and word.start <= end]
    if not visible:
        output.write_text("")
        return output
    accent_ass = _ass_color(accent)
    for group in _groups(visible):
        group_start, group_end = max(start, group[0].start), min(end, group[-1].end)
        if style == CaptionStyle.KARAOKE:
            chunks = []
            for word in group:
                centiseconds = max(1, round((word.end - word.start) * 100))
                chunks.append(f"{{\\k{centiseconds}\\c{accent_ass}}}{_escape(word.word.upper())}")
            subs.events.append(pysubs2.SSAEvent(start=int((group_start - start) * 1000), end=int((group_end - start) * 1000), text=" ".join(chunks), style="Caption"))
            continue
        for index, active in enumerate(group):
            segment_start = max(start, active.start)
            segment_end = min(end, active.end if index == len(group) - 1 else group[index + 1].start)
            text = " ".join(f"{{\\c{accent_ass}}}{_escape(word.word.upper())}{{\\c&HFFFFFF&}}" if word is active else _escape(word.word.upper()) for word in group)
            subs.events.append(pysubs2.SSAEvent(start=int((segment_start - start) * 1000), end=int((segment_end - start) * 1000), text=text, style="Caption"))
    subs.save(str(output), format_="ass")
    return output
