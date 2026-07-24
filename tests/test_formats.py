"""Offline tests for the viral-format composition suite (no LLM/TTS network)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from clipfactory.ffmpeg_bin import ffmpeg_bin, ffprobe_bin
from clipfactory.formats.base import (
    Panel,
    concat_segments,
    media_duration,
    render_panel,
    sfx_between,
    synth_boom_sfx,
    to_vertical_segment,
    wrap_text,
)
from clipfactory.formats.fancam import FancamPlan, build_fancam_video, parse_moments


def _probe_dims(path: Path) -> str:
    result = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _synthetic_source(path: Path, seconds: float = 12.0) -> Path:
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=1280x720:rate=30:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def test_wrap_text():
    assert wrap_text("one two three four five", 9) == "one two\nthree\nfour five"


def test_parse_moments():
    assert parse_moments("12.5-16, 42-45.5") == [(12.5, 16.0), (42.0, 45.5)]
    assert parse_moments("5-3") == []


def test_render_panel_color_card_is_vertical(tmp_path: Path):
    panel = Panel(duration=1.0, image=None, label="THE VOID BED", sublabel="option 1")
    target = render_panel(panel, tmp_path / "panel.mp4")
    assert _probe_dims(target) == "1080,1920"
    assert 0.8 <= media_duration(target) <= 1.4


def test_vertical_segment_and_concat(tmp_path: Path):
    source = _synthetic_source(tmp_path / "src.mp4", 6.0)
    seg1 = to_vertical_segment(source, tmp_path / "a.mp4", 0.5, 2.0)
    seg2 = to_vertical_segment(source, tmp_path / "b.mp4", 3.0, 2.0)
    joined = concat_segments([seg1, seg2], tmp_path / "joined.mp4", with_audio=True)
    assert _probe_dims(joined) == "1080,1920"
    assert 3.5 <= media_duration(joined) <= 4.6


def test_sfx_between_adds_audio(tmp_path: Path):
    source = _synthetic_source(tmp_path / "src.mp4", 8.0)
    segments = [
        to_vertical_segment(source, tmp_path / f"s{i}.mp4", i * 2.0, 1.5) for i in range(3)
    ]
    sfx = synth_boom_sfx(tmp_path / "boom.m4a")
    joined = sfx_between(segments, sfx, tmp_path)
    assert joined.exists()
    assert 4.0 <= media_duration(joined) <= 5.2


def test_fancam_end_to_end_with_manual_moments(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    source = _synthetic_source(tmp_path / "episode.mp4", 15.0)
    plan = FancamPlan(
        overlay="maddie attitude",
        caption="the attitude era",
        hashtags=["#edit"],
        moments=parse_moments("1-3,5-7.5,10-12"),
    )
    final = build_fancam_video(source, plan, tmp_path / "work")
    assert _probe_dims(final) == "1080,1920"
    assert 6.0 <= media_duration(final) <= 8.5


def test_poll_build_with_mocked_plan(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    from clipfactory.formats import ranked_poll
    from clipfactory.llm import LLMUsage

    fake = ranked_poll.PollPlan(
        topic="which bedroom",
        intro="which bedroom are you sleeping in?",
        options=[
            ranked_poll.PollOption(label="the void bed", image_prompt="x"),
            ranked_poll.PollOption(label="cloud 9000", image_prompt="y"),
            ranked_poll.PollOption(label="lava loft", image_prompt="z"),
        ],
        outro="wrong answers only",
        caption="be honest",
        hashtags=["#poll"],
    )
    monkeypatch.setattr(ranked_poll, "plan_poll", lambda topic, count=6: (fake, LLMUsage()))
    final, plan, usage = ranked_poll.build_poll_video("which bedroom", tmp_path / "work", options=3, seconds_per_option=1.0)
    assert plan.intro.startswith("which bedroom")
    assert _probe_dims(final) == "1080,1920"
    assert 6.0 <= media_duration(final) <= 9.0


def test_asmr_and_montage_require_assets(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    from clipfactory.formats.asmr import build_asmr_video
    from clipfactory.formats.mood_montage import build_montage_video

    with pytest.raises(FileNotFoundError):
        build_asmr_video("glass-fruit", tmp_path / "work1")
    with pytest.raises(FileNotFoundError):
        build_montage_video("nyc-rain", tmp_path / "work2")


def test_montage_with_synthetic_broll(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    broll = tmp_path / "assets" / "broll" / "nyc-rain"
    broll.mkdir(parents=True)
    _synthetic_source(broll / "rain1.mp4", 8.0)
    _synthetic_source(broll / "rain2.mp4", 8.0)

    from clipfactory.formats import mood_montage
    from clipfactory.llm import LLMUsage

    fake = mood_montage.MontagePlan(overlay="nyc rain hits different", caption="cap", hashtags=["#rain"])
    monkeypatch.setattr(mood_montage, "plan_montage", lambda c, m: (fake, LLMUsage()))
    final, plan, usage = mood_montage.build_montage_video("nyc-rain", tmp_path / "work", target_seconds=6.0, min_cut=2.0, max_cut=3.0)
    assert _probe_dims(final) == "1080,1920"
    assert plan.overlay == "nyc rain hits different"


def test_history_script_parsing(monkeypatch):
    from clipfactory.formats import history_pov
    from clipfactory.llm import LLMUsage

    payload = {
        "hook": "You wake up in 1848 and you are already late for the mill.",
        "scenes": [
            {"narration": "It is 4am.", "image_prompt": "dark bedroom", "label": "4AM"},
            {"narration": "Breakfast is bread.", "image_prompt": "stale bread", "label": "BREAKFAST"},
        ],
        "caption": "could you survive this?",
        "hashtags": ["#history"],
    }
    monkeypatch.setattr(history_pov, "call_llm", lambda prompt: (json.dumps(payload), LLMUsage(input_tokens=5, output_tokens=7)))
    script, usage = history_pov.write_script("day in the life of a victorian child")
    assert len(script.scenes) == 2
    assert script.hook.startswith("You wake up")
    assert usage.output_tokens == 7


def test_generated_packaging(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    from clipfactory.formats.packaging import package_generated
    from clipfactory.models import LicenseStatus

    video = _synthetic_source(tmp_path / "final.mp4", 3.0)
    package = package_generated(
        video,
        format_name="poll",
        niche="poll",
        run_id="20260723_010000_test",
        title="which bedroom",
        caption="be honest",
        hashtags=["#poll"],
        hook_sentence="which bedroom?",
        reason="test",
        score=75,
        license_status=LicenseStatus.ORIGINAL,
        tags=["v1"],
    )
    meta = json.loads((package.directory / "meta.json").read_text())
    assert meta["run_id"] == "20260723_010000_test"
    assert meta["license_status"] == "original"
    assert "poll" in meta["tags"]
    assert (package.directory / "clip.mp4").exists()
    assert (package.directory / "cover.jpg").exists()


def test_scenery_promo_from_existing_image(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    # A supplied image avoids all external image APIs in this render test.
    image = tmp_path / "aurora.png"
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x17335c:s=1024x1536",
            "-frames:v",
            "1",
            str(image),
        ],
        check=True,
        capture_output=True,
    )
    music = tmp_path / "promo.m4a"
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=8",
            "-c:a",
            "aac",
            str(music),
        ],
        check=True,
        capture_output=True,
    )
    (tmp_path / "ATTRIBUTION.txt").write_text(
        '"Test Track" Test Artist — CC BY 4.0 https://creativecommons.org/licenses/by/4.0/'
    )

    from clipfactory.formats import scenery_promo
    from clipfactory.llm import LLMUsage

    fake = scenery_promo.SceneryPlan(
        title="aurora after midnight",
        image_prompt="aurora over a frozen beach",
        caption="somewhere quiet",
        hashtags=["#aurora", "#scenery"],
    )
    monkeypatch.setattr(
        scenery_promo,
        "plan_scenery",
        lambda concept, campaign="", artist="": (fake, LLMUsage(3, 4)),
    )
    final, plan, usage, track, visual_source = scenery_promo.build_scenery_promo(
        "aurora over a black-sand beach",
        tmp_path / "work",
        music=music,
        campaign="test-campaign",
        source=image,
        seconds=4.0,
        music_start=1.0,
        video_provider="image",
    )
    assert _probe_dims(final) == "1080,1920"
    assert 3.7 <= media_duration(final) <= 4.2
    assert track == music.resolve()
    assert visual_source == str(image.resolve())
    assert plan.title == "aurora after midnight"
    assert "CC BY 4.0" in plan.caption
    assert usage.output_tokens == 4


def test_scenery_music_campaign_folder(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    campaign = tmp_path / "assets" / "music" / "promotions" / "artist-july"
    campaign.mkdir(parents=True)
    track = campaign / "hook.wav"
    track.write_bytes(b"placeholder")
    from clipfactory.formats.scenery_promo import resolve_promo_music

    assert resolve_promo_music(None, "artist-july") == track.resolve()


def test_scenery_modal_provider_delegates_all_rendering(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    image = tmp_path / "keyframe.png"
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x17335c:s=704x1280",
            "-frames:v",
            "1",
            str(image),
        ],
        check=True,
        capture_output=True,
    )
    music = tmp_path / "track.m4a"
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=8",
            "-c:a",
            "aac",
            str(music),
        ],
        check=True,
        capture_output=True,
    )

    from clipfactory.formats import scenery_promo
    from clipfactory.llm import LLMUsage
    import clipfactory.modal_video as modal_video

    fake_plan = scenery_promo.SceneryPlan(
        title="moving waterfall",
        image_prompt="waterfall in a moss forest",
        video_prompt="water flows, fog drifts, leaves sway, slow camera push",
        caption="somewhere quiet",
        hashtags=["#scenery"],
    )
    monkeypatch.setattr(
        scenery_promo,
        "plan_scenery",
        lambda concept, campaign="", artist="": (fake_plan, LLMUsage()),
    )
    received = {}

    def fake_modal(**kwargs):
        received.update(kwargs)
        return _synthetic_source(kwargs["target"], 4.0)

    monkeypatch.setattr(modal_video, "generate_modal_wan", fake_modal)
    final, plan, usage, track, source = scenery_promo.build_scenery_promo(
        "moving waterfall",
        tmp_path / "work",
        music=music,
        source=image,
        seconds=4.0,
        video_provider="modal-wan",
        modal_model="wan-a14b",
        seed=42,
    )
    assert final.exists()
    assert received["model"] == "wan-a14b"
    assert received["seed"] == 42
    assert "fog drifts" in received["prompt"]
    assert received["music"] == music.resolve()


def test_generated_clip_ids_are_distinct_per_run(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    from clipfactory.formats.packaging import package_generated
    from clipfactory.models import LicenseStatus

    first_video = _synthetic_source(tmp_path / "first.mp4", 2.0)
    second_video = _synthetic_source(tmp_path / "second.mp4", 2.0)
    common = dict(
        format_name="scenery",
        niche="scenery",
        title="same concept",
        caption="caption",
        hashtags=["#scenery"],
        hook_sentence="hook",
        reason="promo",
        score=75,
        license_status=LicenseStatus.CAMPAIGN_LICENSED,
        tags=[],
    )
    first = package_generated(first_video, run_id="run-one", **common)
    second = package_generated(second_video, run_id="run-two", **common)
    assert first.clip_id != second.clip_id
