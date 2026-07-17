from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from clipfactory.discover.service import discover_sources
from clipfactory.models import Episode, LicenseStatus, SourceConfig, SourceType
from clipfactory.state.repository import SQLiteState


def _episode(external_id: str, source_id: str = "show") -> Episode:
    return Episode(
        source_id=source_id,
        external_id=external_id,
        title=external_id,
        url=f"https://example.com/{external_id}",
        published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        duration_seconds=3600,
        video=True,
        license_status=LicenseStatus.CLIPPING_ENCOURAGED,
    )


def test_once_skips_completed_and_retries_failed(tmp_path: Path):
    state = SQLiteState(tmp_path / "state.sqlite")
    source = SourceConfig(
        id="show",
        type=SourceType.YOUTUBE_CHANNEL,
        url="https://example.com/channel",
        niches=["startup", "ai"],
        license_status=LicenseStatus.CLIPPING_ENCOURAGED,
    )
    listed = [_episode("ep1"), _episode("ep2")]

    with patch("clipfactory.discover.service._youtube", return_value=listed):
        first = discover_sources([source], state, cap=3)
        assert [item.external_id for item in first] == ["ep1", "ep2"]

        state.finish_niche_run("show", "ep1", "startup", "completed")
        state.finish_niche_run("show", "ep1", "ai", "completed")
        state.finish_niche_run("show", "ep2", "startup", "failed", "ingest")
        # ai for ep2 never claimed

        second = discover_sources([source], state, cap=3)
        assert [item.external_id for item in second] == ["ep2"]

        state.finish_niche_run("show", "ep2", "startup", "completed")
        state.finish_niche_run("show", "ep2", "ai", "completed")
        third = discover_sources([source], state, cap=3)
        assert third == []
