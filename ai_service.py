"""AI service for tarot reading generation using Anthropic Claude.

Mirrors the streaming approach used in the sibling ``astro`` project so the
tarot app can generate readings from the card data we already model.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterator

try:  # Load a local .env when present, matching the astro project.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass

from anthropic import Anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4000

_client: Anthropic | None = None


def _token() -> str | None:
    return os.environ.get("ANTHROPIC_TOKEN")


def has_ai_client() -> bool:
    """Return True when an Anthropic token is configured."""
    return bool(_token())


def get_client() -> Anthropic:
    """Get or lazily create the Anthropic client, validating the token."""
    global _client
    if _client is None:
        token = _token()
        if not token:
            raise ValueError("ANTHROPIC_TOKEN environment variable is not set")
        _client = Anthropic(api_key=token, timeout=60.0)
    return _client


def stream_ai_api(
    system_content: str, user_prompt: str, temperature: float = 0.8
) -> Iterator[str]:
    """Stream an Anthropic response, yielding text chunks.

    Raises the underlying exception so callers can surface a friendly message.
    """
    api_client = get_client()
    with api_client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=temperature,
        system=system_content,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
