from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from clipfactory.deliver.notify import notify_summary
from clipfactory.discover.service import _iso8601_duration
from clipfactory.state.repository import SQLiteState


def test_iso8601_duration():
    assert _iso8601_duration("PT1H2M3S") == 3723
    assert _iso8601_duration("PT45S") == 45
    assert _iso8601_duration("bad") is None


def test_notify_does_not_raise_on_webhook_failure(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://example.invalid/hook")

    def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    with patch("clipfactory.deliver.notify.httpx.post", side_effect=boom):
        notify_summary({"clips": [{"title": "x", "score": 90, "path": "outbox/x"}], "errors": [], "cost_estimate_usd": 0.01})


def test_feedback_jsonl_supplements_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_ROOT", str(tmp_path))
    from clipfactory.config import project_root

    project_root.cache_clear()
    feedback = tmp_path / "feedback"
    feedback.mkdir()
    (feedback / "startup.jsonl").write_text('{"clip_id":"a","reason":"weak hook"}\n{"clip_id":"b","reason":"too long"}\n')
    state = SQLiteState(tmp_path / "state.sqlite")
    assert state.recent_feedback("startup") == ["too long", "weak hook"]
