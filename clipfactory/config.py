from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import NicheConfig, Settings, SourcesConfig


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    raw = yaml.safe_load(path.read_text())
    return raw or {}


@lru_cache(maxsize=1)
def project_root() -> Path:
    return Path(os.getenv("LOCAL_ROOT", Path.cwd())).resolve()


def load_settings(root: Path | None = None) -> Settings:
    root = root or project_root()
    values = _read_yaml(root / "config" / "settings.yaml")
    for field in ("storage_backend", "state_backend", "whisper_model", "whisper_device"):
        if os.getenv(field.upper()):
            values[field] = os.environ[field.upper()]
    return Settings.model_validate(values)


def load_sources(root: Path | None = None) -> SourcesConfig:
    return SourcesConfig.model_validate(_read_yaml((root or project_root()) / "config" / "sources.yaml"))


def load_niche(name: str, root: Path | None = None) -> NicheConfig:
    path = (root or project_root()) / "config" / "niches" / f"{name}.yaml"
    niche = NicheConfig.model_validate(_read_yaml(path))
    if niche.name != name:
        raise ValidationError.from_exception_data("NicheConfig", [])
    return niche


def load_all_niches(root: Path | None = None) -> dict[str, NicheConfig]:
    base = (root or project_root()) / "config" / "niches"
    return {path.stem: NicheConfig.model_validate(_read_yaml(path)) for path in base.glob("*.yaml")}
