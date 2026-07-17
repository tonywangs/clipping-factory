from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from clipfactory.config import project_root
from clipfactory.ids import make_clip_id
from clipfactory.models import CaptionStyle, ClipMeta, LicenseStatus


def test_meta_clip_id_matches_dashboard_helper(tmp_path: Path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(Path("/workspace/config/settings.yaml").read_text())
    (tmp_path / "config" / "sources.yaml").write_text("sources: []\n")
    niche_dir = tmp_path / "config" / "niches"
    niche_dir.mkdir()
    (niche_dir / "startup.yaml").write_text(Path("/workspace/config/niches/startup.yaml").read_text())

    meta = ClipMeta(
        clip_id=make_clip_id("show", "ep1", "startup", 12.5, 40.0),
        niche="startup",
        source_id="show",
        external_id="ep1",
        source_show="show",
        episode_title="Ep",
        episode_url="https://example.com",
        license_status=LicenseStatus.CLIPPING_ENCOURAGED,
        start=12.5,
        end=40.0,
        score=88,
        title="Hook",
        caption="caption",
        hashtags=["#startup"],
        hook_sentence="hook",
        virality_reason="reason",
        caption_style=CaptionStyle.HORMOZI,
    )
    directory = tmp_path / "outbox" / "startup" / "undated_hook"
    directory.mkdir(parents=True)
    (directory / "meta.json").write_text(meta.model_dump_json())
    (directory / "clip.mp4").write_bytes(b"fake")

    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    project_root.cache_clear()

    import importlib
    import dashboard.app as dashboard_app

    importlib.reload(dashboard_app)

    clips = dashboard_app._clips()
    assert len(clips) == 1
    assert clips[0]["clip_id"] == meta.clip_id

    client = TestClient(dashboard_app.app)
    response = client.post(
        f"/clips/{meta.clip_id}/rejected",
        content="reason=weak+hook",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert not directory.exists()
    assert (tmp_path / "rejected" / "startup" / "undated_hook" / "meta.json").exists()
    feedback = (tmp_path / "feedback" / "startup.jsonl").read_text()
    assert "weak hook" in feedback
