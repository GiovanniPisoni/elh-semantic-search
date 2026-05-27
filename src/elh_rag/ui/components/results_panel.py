"""
Results panel (right column of the chat view).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from elh_rag.agent._models import AgentResponse
from elh_rag.ui.components.property_card import (
    render_property_card,
    render_snippet_card,
)

logger = logging.getLogger(__name__)

_MAX_SNIPPETS_PER_CORPUS = 3


def extract_cards(response: AgentResponse | None) -> list[str]:
    """Walk ``response.tool_trace`` and produce ordered HTML cards."""
    if response is None:
        return []

    cards: list[str] = []
    seen_room_ids: set[str] = set()
    snippets_per_corpus: dict[str, int] = {}

    for call in response.tool_trace:
        if call.error or not call.output_json:
            continue
        try:
            output: Any = json.loads(call.output_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse tool output for %s; skipping", call.name)
            continue

        if call.name in ("find_rooms", "find_available_rooms"):
            cards.extend(_cards_from_rooms(output, seen_room_ids))
        elif call.name == "get_property_details":
            cards.extend(_cards_from_property_details(output))
        elif call.name in ("search_descriptions", "search_reviews"):
            corpus = "descriptions" if call.name == "search_descriptions" else "reviews"
            already = snippets_per_corpus.get(corpus, 0)
            remaining = max(0, _MAX_SNIPPETS_PER_CORPUS - already)
            new_cards = _cards_from_search_hits(output, corpus, remaining)
            cards.extend(new_cards)
            snippets_per_corpus[corpus] = already + len(new_cards)

    return cards


def _cards_from_rooms(output: Any, seen: set[str]) -> list[str]:
    if not isinstance(output, dict):
        return []
    rooms = output.get("rooms") or []
    out: list[str] = []
    for room in rooms:
        if not isinstance(room, dict):
            continue
        rid = str(room.get("room_id") or room.get("encoded_room_id") or "")
        if rid and rid in seen:
            continue
        if rid:
            seen.add(rid)
        out.append(render_property_card(room))
    return out


def _cards_from_property_details(output: Any) -> list[str]:
    if not isinstance(output, dict):
        return []
    house = output.get("house") or {}
    room = output.get("room") or {}
    if not isinstance(house, dict):
        house = {}
    if not isinstance(room, dict):
        room = {}
    if not house and not room:
        return []
    merged = {**house, **room}
    return [render_property_card(merged)]


def _cards_from_search_hits(output: Any, corpus: str, limit: int) -> list[str]:
    if limit <= 0 or not isinstance(output, dict):
        return []
    hits = output.get("hits") or []
    out: list[str] = []
    for hit in hits[:limit]:
        if not isinstance(hit, dict):
            continue
        out.append(render_snippet_card(hit, corpus))
    return out


def header_html(n_cards: int) -> str:
    """Return the right-column header markup (grid row 1)."""
    suffix = "s" if n_cards != 1 else ""
    return (
        '<div class="col-header">'
        '<div class="col-header-title">Search results</div>'
        f'<div class="col-header-sub">{n_cards} result{suffix}</div>'
        "</div>"
    )


def body_html(cards: list[str]) -> str:
    """Return the scrollable cards body (grid row 2)."""
    if not cards:
        return (
            '<div class="col-scroll">'
            '<div class="results-empty">No properties to show for this query.</div>'
            "</div>"
        )
    return '<div class="col-scroll">' + "".join(cards) + "</div>"


def footer_html() -> str:
    """Return the empty white footer (grid row 3)."""
    return '<div class="chat-footer-right"></div>'
