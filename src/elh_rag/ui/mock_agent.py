"""
Mock agent for UI smoke tests.

Drop-in for ``run_agent_turn`` that returns a hardcoded ``AgentResponse``
without hitting the Anthropic API. Toggled via the ``ELH_USE_MOCK_AGENT``
env var (see :mod:`elh_rag.ui.app`).

Four canonical questions are matched exactly (case- and whitespace-
insensitive); everything else routes to a generic catch-all that returns
two rooms via a synthetic ``find_rooms`` trace.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from elh_rag.agent._models import AgentResponse, ConversationTurn, ToolCall

# Hardcoded rooms (canonical Phase 3 RoomMatch field set)

_ROOM_INTENDENTE: dict[str, Any] = {
    "room_id": "HSE_INTENDENTE|RM_101",
    "house_id": "HSE_INTENDENTE",
    "house_name": "Intendente Charm",
    "city": "Lisbon",
    "zone": "Centro",
    "neighborhood": "Intendente",
    "price_per_month_eur": 450.0,
    "private_bathroom": True,
    "distance_to_transport_m": 120,
    "nearest_metro_line": "Verde",
    "available_from": "2026-09-01",
    "min_reserve_months": 3,
    "amenities": ["wifi", "washer", "elevator"],
    "excerpt": (
        "Charming room near Intendente metro, great natural light and a "
        "small balcony overlooking the square."
    ),
    "match_score": 0.93,
    "is_fixed_price": False,
    "price_label": "",
}

_ROOM_ALFAMA: dict[str, Any] = {
    "room_id": "HSE_ALFAMA|RM_3",
    "house_id": "HSE_ALFAMA",
    "house_name": "Alfama Heights",
    "city": "Lisbon",
    "zone": "Centro",
    "neighborhood": "Alfama",
    "price_per_month_eur": 520.0,
    "private_bathroom": False,
    "distance_to_transport_m": 350,
    "nearest_metro_line": "Azul",
    "available_from": "2026-09-15",
    "min_reserve_months": 4,
    "amenities": ["wifi", "rooftop_view"],
    "excerpt": (
        "Quiet room in the heart of historic Alfama with a balcony and "
        "tiled floors. Shared bathroom with one housemate."
    ),
    "match_score": 0.89,
    "is_fixed_price": False,
    "price_label": "",
}

_ROOM_BAIRROALTO: dict[str, Any] = {
    "room_id": "HSE_BAIRROALTO|RM_2",
    "house_id": "HSE_BAIRROALTO",
    "house_name": "Bairro Alto Studios",
    "city": "Lisbon",
    "zone": "Centro",
    "neighborhood": "Bairro Alto",
    "price_per_month_eur": 395.0,
    "private_bathroom": True,
    "distance_to_transport_m": 80,
    "nearest_metro_line": "Verde",
    "available_from": "2026-09-05",
    "min_reserve_months": 3,
    "amenities": ["wifi", "balcony"],
    "excerpt": (
        "Compact studio in lively Bairro Alto with private bathroom, "
        "ideal for a short Erasmus stay."
    ),
    "match_score": 0.86,
    "is_fixed_price": False,
    "price_label": "",
}


# Helpers


def _dumps(payload: Any) -> str:
    """JSON-serialise mock tool output. Mirrors the post-fix agent loop."""
    return json.dumps(payload, default=str)


def _tool_call(
    *,
    hop_index: int,
    name: str,
    input_payload: dict[str, Any],
    output_payload: Any,
    duration_ms: int,
) -> ToolCall:
    return ToolCall(
        hop_index=hop_index,
        name=name,
        input_json=_dumps(input_payload),
        output_json=_dumps(output_payload),
        error=None,
        duration_ms=duration_ms,
        started_at=datetime.now(UTC),
    )


def _assemble(
    *,
    query: str,
    final_message: str,
    tool_trace: list[ToolCall],
    total_duration_ms: int,
) -> AgentResponse:
    return AgentResponse(
        query=query,
        final_message=final_message,
        stop_reason="end_turn",
        hop_count=max(1, len(tool_trace) + 1),
        tool_trace=tool_trace,
        input_tokens=850,
        output_tokens=320,
        total_duration_ms=total_duration_ms,
        started_at=datetime.now(UTC),
    )


# Response builders


def _response_lisbon_september(query: str) -> AgentResponse:
    """Q1: Find rooms in Lisbon available from September 2026."""
    output = {
        "rooms": [_ROOM_INTENDENTE, _ROOM_ALFAMA, _ROOM_BAIRROALTO],
        "total_matches": 3,
        "query_summary": "Lisbon rooms available 2026-09-01..2027-02-28",
    }
    call = _tool_call(
        hop_index=0,
        name="find_available_rooms",
        input_payload={
            "query": "rooms in Lisbon",
            "city": "Lisbon",
            "available_from": "2026-09-01",
            "available_to": "2027-02-28",
            "top_k": 5,
        },
        output_payload=output,
        duration_ms=420,
    )
    final = (
        "I found 3 rooms in Lisbon available from September 2026. Here are "
        "the best matches:\n\n"
        "- **Intendente Charm** — €450/month, private bathroom, 2 min from "
        "the green-line metro.\n"
        "- **Alfama Heights** — €520/month, shared bathroom, historic centre.\n"
        "- **Bairro Alto Studios** — €395/month, private bathroom, lively "
        "neighbourhood.\n\n"
        "Let me know which one you'd like more details on."
    )
    return _assemble(query=query, final_message=final, tool_trace=[call], total_duration_ms=1180)


def _response_cancellation_policy(query: str) -> AgentResponse:
    """Q2: cancellation policy & deposit refund (no cards)."""
    output = {
        "answer": (
            "Bookings can be cancelled up to 30 days before move-in for a "
            "full refund of the first month's payment, minus a 5% admin fee. "
            "The deposit is fully refundable at the end of the stay subject "
            "to no damages."
        ),
        "citations": ["policy_v3.md#cancellation", "policy_v3.md#deposit"],
    }
    call = _tool_call(
        hop_index=0,
        name="answer_policy_question",
        input_payload={"question": "cancellation policy and deposit refund"},
        output_payload=output,
        duration_ms=380,
    )
    final = (
        "**Cancellation policy:** You can cancel up to 30 days before move-in "
        "and receive a full refund of the first month's rent, minus a 5% "
        "administrative fee.\n\n"
        "**Deposit:** Your security deposit is fully refundable at the end "
        "of your stay, provided there are no damages beyond normal wear and "
        "tear. Refunds are processed within 14 days of move-out."
    )
    return _assemble(query=query, final_message=final, tool_trace=[call], total_duration_ms=950)


def _response_total_cost_intendente(query: str) -> AgentResponse:
    """Q3: total cost for a 6-month stay in Intendente."""
    rooms_output = {
        "rooms": [_ROOM_INTENDENTE, _ROOM_BAIRROALTO],
        "total_matches": 2,
        "query_summary": "Rooms in Intendente, Lisbon",
    }
    rooms_call = _tool_call(
        hop_index=0,
        name="find_rooms",
        input_payload={"query": "rooms in Intendente", "neighborhood": "Intendente", "top_k": 5},
        output_payload=rooms_output,
        duration_ms=310,
    )
    cost_intendente = _tool_call(
        hop_index=1,
        name="compute_total_cost",
        input_payload={"room_id": _ROOM_INTENDENTE["room_id"], "months": 6},
        output_payload={
            "room_id": _ROOM_INTENDENTE["room_id"],
            "months": 6,
            "monthly_rent_eur": 450.0,
            "rent_total_eur": 2700.0,
            "deposit_eur": 450.0,
            "admin_fee_eur": 95.0,
            "grand_total_eur": 3245.0,
        },
        duration_ms=180,
    )
    cost_bairro = _tool_call(
        hop_index=1,
        name="compute_total_cost",
        input_payload={"room_id": _ROOM_BAIRROALTO["room_id"], "months": 6},
        output_payload={
            "room_id": _ROOM_BAIRROALTO["room_id"],
            "months": 6,
            "monthly_rent_eur": 395.0,
            "rent_total_eur": 2370.0,
            "deposit_eur": 395.0,
            "admin_fee_eur": 95.0,
            "grand_total_eur": 2860.0,
        },
        duration_ms=170,
    )
    final = (
        "For a 6-month stay, here is the total cost for each Intendente-area "
        "option I found:\n\n"
        "- **Intendente Charm** — €3,245 total (€2,700 rent + €450 deposit "
        "+ €95 admin fee).\n"
        "- **Bairro Alto Studios** — €2,860 total (€2,370 rent + €395 deposit "
        "+ €95 admin fee).\n\n"
        "Note that the deposit is refundable at the end of the stay."
    )
    return _assemble(
        query=query,
        final_message=final,
        tool_trace=[rooms_call, cost_intendente, cost_bairro],
        total_duration_ms=1850,
    )


def _response_alfama_quiet(query: str) -> AgentResponse:
    """Q4: what students say about how quiet Alfama is at night."""
    hits = [
        {
            "text": (
                "Alfama is one of the quieter neighbourhoods in central Lisbon. "
                "The narrow streets keep traffic out and most bars close by "
                "midnight."
            ),
            "score": 0.91,
            "source_id": "review_001",
            "metadata": {
                "flatname": "Alfama Heights",
                "zone": "Centro",
                "city": "Lisbon",
                "overall_rating": 5,
            },
        },
        {
            "text": (
                "I rented a room near Largo do Chafariz and could sleep with "
                "the window open even on weekends — the area really does "
                "wind down after 11 pm."
            ),
            "score": 0.87,
            "source_id": "review_002",
            "metadata": {
                "flatname": "Casa do Limoeiro",
                "zone": "Centro",
                "city": "Lisbon",
                "overall_rating": 4,
            },
        },
        {
            "text": (
                "There is some occasional tourist noise during fado-house "
                "hours, but compared to Bairro Alto it is silent."
            ),
            "score": 0.82,
            "source_id": "review_003",
            "metadata": {
                "flatname": "Alfama Heights",
                "zone": "Centro",
                "city": "Lisbon",
                "overall_rating": 4,
            },
        },
    ]
    output = {
        "hits": hits,
        "total_hits": 3,
        "corpus": "reviews",
        "query_used": "Alfama quiet at night",
    }
    call = _tool_call(
        hop_index=0,
        name="search_reviews",
        input_payload={"query": "Alfama quiet at night", "city": "Lisbon", "top_k": 5},
        output_payload=output,
        duration_ms=410,
    )
    final = (
        "Students generally describe Alfama as quiet at night, especially "
        "compared to Bairro Alto. Several reviews mention being able to "
        "sleep with windows open, with bars typically winding down by "
        "midnight. The main exception is some occasional noise from fado "
        "houses on weekend evenings."
    )
    return _assemble(query=query, final_message=final, tool_trace=[call], total_duration_ms=1020)


def _response_generic(query: str) -> AgentResponse:
    """Catch-all: two rooms via find_rooms."""
    output = {
        "rooms": [_ROOM_INTENDENTE, _ROOM_BAIRROALTO],
        "total_matches": 2,
        "query_summary": "Top Lisbon picks for your query",
    }
    call = _tool_call(
        hop_index=0,
        name="find_rooms",
        input_payload={"query": query, "top_k": 5},
        output_payload=output,
        duration_ms=350,
    )
    final = (
        "Here are a couple of Lisbon rooms that might match what you're "
        "looking for. Tell me more about your dates, budget, or preferred "
        "neighbourhood and I can narrow it down."
    )
    return _assemble(query=query, final_message=final, tool_trace=[call], total_duration_ms=900)


# Public dispatch

_RESPONSE_MAP = {
    "find rooms in lisbon available from september 2026": _response_lisbon_september,
    "what is the cancellation policy and deposit refund?": _response_cancellation_policy,
    "what is the total cost for a 6-month stay in intendente?": _response_total_cost_intendente,
    "what do students say about how quiet alfama is at night?": _response_alfama_quiet,
}


def mock_run_agent_turn(
    query: str,
    ctx: Any = None,
    *,
    conversation_history: list[ConversationTurn] | None = None,
    **_: Any,
) -> AgentResponse:
    """Drop-in replacement for ``run_agent_turn`` (no API call).

    Extra keyword arguments accepted by the real function (``on_text``,
    ``on_tool_call``, ``llm``, ``synthesis_llm``, ...) are silently
    swallowed by ``**_`` so the call site doesn't need to branch.
    """
    key = " ".join(query.strip().lower().split())
    builder = _RESPONSE_MAP.get(key, _response_generic)
    return builder(query)
