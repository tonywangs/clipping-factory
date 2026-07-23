"""Shared LLM text-generation helper used by ranking and content formats."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: "LLMUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


def extract_json(value: str) -> dict:
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip())
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end < start:
            raise
        return json.loads(value[start : end + 1])


def call_llm(prompt: str, provider: str | None = None) -> tuple[str, LLMUsage]:
    provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
    usage = LLMUsage()
    if provider == "anthropic":
        from anthropic import Anthropic

        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=4096,
            temperature=0.4,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.usage:
            usage = LLMUsage(
                input_tokens=int(response.usage.input_tokens or 0),
                output_tokens=int(response.usage.output_tokens or 0),
            )
        return "".join(block.text for block in response.content if hasattr(block, "text")), usage
    if provider == "openai":
        from openai import OpenAI

        response = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        if response.usage:
            usage = LLMUsage(
                input_tokens=int(response.usage.prompt_tokens or 0),
                output_tokens=int(response.usage.completion_tokens or 0),
            )
        return response.choices[0].message.content or "{}", usage
    if provider == "gemini":
        from google import genai

        response = genai.Client(api_key=os.environ["GEMINI_API_KEY"]).models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.4},
        )
        meta = getattr(response, "usage_metadata", None)
        if meta:
            usage = LLMUsage(
                input_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
            )
        return response.text or "{}", usage
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
