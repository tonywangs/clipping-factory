from pathlib import Path

from clipfactory.models import Episode, LicenseStatus
from clipfactory.state.repository import SQLiteState


def test_state_claims_once_and_preserves_feedback(tmp_path: Path):
    state = SQLiteState(tmp_path / "state.sqlite")
    episode = Episode(
        source_id="show",
        external_id="one",
        title="One",
        url="https://example.com",
        license_status=LicenseStatus.CLIPPING_ENCOURAGED,
    )
    state.upsert_episode(episode)
    assert state.episode_seen("show", "one")
    assert state.claim_niche_run("show", "one", "startup")
    state.finish_niche_run("show", "one", "startup", "completed")
    assert not state.claim_niche_run("show", "one", "startup")
    state.add_clip("clip", "show", "one", "startup", "outbox/startup/clip", {})
    state.transition_clip("clip", "rejected", "bad hook")
    assert state.recent_feedback("startup") == ["bad hook"]


def test_failed_niche_remains_pending(tmp_path: Path):
    state = SQLiteState(tmp_path / "state.sqlite")
    assert state.has_pending_niche_work("show", "one", ["startup", "ai"])
    assert state.claim_niche_run("show", "one", "startup")
    state.finish_niche_run("show", "one", "startup", "failed", "boom")
    assert state.claim_niche_run("show", "one", "ai")
    state.finish_niche_run("show", "one", "ai", "completed")
    assert state.has_pending_niche_work("show", "one", ["startup", "ai"])
    assert state.claim_niche_run("show", "one", "startup")
    state.finish_niche_run("show", "one", "startup", "completed")
    assert not state.has_pending_niche_work("show", "one", ["startup", "ai"])


def test_last_run_at(tmp_path: Path):
    state = SQLiteState(tmp_path / "state.sqlite")
    assert state.last_run_at() is None
    state.record_run({"clips": []})
    assert state.last_run_at() is not None
