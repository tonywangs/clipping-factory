"""Format 1 — AI history POV: "day in the life of a Victorian child" etc.

LLM writes a hooky first-person script split into scenes → TTS narrates →
each scene gets an image (operator folder → OpenAI images → styled card) →
Ken Burns slideshow synced to narration, big captions, optional music bed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..llm import LLMUsage, call_llm, extract_json
from .base import (
    AUDIO_KINDS,
    Panel,
    concat_segments,
    drawtext_filter,
    finalize,
    gather_media,
    media_duration,
    mix_music,
    render_panel,
    run,
    wrap_text,
)
from ..config import project_root
from ..ffmpeg_bin import ffmpeg_bin
from ..progress import Progress
from .images import generate_image, operator_images, slugify
from .tts import synthesize


@dataclass
class Scene:
    narration: str
    image_prompt: str
    label: str


@dataclass
class HistoryScript:
    topic: str
    hook: str
    scenes: list[Scene]
    caption: str
    hashtags: list[str] = field(default_factory=list)


SCRIPT_PROMPT = """You write viral TikTok "POV day in the life" history scripts.
Topic: {topic}
Write a first-person script for a ~45 second narrated video.
Rules:
- Open with a 1-sentence HOOK that creates instant curiosity (mention the year).
- 6 to 8 short scenes, each 1-2 spoken sentences, chronological through one day.
- Brutal, specific, surprising historical details beat generic ones.
- Present tense, first person. No modern slang in narration.
- Each scene gets: narration, an image_prompt (vivid, cinematic, historically accurate,
  no text in image), and a 2-4 word on-screen label (e.g. "5AM: CHIMNEY SHIFT").
Return JSON only:
{{"hook": string, "scenes":[{{"narration": string, "image_prompt": string, "label": string}}],
"caption": string (TikTok caption with a question to drive comments), "hashtags":[string]}}"""


def write_script(topic: str) -> tuple[HistoryScript, LLMUsage]:
    raw, usage = call_llm(SCRIPT_PROMPT.format(topic=topic))
    data = extract_json(raw)
    scenes = [
        Scene(
            narration=str(item.get("narration", "")).strip(),
            image_prompt=str(item.get("image_prompt", "")).strip(),
            label=str(item.get("label", "")).strip(),
        )
        for item in data.get("scenes", [])
        if item.get("narration")
    ]
    if not scenes:
        raise RuntimeError("History script generation returned no scenes")
    return (
        HistoryScript(
            topic=topic,
            hook=str(data.get("hook", "")).strip(),
            scenes=scenes,
            caption=str(data.get("caption", "")).strip(),
            hashtags=[str(t) for t in data.get("hashtags", [])],
        ),
        usage,
    )


def _scene_image(scene: Scene, index: int, pool: list[Path], work: Path) -> Path | None:
    if pool:
        return pool[index % len(pool)]
    generated = generate_image(
        scene.image_prompt,
        work / f"scene_{index:02d}.png",
        style_suffix=", cinematic lighting, photorealistic, vertical 9:16 composition",
    )
    return generated  # None → styled color card fallback in render_panel


def _burn_scene_caption(segment: Path, target: Path, text: str) -> Path:
    vf = drawtext_filter(wrap_text(text, 24), size=60, y="h*0.62", color="white", border=7) + ",format=yuv420p"
    run([ffmpeg_bin(), "-y", "-i", str(segment), "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "copy", str(target)])
    return target


def build_history_video(topic: str, work: Path, *, music_mood: str = "cinematic", voice: str = "") -> tuple[Path, HistoryScript, LLMUsage]:
    progress = Progress("history")
    work.mkdir(parents=True, exist_ok=True)
    progress.emit("Writing script with the configured LLM…")
    script, usage = write_script(topic)
    progress.emit(f"Script ready: {len(script.scenes)} scenes")
    (work / "script.json").write_text(
        json.dumps(
            {
                "topic": topic,
                "hook": script.hook,
                "scenes": [scene.__dict__ for scene in script.scenes],
                "caption": script.caption,
                "hashtags": script.hashtags,
            },
            indent=2,
        )
    )
    pool = operator_images(topic)
    if pool:
        progress.emit(f"Using {len(pool)} operator image(s) from assets/images/")
    else:
        progress.emit("No operator images found; trying AI images, then styled cards")
    segments: list[Path] = []
    narrations: list[Path] = []
    lines = [script.hook, *[scene.narration for scene in script.scenes]]
    labels = ["", *[scene.label for scene in script.scenes]]
    for index, line in enumerate(lines):
        progress.step(index + 1, len(lines), "Generating narration")
        audio = synthesize(line, work / f"narration_{index:02d}.mp3", voice=voice)
        narrations.append(audio)
        duration = max(2.2, media_duration(audio) + 0.35)
        progress.step(index + 1, len(lines), "Sourcing scene image")
        if index == 0:
            image = _scene_image(script.scenes[0], 0, pool, work)
            panel = Panel(duration=duration, image=image, label=None)
        else:
            scene = script.scenes[index - 1]
            image = _scene_image(scene, index - 1, pool, work)
            panel = Panel(duration=duration, image=image, label=scene.label or None)
        image_source = "image" if image else "styled card"
        progress.step(index + 1, len(lines), f"Rendering scene ({duration:.1f}s, {image_source})")
        silent = render_panel(panel, work / f"panel_{index:02d}.mp4")
        captioned = _burn_scene_caption(silent, work / f"panelcap_{index:02d}.mp4", line)
        with_voice = work / f"scene_{index:02d}.mp4"
        run(
            [
                ffmpeg_bin(),
                "-y",
                "-i",
                str(captioned),
                "-i",
                str(audio),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-shortest",
                str(with_voice),
            ]
        )
        segments.append(with_voice)
    progress.emit("Combining rendered scenes…")
    assembled = concat_segments(segments, work / "assembled.mp4", with_audio=True)
    music = gather_media(project_root() / "assets" / "music" / "moods" / music_mood, AUDIO_KINDS)
    if music:
        progress.emit(f"Mixing {music_mood} music bed under narration…")
        assembled = mix_music(assembled, music[0], work / "with_music.mp4", music_db=-20, duck_under_voice=True)
    else:
        progress.emit(f"No {music_mood} music found; continuing without music")
    progress.emit("Finalizing video (loudness, codec, faststart)…")
    final = finalize(assembled, work / "final.mp4", max_seconds=90)
    progress.done("History video ready")
    return final, script, usage
