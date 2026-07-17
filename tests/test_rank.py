from clipfactory.models import Candidate, CaptionStyle, ClipLength, NicheConfig, Transcript, TranscriptSegment, Word
from clipfactory.rank import rank_candidates, snap_to_words


def transcript():
    return Transcript(duration=40, segments=[TranscriptSegment(start=0, end=40, text="one two three four", words=[Word(word="one", start=10, end=11), Word(word="two", start=11, end=12), Word(word="three", start=12, end=35), Word(word="four", start=35, end=36)])])


def niche():
    return NicheConfig(name="test", account_handle="@test", audience="test", tone="test", clip_length_seconds=ClipLength(min=20, max=40), caption_style=CaptionStyle.HORMOZI, accent_color="#FFD400")


def test_snap_to_word_boundaries():
    result = snap_to_words(Candidate(start=10.3, end=35.5, score=90, title="x", hook_sentence="x", virality_reason="x"), transcript(), 20, 40)
    assert result and result.start == 10 and result.end == 36


def test_rank_deduplicates_and_filters_score():
    def fake(_: str) -> str:
        return '{"highlights":[{"start":10.2,"end":35.8,"score":90,"title":"first","hook_sentence":"h","virality_reason":"r","hashtags":["#x"]},{"start":11,"end":35,"score":80,"title":"duplicate","hook_sentence":"h","virality_reason":"r"}]}'
    result = rank_candidates(transcript(), niche(), [], fake)
    assert [item.title for item in result] == ["first"]
