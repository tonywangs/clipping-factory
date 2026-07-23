"""Format 3 — "which X would you pick" ranked polls.

"Which bedroom would you sleep in the hardest", "which toilet would you poop
in the hardest" — an image slideshow where every option gets a big number +
absurd label, ending on a comment-bait card.

Images per option: operator folder → OpenAI generation → styled color cards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import project_root
from ..llm import LLMUsage, call_llm, extract_json
from .base import (
    AUDIO_KINDS,
    Panel,
    concat_segments,
    finalize,
    gather_media,
    mix_music,
    render_panel,
)
from .images import generate_image, operator_images


@dataclass
class PollOption:
    label: str
    image_prompt: str


@dataclass
class PollPlan:
    topic: str
    intro: str
    options: list[PollOption]
    outro: str
    caption: str
    hashtags: list[str] = field(default_factory=list)


POLL_PROMPT = """You design viral "which one would you pick" TikTok slideshows.
Topic: {topic}
Design {count} wildly different options. Each option needs:
- label: short absurd name shown on screen (e.g. "the void bed", "cloud 9000")
- image_prompt: vivid text-free image description of that option, 9:16
Also write:
- intro: one-line on-screen hook (e.g. "which bedroom are you sleeping in? be honest")
- outro: comment-bait closer (e.g. "wrong answers only in the comments")
- caption + 6-8 hashtags
Return JSON only:
{{"intro": string, "options":[{{"label": string, "image_prompt": string}}],
"outro": string, "caption": string, "hashtags":[string]}}"""


def plan_poll(topic: str, count: int = 6) -> tuple[PollPlan, LLMUsage]:
    raw, usage = call_llm(POLL_PROMPT.format(topic=topic, count=count))
    data = extract_json(raw)
    options = [
        PollOption(label=str(item.get("label", "")).strip(), image_prompt=str(item.get("image_prompt", "")).strip())
        for item in data.get("options", [])
        if item.get("label")
    ]
    if len(options) < 2:
        raise RuntimeError("Poll generation returned fewer than 2 options")
    return (
        PollPlan(
            topic=topic,
            intro=str(data.get("intro", topic)).strip(),
            options=options,
            outro=str(data.get("outro", "comments. now.")).strip(),
            caption=str(data.get("caption", topic)).strip(),
            hashtags=[str(t) for t in data.get("hashtags", [])],
        ),
        usage,
    )


CARD_COLORS = ["0x1b1b2f", "0x16213e", "0x0f3460", "0x533483", "0x2c061f", "0x374045", "0x1a1a2e", "0x321e3e"]


def build_poll_video(
    topic: str,
    work: Path,
    *,
    options: int = 6,
    seconds_per_option: float = 2.6,
    music_mood: str = "suspense",
) -> tuple[Path, PollPlan, LLMUsage]:
    work.mkdir(parents=True, exist_ok=True)
    plan, usage = plan_poll(topic, options)
    pool = operator_images(topic)
    panels: list[Panel] = [Panel(duration=2.2, image=None, label=plan.intro, bg_color="0x0d0d0d")]
    for index, option in enumerate(plan.options):
        image = pool[index % len(pool)] if pool else generate_image(
            option.image_prompt, work / f"option_{index:02d}.png", style_suffix=", vertical 9:16, photorealistic, no text"
        )
        panels.append(
            Panel(
                duration=seconds_per_option,
                image=image,
                label=f"{index + 1}. {option.label}",
                bg_color=CARD_COLORS[index % len(CARD_COLORS)],
            )
        )
    panels.append(Panel(duration=2.4, image=None, label=plan.outro, bg_color="0x0d0d0d"))
    segments = [render_panel(panel, work / f"panel_{index:02d}.mp4") for index, panel in enumerate(panels)]
    assembled = concat_segments(segments, work / "assembled.mp4", with_audio=False)
    music = gather_media(project_root() / "assets" / "music" / "moods" / music_mood, AUDIO_KINDS)
    if music:
        assembled = mix_music(assembled, music[0], work / "with_music.mp4", music_db=-6, keep_video_audio=False)
    final = finalize(assembled, work / "final.mp4", max_seconds=60)
    return final, plan, usage
