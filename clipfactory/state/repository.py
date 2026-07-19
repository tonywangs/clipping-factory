from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import project_root
from ..models import Episode

TERMINAL_SUCCESS = {"completed"}
BLOCKING_STATUSES = {"running", "completed"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _feedback_jsonl(niche: str, limit: int, exclude: set[str] | None = None) -> list[str]:
    path = project_root() / "feedback" / f"{niche}.jsonl"
    if not path.exists() or limit <= 0:
        return []
    exclude = exclude or set()
    reasons: list[str] = []
    for line in reversed(path.read_text().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        reason = str(payload.get("reason") or "").strip()
        if reason and reason not in exclude and reason not in reasons:
            reasons.append(reason)
        if len(reasons) >= limit:
            break
    return reasons


class StateRepository(ABC):
    @abstractmethod
    def episode_seen(self, source_id: str, external_id: str) -> bool: ...

    @abstractmethod
    def upsert_episode(self, episode: Episode) -> None: ...

    @abstractmethod
    def get_episode(self, source_id: str, external_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def claim_niche_run(self, source_id: str, external_id: str, niche: str) -> bool: ...

    @abstractmethod
    def reset_niche_run(self, source_id: str, external_id: str, niche: str) -> None: ...

    @abstractmethod
    def finish_niche_run(self, source_id: str, external_id: str, niche: str, status: str, error: str | None = None) -> None: ...

    @abstractmethod
    def niche_run_status(self, source_id: str, external_id: str, niche: str) -> str | None: ...

    @abstractmethod
    def has_pending_niche_work(self, source_id: str, external_id: str, niches: list[str]) -> bool: ...

    @abstractmethod
    def add_clip(self, clip_id: str, source_id: str, external_id: str, niche: str, path: str, meta: dict[str, Any]) -> None: ...

    @abstractmethod
    def transition_clip(self, clip_id: str, status: str, rejection_reason: str | None = None) -> None: ...

    @abstractmethod
    def recent_feedback(self, niche: str, limit: int = 20) -> list[str]: ...

    @abstractmethod
    def record_run(self, summary: dict[str, Any]) -> None: ...

    @abstractmethod
    def last_run_at(self) -> datetime | None: ...


class SQLiteState(StateRepository):
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or project_root() / "data" / "clipfactory.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS episodes (
          source_id TEXT NOT NULL, external_id TEXT NOT NULL, payload TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          PRIMARY KEY (source_id, external_id)
        );
        CREATE TABLE IF NOT EXISTS niche_runs (
          source_id TEXT NOT NULL, external_id TEXT NOT NULL, niche TEXT NOT NULL,
          status TEXT NOT NULL, error TEXT, updated_at TEXT NOT NULL,
          PRIMARY KEY (source_id, external_id, niche)
        );
        CREATE TABLE IF NOT EXISTS clips (
          clip_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, external_id TEXT NOT NULL,
          niche TEXT NOT NULL, status TEXT NOT NULL, path TEXT NOT NULL, meta TEXT NOT NULL,
          rejection_reason TEXT, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, summary TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
        self.conn.commit()

    def episode_seen(self, source_id: str, external_id: str) -> bool:
        return self.get_episode(source_id, external_id) is not None

    def upsert_episode(self, episode: Episode) -> None:
        payload = episode.model_dump(mode="json")
        self.conn.execute("""INSERT INTO episodes VALUES (?, ?, ?, ?, ?)
          ON CONFLICT(source_id, external_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
          (episode.source_id, episode.external_id, json.dumps(payload), now(), now()))
        self.conn.commit()

    def get_episode(self, source_id: str, external_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT payload FROM episodes WHERE source_id=? AND external_id=?", (source_id, external_id)).fetchone()
        return json.loads(row["payload"]) if row else None

    def claim_niche_run(self, source_id: str, external_id: str, niche: str) -> bool:
        row = self.conn.execute("SELECT status FROM niche_runs WHERE source_id=? AND external_id=? AND niche=?", (source_id, external_id, niche)).fetchone()
        if row and row["status"] in BLOCKING_STATUSES:
            return False
        self.conn.execute("""INSERT INTO niche_runs VALUES (?, ?, ?, 'running', NULL, ?)
          ON CONFLICT(source_id, external_id, niche) DO UPDATE SET status='running', error=NULL, updated_at=excluded.updated_at""",
          (source_id, external_id, niche, now()))
        self.conn.commit()
        return True

    def reset_niche_run(self, source_id: str, external_id: str, niche: str) -> None:
        self.conn.execute(
            "DELETE FROM niche_runs WHERE source_id=? AND external_id=? AND niche=?",
            (source_id, external_id, niche),
        )
        self.conn.commit()

    def finish_niche_run(self, source_id: str, external_id: str, niche: str, status: str, error: str | None = None) -> None:
        self.conn.execute(
            """INSERT INTO niche_runs VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_id, external_id, niche) DO UPDATE SET status=excluded.status, error=excluded.error, updated_at=excluded.updated_at""",
            (source_id, external_id, niche, status, error, now()),
        )
        self.conn.commit()

    def niche_run_status(self, source_id: str, external_id: str, niche: str) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM niche_runs WHERE source_id=? AND external_id=? AND niche=?",
            (source_id, external_id, niche),
        ).fetchone()
        return str(row["status"]) if row else None

    def has_pending_niche_work(self, source_id: str, external_id: str, niches: list[str]) -> bool:
        return any(self.niche_run_status(source_id, external_id, niche) not in TERMINAL_SUCCESS for niche in niches)

    def add_clip(self, clip_id: str, source_id: str, external_id: str, niche: str, path: str, meta: dict[str, Any]) -> None:
        self.conn.execute("""INSERT INTO clips VALUES (?, ?, ?, ?, 'outbox', ?, ?, NULL, ?)
          ON CONFLICT(clip_id) DO UPDATE SET path=excluded.path, meta=excluded.meta, updated_at=excluded.updated_at""",
          (clip_id, source_id, external_id, niche, path, json.dumps(meta), now()))
        self.conn.commit()

    def transition_clip(self, clip_id: str, status: str, rejection_reason: str | None = None) -> None:
        self.conn.execute(
            "UPDATE clips SET status=?, rejection_reason=?, updated_at=? WHERE clip_id=?",
            (status, rejection_reason, now(), clip_id),
        )
        self.conn.commit()

    def recent_feedback(self, niche: str, limit: int = 20) -> list[str]:
        rows = self.conn.execute(
            "SELECT rejection_reason FROM clips WHERE niche=? AND rejection_reason IS NOT NULL ORDER BY updated_at DESC LIMIT ?",
            (niche, limit),
        ).fetchall()
        reasons = [row["rejection_reason"] for row in rows]
        if len(reasons) >= limit:
            return reasons[:limit]
        reasons.extend(_feedback_jsonl(niche, limit - len(reasons), exclude=set(reasons)))
        return reasons[:limit]

    def record_run(self, summary: dict[str, Any]) -> None:
        self.conn.execute("INSERT INTO runs(summary, created_at) VALUES (?, ?)", (json.dumps(summary), now()))
        self.conn.commit()

    def last_run_at(self) -> datetime | None:
        row = self.conn.execute("SELECT created_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        return datetime.fromisoformat(row["created_at"])


class FirestoreState(StateRepository):
    """Cloud implementation with the same idempotency keys as SQLite."""
    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore
        self.client = firestore.Client(project=project)

    def _episode_ref(self, source_id: str, external_id: str):
        return self.client.collection("episodes").document(f"{source_id}:{external_id}")

    def episode_seen(self, source_id: str, external_id: str) -> bool:
        return self._episode_ref(source_id, external_id).get().exists

    def upsert_episode(self, episode: Episode) -> None:
        self._episode_ref(episode.source_id, episode.external_id).set(episode.model_dump(mode="json") | {"updated_at": now()}, merge=True)

    def get_episode(self, source_id: str, external_id: str) -> dict[str, Any] | None:
        snap = self._episode_ref(source_id, external_id).get()
        return snap.to_dict() if snap.exists else None

    def claim_niche_run(self, source_id: str, external_id: str, niche: str) -> bool:
        from google.cloud.firestore import transactional
        ref = self.client.collection("niche_runs").document(f"{source_id}:{external_id}:{niche}")
        transaction = self.client.transaction()
        @transactional(transaction)
        def claim(tx):
            existing = ref.get(transaction=tx)
            if existing.exists and existing.to_dict().get("status") in BLOCKING_STATUSES:
                return False
            tx.set(ref, {"status": "running", "updated_at": now()}, merge=True)
            return True
        return claim(transaction)

    def reset_niche_run(self, source_id: str, external_id: str, niche: str) -> None:
        self.client.collection("niche_runs").document(f"{source_id}:{external_id}:{niche}").delete()

    def finish_niche_run(self, source_id: str, external_id: str, niche: str, status: str, error: str | None = None) -> None:
        self.client.collection("niche_runs").document(f"{source_id}:{external_id}:{niche}").set({"status": status, "error": error, "updated_at": now()}, merge=True)

    def niche_run_status(self, source_id: str, external_id: str, niche: str) -> str | None:
        snap = self.client.collection("niche_runs").document(f"{source_id}:{external_id}:{niche}").get()
        if not snap.exists:
            return None
        return snap.to_dict().get("status")

    def has_pending_niche_work(self, source_id: str, external_id: str, niches: list[str]) -> bool:
        return any(self.niche_run_status(source_id, external_id, niche) not in TERMINAL_SUCCESS for niche in niches)

    def add_clip(self, clip_id: str, source_id: str, external_id: str, niche: str, path: str, meta: dict[str, Any]) -> None:
        self.client.collection("clips").document(clip_id).set({"source_id": source_id, "external_id": external_id, "niche": niche, "status": "outbox", "path": path, "meta": meta, "updated_at": now()}, merge=True)

    def transition_clip(self, clip_id: str, status: str, rejection_reason: str | None = None) -> None:
        self.client.collection("clips").document(clip_id).set({"status": status, "rejection_reason": rejection_reason, "updated_at": now()}, merge=True)

    def recent_feedback(self, niche: str, limit: int = 20) -> list[str]:
        rows = self.client.collection("clips").where("niche", "==", niche).where("status", "==", "rejected").order_by("updated_at", direction="DESCENDING").limit(limit).stream()
        reasons = [item.to_dict().get("rejection_reason", "") for item in rows if item.to_dict().get("rejection_reason")]
        if len(reasons) >= limit:
            return reasons[:limit]
        reasons.extend(_feedback_jsonl(niche, limit - len(reasons), exclude=set(reasons)))
        return reasons[:limit]

    def record_run(self, summary: dict[str, Any]) -> None:
        self.client.collection("runs").add(summary | {"created_at": now()})

    def last_run_at(self) -> datetime | None:
        rows = self.client.collection("runs").order_by("created_at", direction="DESCENDING").limit(1).stream()
        for item in rows:
            value = item.to_dict().get("created_at")
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value)
        return None


def build_state(backend: str, project: str | None = None) -> StateRepository:
    return FirestoreState(project) if backend == "firestore" else SQLiteState()
