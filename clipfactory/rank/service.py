from __future__ import annotations

import json
import os
import re
from collections.abc import Callable

from pydantic import BaseModel, Field

from ..models import Candidate, NicheConfig, Transcript, Word


class CandidateBatch(BaseModel):
    highlights: list[Candidate] = Field(default_factory=list)


def _transcript_text(transcript: Transcript) -> str:
    return "\n".join(f"[{segment.start:.1f}s] {segment.text}" for segment in transcript.segments)


def _prompt(transcript: Transcript, niche: NicheConfig, feedback: list[str]) -> str:
    return f"""You are an elite short-form video editor. Select viral, self-contained clips.
Audience: {niche.audience}
Tone: {niche.tone}
Prioritize: {', '.join(niche.prioritize_topics) or 'strong useful moments'}
Skip: {', '.join(niche.skip_topics) or 'nothing'}
Banned words: {', '.join(niche.banned_words) or 'none'}
Length: {niche.clip_length_seconds.min}-{niche.clip_length_seconds.max} seconds.
Example hooks: {json.dumps(niche.example_hooks)}
Recent rejected-clip guidance: {json.dumps(feedback)}
Score viral potential 0-100. Seek hooks, emotional peaks, opinion bombs, revelations,
conflict, quotable lines, story peaks, and practical value. Do not cut mid-thought.
Return JSON only: {{"highlights":[{{"start":number,"end":number,"score":integer,"title":string,"hook_sentence":string,"virality_reason":string,"suggested_caption":string,"hashtags":[string]}}]}}.

Transcript:
{_transcript_text(transcript)}"""


def _extract_json(value: str) -> dict:
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip())
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end < start:
            raise
        return json.loads(value[start:end + 1])


def _call_provider(prompt: str, provider: str | None = None) -> str:
    provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"), max_tokens=4096, temperature=0.2, messages=[{"role": "user", "content": prompt}])
        return "".join(block.text for block in response.content if hasattr(block, "text"))
    if provider == "openai":
        from openai import OpenAI
        response = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), messages=[{"role": "user", "content": prompt}], temperature=0.2, response_format={"type": "json_object"})
        return response.choices[0].message.content or "{}"
    if provider == "gemini":
        from google import genai
        response = genai.Client(api_key=os.environ["GEMINI_API_KEY"]).models.generate_content(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), contents=prompt, config={"response_mime_type": "application/json", "temperature": 0.2})
        return response.text or "{}"
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def snap_to_words(candidate: Candidate, transcript: Transcript, min_seconds: float, max_seconds: float) -> Candidate | None:
    words = [word for segment in transcript.segments for word in segment.words]
    if not words:
        return candidate if min_seconds <= candidate.end - candidate.start <= max_seconds else None
    start_word = next((word for word in words if word.end >= candidate.start), words[0])
    end_word = next((word for word in reversed(words) if word.start <= candidate.end), words[-1])
    start, end = start_word.start, end_word.end
    duration = end - start
    if duration < min_seconds or duration > min(max_seconds, 60):
        return None
    return candidate.model_copy(update={"start": round(start, 3), "end": round(end, 3)})


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    result: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        if all(max(0, min(candidate.end, kept.end) - max(candidate.start, kept.start)) <= .5 * (candidate.end - candidate.start) for kept in result):
            result.append(candidate)
    return result


def rank_candidates(transcript: Transcript, niche: NicheConfig, feedback: list[str], call: Callable[[str], str] = _call_provider) -> list[Candidate]:
    prompt = _prompt(transcript, niche, feedback)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            batch = CandidateBatch.model_validate(_extract_json(call(prompt)))
            candidates = [snapped for item in batch.highlights if item.score >= niche.min_score if (snapped := snap_to_words(item, transcript, niche.clip_length_seconds.min, niche.clip_length_seconds.max))]
            return _dedupe(candidates)[:niche.clips_per_episode]
        except Exception as exc:
            last_error = exc
            prompt += "\nReturn strictly valid JSON matching the requested schema."
    raise RuntimeError(f"Ranker returned invalid data after 3 attempts: {last_error}")
