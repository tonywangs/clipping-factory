from pathlib import Path

import pytest

from clipfactory.config import load_niche
from clipfactory.models import ClipLength


def test_startup_niche_is_valid():
    niche = load_niche("startup", Path.cwd())
    assert niche.caption_style == "hormozi"
    assert niche.clip_length_seconds.max == 55


def test_clip_length_validation():
    with pytest.raises(ValueError):
        ClipLength(min=50, max=20)
