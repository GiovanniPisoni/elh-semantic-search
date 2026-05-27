"""
Typed wrapper around Streamlit's `st.session_state`.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from elh_rag.agent._models import AgentResponse, ConversationTurn
from elh_rag.config import settings


@dataclass(slots=True)
class ChatMessage:
    """One bubble in the UI chat history."""

    role: str  # "user" | "assistant"
    content: str
    response: AgentResponse | None = None


_DEFAULTS: dict[str, object] = {
    "last_response": None,
    "chat_history": [],
    "conversation_history": [],
    "scroll_to_latest": False,
    "force_chat_view": False,
}


def init() -> None:
    """Initialise session state with default values (idempotent).

    Mutable defaults (lists, dicts) are copied so every init() yields
    a fresh instance — assigning the module-level ``_DEFAULTS["chat_history"]``
    list directly would alias it into session_state, and subsequent
    ``record_query`` ``.append`` calls would mutate the module-level
    default. Then a Home-click → full-purge → init() cycle would assign
    that already-populated list back into session_state, leaking the
    prior conversation into what should be a fresh chat.
    """
    for key, value in _DEFAULTS.items():
        if key not in st.session_state:
            if isinstance(value, list):
                st.session_state[key] = list(value)
            elif isinstance(value, dict):
                st.session_state[key] = dict(value)
            else:
                st.session_state[key] = value


def has_response() -> bool:
    """True if at least one query has been answered."""
    return st.session_state.get("last_response") is not None


def get_last_response() -> AgentResponse | None:
    """Return the most recent AgentResponse, if any."""
    return st.session_state.get("last_response")


def get_chat_history() -> list[ChatMessage]:
    """Return the full UI chat history."""
    return list(st.session_state.get("chat_history", []))


def get_conversation_history() -> list[ConversationTurn]:
    """Return the agent-facing conversation history (capped, FIFO)."""
    return list(st.session_state.get("conversation_history", []))


def record_query(question: str, response: AgentResponse) -> None:
    """Persist a new Q&A turn into the session state."""
    st.session_state["last_response"] = response

    history: list[ChatMessage] = st.session_state.get("chat_history", [])
    history.append(ChatMessage(role="user", content=question))
    history.append(ChatMessage(role="assistant", content=response.final_message, response=response))
    st.session_state["chat_history"] = history

    convo: list[ConversationTurn] = st.session_state.get("conversation_history", [])
    convo.append(ConversationTurn(role="user", content=question))
    convo.append(ConversationTurn(role="assistant", content=response.final_message))
    cap = settings.agent_max_history_turns
    if len(convo) > cap:
        convo = convo[-cap:]
    st.session_state["conversation_history"] = convo


def start_new_chat() -> None:
    """Clear the conversation but stay in the chat view with an empty form."""
    st.session_state["chat_history"] = []
    st.session_state["conversation_history"] = []
    st.session_state["last_response"] = None
    st.session_state["scroll_to_latest"] = False
    st.session_state["force_chat_view"] = True


def should_show_chat_view() -> bool:
    """True if we have a response OR the user explicitly started a new chat."""
    return has_response() or bool(st.session_state.get("force_chat_view", False))


def request_scroll_to_latest() -> None:
    """Flag that the next render should scroll the latest user bubble into view."""
    st.session_state["scroll_to_latest"] = True


def consume_scroll_to_latest() -> bool:
    """Return the scroll flag and clear it."""
    flag = bool(st.session_state.get("scroll_to_latest", False))
    if flag:
        st.session_state["scroll_to_latest"] = False
    return flag
