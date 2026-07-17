from clipfactory.ids import make_clip_id
from clipfactory.models import Candidate, CaptionStyle, ClipLength, NicheConfig, Transcript, TranscriptSegment, Word
from clipfactory.rank import chunk_transcript, estimate_cost_usd, rank_candidates, snap_to_words
from clipfactory.rank.service import TokenUsage


def transcript():
    return Transcript(
        duration=40,
        segments=[
            TranscriptSegment(
                start=0,
                end=40,
                text="one two three four",
                words=[
                    Word(word="one", start=10, end=11),
                    Word(word="two", start=11, end=12),
                    Word(word="three", start=12, end=35),
                    Word(word="four", start=35, end=36),
                ],
            )
        ],
    )


def niche():
    return NicheConfig(
        name="test",
        account_handle="@test",
        audience="test",
        tone="test",
        clip_length_seconds=ClipLength(min=20, max=40),
        caption_style=CaptionStyle.HORMOZI,
        accent_color="#FFD400",
        hashtags_base=["#startup"],
    )


def test_snap_to_word_boundaries_pads_leading_silence():
    result = snap_to_words(
        Candidate(start=10.3, end=35.5, score=90, title="x", hook_sentence="x", virality_reason="x"),
        transcript(),
        20,
        40,
    )
    assert result is not None
    assert result.start == 9.7
    assert result.end == 36


def test_rank_deduplicates_and_filters_score():
    def fake(_: str):
        return (
            '{"highlights":[{"start":10.2,"end":35.8,"score":90,"title":"first","hook_sentence":"h",'
            '"virality_reason":"r","suggested_caption":"c","hashtags":["#x"]},'
            '{"start":11,"end":35,"score":80,"title":"duplicate","hook_sentence":"h","virality_reason":"r",'
            '"suggested_caption":"c","hashtags":[]}]}'
        )

    result = rank_candidates(transcript(), niche(), [], fake)
    assert [item.title for item in result.candidates] == ["first"]
    assert result.candidates[0].hashtags[0] == "#startup"


def test_chunk_transcript_splits_long_audio():
    words = [Word(word=f"w{i}", start=float(i), end=float(i) + 0.5) for i in range(0, 2500, 30)]
    long = Transcript(
        duration=2500,
        segments=[TranscriptSegment(start=w.start, end=w.end, text=w.word, words=[w]) for w in words],
    )
    chunks = chunk_transcript(long)
    assert len(chunks) >= 2


def test_estimate_cost():
    assert estimate_cost_usd(TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000), {"input": 3, "output": 15}) == 18.0


def test_clip_id_stable():
    assert make_clip_id("a", "b", "startup", 1.0, 2.0) == make_clip_id("a", "b", "startup", 1.0, 2.0)
    assert make_clip_id("a", "b", "startup", 1.0, 2.0) != make_clip_id("a", "c", "startup", 1.0, 2.0)
