"""
LLM client for CoGMEM-QA agents.

Uses the google-genai SDK (google.genai, v1+).  The client is created once
and cached; agents that need testability should inject their own llm_fn
rather than calling call_llm() directly.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Callable

from google import genai

_MODEL = "gemini-2.0-flash"


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    """Return a cached Gemini client.  Raises ValueError if GEMINI_API_KEY is unset."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable not set. "
            "Add it to .env or export it before running agents."
        )
    return genai.Client(api_key=api_key)


def call_llm(prompt: str) -> str:
    """Send *prompt* to Gemini and return the text response."""
    client = get_gemini_client()
    response = client.models.generate_content(model=_MODEL, contents=prompt)
    return response.text


def call_llm_with(prompt: str, llm_fn: Callable[[str], str]) -> str:
    """Call *llm_fn* with *prompt* and return its string result."""
    return llm_fn(prompt)
