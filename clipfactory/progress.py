"""Small, dependency-free progress reporter for long-running CLI jobs."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Progress:
    """Print timestamped, immediately flushed progress messages to stderr."""

    job: str
    started_at: float = field(default_factory=time.monotonic)

    def emit(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        elapsed = time.monotonic() - self.started_at
        print(
            f"[{timestamp}] [{self.job}] +{elapsed:5.1f}s  {message}",
            file=sys.stderr,
            flush=True,
        )

    def step(self, current: int, total: int, message: str) -> None:
        self.emit(f"[{current}/{total}] {message}")

    def done(self, message: str = "Complete") -> None:
        self.emit(f"{message} ({time.monotonic() - self.started_at:.1f}s total)")
