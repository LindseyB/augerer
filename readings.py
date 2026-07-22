"""Tarot reading generation: builds prompts from card data and streams AI text.

Mirrors the ``calculations.py`` streaming pattern from the sibling ``astro``
project, adapted to tarot card data.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from typing import Any

from ai_service import stream_ai_api
from prompt_templates import load_prompt_template, load_prompt_text

logger = logging.getLogger(__name__)

THREE_CARD_POSITIONS = ("Past", "Present", "Future")

_ONE_CARD_FALLBACK = (
    "**The cards are quiet.** The reader is taking a cosmic tea break. "
    "Sit with the card you drew and trust your own intuition. \u2728"
)
_THREE_CARD_FALLBACK = (
    "**The cards are quiet.** The reader is taking a cosmic tea break. "
    "Reflect on your three cards as past, present, and future, and trust "
    "your own intuition. \u2728"
)


def _prompt_temperature(metadata: Mapping[str, object]) -> float:
    value = metadata.get("temperature", 0.8)
    if isinstance(value, bool):
        return 0.8
    return float(value) if isinstance(value, (int, float)) else 0.8


def _card_block(card: dict[str, Any], orientation: str, position: str | None = None) -> str:
    orientation = "reversed" if orientation == "reversed" else "upright"
    meanings = card.get("meanings", {}) or {}
    cues = meanings.get(orientation) or []
    cue_text = ", ".join(str(cue) for cue in cues) if cues else "(no cues on file)"

    suit = str(card.get("suit", "") or "unknown").title()
    rank = card.get("rank", "")

    header = f"- {card.get('name', 'Unknown card')} ({orientation.title()})"
    if position:
        header += f" \u2014 Position: {position}"

    details = f"  Suit: {suit} \u00b7 Rank: {rank}"
    cue_line = f"  {orientation.title()} meaning cues: {cue_text}"
    return "\n".join([header, details, cue_line])


def build_one_card_prompt(card: dict[str, Any], orientation: str) -> str:
    template = load_prompt_template("one_card_user.md")
    return template.render(card_block=_card_block(card, orientation))


def build_three_card_prompt(drawn: list[dict[str, Any]]) -> str:
    template = load_prompt_template("three_card_user.md")
    blocks = [
        _card_block(entry["card"], entry.get("orientation", "upright"), entry.get("position"))
        for entry in drawn
    ]
    return template.render(card_block="\n\n".join(blocks))


def stream_one_card_reading(card: dict[str, Any], orientation: str, question: str | None = None) -> Iterator[str]:
    """Stream a single-card reading, yielding text chunks."""
    template = load_prompt_template("one_card_user.md")
    user_prompt = template.render(card_block=_card_block(card, orientation))
    if question:
        user_prompt = f"The querent's question: {question}\n\n{user_prompt}"
    system_content = load_prompt_text("reading_system.md")

    try:
        yield from stream_ai_api(
            system_content, user_prompt, temperature=_prompt_temperature(template.metadata)
        )
    except Exception as exc:  # pragma: no cover - network/credential errors
        logger.error("Error streaming one-card reading: %s", exc)
        yield _ONE_CARD_FALLBACK


def stream_three_card_reading(drawn: list[dict[str, Any]], question: str | None = None) -> Iterator[str]:
    """Stream a past/present/future reading, yielding text chunks."""
    template = load_prompt_template("three_card_user.md")
    blocks = [
        _card_block(entry["card"], entry.get("orientation", "upright"), entry.get("position"))
        for entry in drawn
    ]
    user_prompt = template.render(card_block="\n\n".join(blocks))
    if question:
        user_prompt = f"The querent's question: {question}\n\n{user_prompt}"
    system_content = load_prompt_text("reading_system.md")

    try:
        yield from stream_ai_api(
            system_content, user_prompt, temperature=_prompt_temperature(template.metadata)
        )
    except Exception as exc:  # pragma: no cover - network/credential errors
        logger.error("Error streaming three-card reading: %s", exc)
        yield _THREE_CARD_FALLBACK
