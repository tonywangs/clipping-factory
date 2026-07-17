from pathlib import Path

from clipfactory.models import Episode, LicenseStatus
from clipfactory.state.repository import SQLiteState


def test_state_claims_once_and_preserves_feedback(tmp_path: Path):
    state = SQLiteState(tmp_path / "state.sqlite")
    episode = Episode(source_id="show", external_id="one", title="One", url="https://example.com", license_status=LicenseStatus.CLIPPING_ENCOURAGED)
    state.upsert_episode(episode)
    assert state.episode_seen("show", "one")
    assert state.claim_niche_run("show", "one", "startup")
    state.finish_niche_run("show", "one", "startup", "completed")
    assert not state.claim_niche_run("show", "one", "startup")
    state.add_clip("clip", "show", "one", "startup", "outbox/startup/clip", {})
    state.transition_clip("clip", "rejected", "bad hook")
    assert state.recent_feedback("startup") == ["bad hook"]
