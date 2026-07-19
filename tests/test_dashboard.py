from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from clipfactory.config import project_root
from clipfactory.ids import make_clip_id, make_run_id
from clipfactory.models import CaptionStyle, ClipMeta, LicenseStatus


def test_dashboard_defaults_to_latest_run_and_filters(tmp_path: Path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(Path("/workspace/config/settings.yaml").read_text())
    (tmp_path / "config" / "sources.yaml").write_text("sources: []\n")
    niche_dir = tmp_path / "config" / "niches"
    niche_dir.mkdir()
    (niche_dir / "startup.yaml").write_text(Path("/workspace/config/niches/startup.yaml").read_text())

    def write_clip(run_id: str, title: str, start: float):
        meta = ClipMeta(
            clip_id=make_clip_id("show", "ep1", "startup", start, start + 20),
            run_id=run_id,
            niche="startup",
            source_id="show",
            external_id="ep1",
            source_show="show",
            episode_title="Ep",
            episode_url="https://example.com",
            license_status=LicenseStatus.CLIPPING_ENCOURAGED,
            start=start,
            end=start + 20,
            score=88,
            title=title,
            caption="caption",
            hashtags=["#startup"],
            hook_sentence="hook",
            virality_reason="reason",
            caption_style=CaptionStyle.HORMOZI,
            tags=["framing-v2"],
        )
        directory = tmp_path / "outbox" / "startup" / run_id / f"undated_{title}"
        directory.mkdir(parents=True)
        (directory / "meta.json").write_text(meta.model_dump_json())
        (directory / "clip.mp4").write_bytes(b"fake")
        return meta, directory

    old_meta, _ = write_clip("20260101_010101_aaaa", "legacy-title", 10.0)
    new_meta, new_dir = write_clip("20260719_020000_bbbb", "fresh-title", 30.0)

    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    project_root.cache_clear()

    import importlib
    import dashboard.app as dashboard_app

    importlib.reload(dashboard_app)

    client = TestClient(dashboard_app.app)
    home = client.get("/")
    assert home.status_code == 200
    assert "20260719_020000_bbbb" in home.text
    assert "legacy-title" not in home.text  # defaults to latest run
    assert "fresh-title" in home.text

    all_runs = client.get("/?run=all")
    assert "legacy-title" in all_runs.text
    assert "fresh-title" in all_runs.text

    response = client.post(
        f"/clips/{new_meta.clip_id}/rejected",
        content="reason=weak+hook",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert not new_dir.exists()
    assert (tmp_path / "rejected" / "startup" / "20260719_020000_bbbb" / "undated_fresh-title" / "meta.json").exists()


def test_make_run_id_includes_label():
    value = make_run_id("framing-v2")
    assert "framing-v2" in value
