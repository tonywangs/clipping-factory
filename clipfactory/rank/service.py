from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from ..models import Candidate, NicheConfig, Transcript, TranscriptSegment, Word

CHUNK_SIZE_SECONDS = 1200
LONG_VIDEO_THRESHOLD = 1800
CHUNK_OVERLAP_SECONDS = 60
START_PAD_SECONDS = 0.3


class CandidateBatch(BaseModel):
    highlights: list[Candidate] = Field(default_factory=list)


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


@dataclass
class RankResult:
    candidates: list[Candidate]
    usage: TokenUsage = field(default_factory=TokenUsage)


def _transcript_text(segments: list[TranscriptSegment]) -> str:
    return "\n".join(f"[{segment.start:.1f}s] {segment.text}" for segment in segments)


def _prompt(segments: list[TranscriptSegment], niche: NicheConfig, feedback: list[str]) -> str:
    return f"""You are an elite short-form video editor for podcast clips on TikTok/Reels.
Audience: {niche.audience}
Tone: {niche.tone}
Prioritize: {', '.join(niche.prioritize_topics) or 'strong useful moments'}
Skip: {', '.join(niche.skip_topics) or 'nothing'}
Banned words: {', '.join(niche.banned_words) or 'none'}
Length: {niche.clip_length_seconds.min}-{niche.clip_length_seconds.max} seconds.
Example hooks: {json.dumps(niche.example_hooks)}
Recent rejected-clip guidance (avoid repeating these failures): {json.dumps(feedback[-20:])}

CRITICAL — every clip must make sense with ZERO prior context:
1. Prefer moments that open with a clear claim, story beat, or the host's question that sets up the punchline.
2. If the best line is an answer, INCLUDE the question/setup immediately before it (even if that means starting earlier).
3. Reject clips that start mid-explanation with vague pronouns ("it", "that", "they") and no referent.
4. Technical/jargon-heavy answers are only good if the first 3 seconds tell a non-expert what is being claimed.
5. Do not cut mid-sentence or mid-thought. End on a complete payoff.
6. Seek hooks, opinion bombs, revelations, conflict, quotables, story peaks, practical value.

Return 5-8 hashtags mixing niche staples and episode-specific tags.
Return JSON only: {{"highlights":[{{"start":number,"end":number,"score":integer,"title":string,"hook_sentence":string,"virality_reason":string,"suggested_caption":string,"hashtags":[string]}}]}}.

Transcript:
{_transcript_text(segments)}"""


def _extract_json(value: str) -> dict:
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip())
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end < start:
            raise
        return json.loads(value[start : end + 1])


def _call_provider(prompt: str, provider: str | None = None) -> tuple[str, TokenUsage]:
    provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
    usage = TokenUsage()
    if provider == "anthropic":
        from anthropic import Anthropic

        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.usage:
            usage = TokenUsage(input_tokens=int(response.usage.input_tokens or 0), output_tokens=int(response.usage.output_tokens or 0))
        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        return text, usage
    if provider == "openai":
        from openai import OpenAI

        response = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        if response.usage:
            usage = TokenUsage(input_tokens=int(response.usage.prompt_tokens or 0), output_tokens=int(response.usage.completion_tokens or 0))
        return response.choices[0].message.content or "{}", usage
    if provider == "gemini":
        from google import genai

        response = genai.Client(api_key=os.environ["GEMINI_API_KEY"]).models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        meta = getattr(response, "usage_metadata", None)
        if meta:
            usage = TokenUsage(
                input_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
            )
        return response.text or "{}", usage
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def chunk_transcript(transcript: Transcript) -> list[tuple[float, list[TranscriptSegment]]]:
    """Split long transcripts into overlapping windows. Returns (offset, segments)."""
    if transcript.duration < LONG_VIDEO_THRESHOLD:
        return [(0.0, transcript.segments)]
    chunks: list[tuple[float, list[TranscriptSegment]]] = []
    start = 0.0
    while start < transcript.duration:
        end = min(start + CHUNK_SIZE_SECONDS, transcript.duration)
        segs = [s for s in transcript.segments if s.end >= start and s.start <= end + CHUNK_OVERLAP_SECONDS]
        if segs:
            chunks.append((start, segs))
        if end >= transcript.duration:
            break
        start += CHUNK_SIZE_SECONDS - CHUNK_OVERLAP_SECONDS
    return chunks or [(0.0, transcript.segments)]


CONTEXT_LOOKBACK_SECONDS = 14.0


def expand_for_context(candidate: Candidate, transcript: Transcript, max_seconds: float) -> Candidate:
    """If a host question/setup sits just before the clip, pull the start back to include it."""
    limit = max(0.0, candidate.start - CONTEXT_LOOKBACK_SECONDS)
    setup: TranscriptSegment | None = None
    for segment in transcript.segments:
        if segment.end <= limit or segment.start >= candidate.start:
            continue
        text = segment.text.strip()
        if not text:
            continue
        if "?" in text or re.search(r"\b(why|how|what|when|who|can you|tell me|do you)\b", text, re.I):
            setup = segment
            break
    if setup is None:
        return candidate
    new_start = setup.start
    # Keep under max duration; if too long, keep as much setup as fits.
    max_end_span = min(max_seconds, 60)
    if candidate.end - new_start > max_end_span:
        new_start = max(setup.start, candidate.end - max_end_span)
    if new_start >= candidate.start:
        return candidate
    return candidate.model_copy(update={"start": round(new_start, 3)})


def snap_to_words(candidate: Candidate, transcript: Transcript, min_seconds: float, max_seconds: float) -> Candidate | None:
    words = [word for segment in transcript.segments for word in segment.words]
    if not words:
        duration = candidate.end - candidate.start
        return candidate if min_seconds <= duration <= max_seconds else None

    start_index = next((index for index, word in enumerate(words) if word.end >= candidate.start), 0)
    end_index = next((index for index in range(len(words) - 1, -1, -1) if words[index].start <= candidate.end), len(words) - 1)
    if end_index < start_index:
        return None

    start_word = words[start_index]
    end_word = words[end_index]
    previous_end = words[start_index - 1].end if start_index > 0 else 0.0
    pad = min(START_PAD_SECONDS, max(0.0, start_word.start - previous_end))
    start = max(0.0, start_word.start - pad)
    end = end_word.end
    duration = end - start
    if duration < min_seconds or duration > min(max_seconds, 60):
        return None
    return candidate.model_copy(update={"start": round(start, 3), "end": round(end, 3)})


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    result: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        duration = candidate.end - candidate.start
        if all(max(0.0, min(candidate.end, kept.end) - max(candidate.start, kept.start)) <= 0.5 * duration for kept in result):
            result.append(candidate)
    return result


def _normalize_hashtags(candidate: Candidate, niche: NicheConfig) -> Candidate:
    tags = []
    for tag in [*niche.hashtags_base, *candidate.hashtags]:
        cleaned = tag if tag.startswith("#") else f"#{tag.lstrip('#')}"
        if cleaned.lower() not in {item.lower() for item in tags}:
            tags.append(cleaned)
    return candidate.model_copy(update={"hashtags": tags[:8]})


def _rank_chunk(
    segments: list[TranscriptSegment],
    niche: NicheConfig,
    feedback: list[str],
    call: Callable[[str], tuple[str, TokenUsage]],
) -> tuple[list[Candidate], TokenUsage]:
    prompt = _prompt(segments, niche, feedback)
    usage = TokenUsage()
    last_error: Exception | None = None
    for _ in range(3):
        try:
            raw, call_usage = call(prompt)
            usage.add(call_usage)
            batch = CandidateBatch.model_validate(_extract_json(raw))
            return batch.highlights, usage
        except Exception as exc:
            last_error = exc
            prompt += "\nReturn strictly valid JSON matching the requested schema."
    raise RuntimeError(f"Ranker returned invalid data after 3 attempts: {last_error}")


def rank_candidates(
    transcript: Transcript,
    niche: NicheConfig,
    feedback: list[str],
    call: Callable[[str], tuple[str, TokenUsage]] | Callable[[str], str] | None = None,
) -> RankResult:
    def adapter(prompt: str) -> tuple[str, TokenUsage]:
        if call is None:
            return _call_provider(prompt)
        result = call(prompt)
        if isinstance(result, tuple):
            return result
        return result, TokenUsage()

    chunks = chunk_transcript(transcript)
    collected: list[Candidate] = []
    usage = TokenUsage()
    for _offset, segments in chunks:
        highlights, chunk_usage = _rank_chunk(segments, niche, feedback, adapter)
        usage.add(chunk_usage)
        # Prompts use absolute segment timestamps, so model times stay absolute.
        collected.extend(highlights)

    snapped: list[Candidate] = []
    for item in collected:
        if item.score < niche.min_score:
            continue
        with_context = expand_for_context(item, transcript, niche.clip_length_seconds.max)
        fixed = snap_to_words(
            with_context,
            transcript,
            niche.clip_length_seconds.min,
            niche.clip_length_seconds.max,
        )
        if fixed:
            snapped.append(_normalize_hashtags(fixed, niche))
    return RankResult(candidates=_dedupe(snapped)[: niche.clips_per_episode], usage=usage)


def estimate_cost_usd(usage: TokenUsage, prices: dict[str, float]) -> float:
    input_rate = float(prices.get("input", 3.0))
    output_rate = float(prices.get("output", 15.0))
    return round((usage.input_tokens * input_rate + usage.output_tokens * output_rate) / 1_000_000, 6)
