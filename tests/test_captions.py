from pathlib import Path

from clipfactory.models import CaptionStyle, Word
from clipfactory.render.captions import write_ass


def test_hormozi_ass_has_active_word_color(tmp_path: Path):
    target = write_ass(
        [Word(word="hello", start=1, end=2), Word(word="world", start=2, end=3)],
        1,
        3,
        CaptionStyle.HORMOZI,
        "#FFD400",
        tmp_path / "clip.ass",
    )
    content = target.read_text()
    assert "Dialogue" in content
    assert "&H0000D4FF&" in content


def test_karaoke_ass_has_k_timing(tmp_path: Path):
    target = write_ass([Word(word="hello", start=1, end=2)], 1, 2, CaptionStyle.KARAOKE, "#FFD400", tmp_path / "clip.ass")
    assert "\\k100" in target.read_text()
