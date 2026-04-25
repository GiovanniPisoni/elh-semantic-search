"""
Typed wrapper around Streamlit's `st.session_state`.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from elh_rag.retrieval.conversation_memory import ConversationMemory
from elh_rag.schemas import RAGResponse


@dataclass(slots=True)
class ChatMessage:
    """One turn of the conversation."""

    role: str  # "user" | "ai"
    content: str


_DEFAULTS: dict[str, object] = {
    "last_response": None,
    "chat_history": [],
    "recent_queries": [],
    "prefill": "",
    "auto_submit": False,
}


def init() -> None:
    """Initialise session state with default values (idempotent)."""
    for key, value in _DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
    
    if "conversation_memory" not in st.session_state:
        st.session_state["conversation_memory"] = ConversationMemory()


def has_response() -> bool:
    """True if at least one query has been answered."""
    return st.session_state.get("last_response") is not None


def get_last_response() -> RAGResponse | None:
    """Return the most recent RAGResponse, if any."""
    return st.session_state.get("last_response")


def get_chat_history() -> list[ChatMessage]:
    """Return the full chat history."""
    return list(st.session_state.get("chat_history", []))


def get_recent_queries() -> list[dict]:
    """Return recently-submitted queries for the sidebar."""
    return list(st.session_state.get("recent_queries", []))


def get_conversation_memory() -> ConversationMemory:
    """Return the per-session ConversationMemory used for follow-up rewriting."""
    memory = st.session_state.get("conversation_memory")
    if memory is None:
        memory = ConversationMemory()
        st.session_state["conversation_memory"] = memory
    return memory


def record_query(question: str, response: RAGResponse) -> None:
    """Persist a new Q&A turn into the session state."""
    st.session_state["last_response"] = response

    history: list[ChatMessage] = st.session_state.get("chat_history", [])
    history.append(ChatMessage(role="user", content=question))
    history.append(ChatMessage(role="ai", content=response.answer))
    st.session_state["chat_history"] = history

    recent: list[dict] = st.session_state.get("recent_queries", [])
    if question not in [r["q"] for r in recent]:
        recent.insert(0, {"q": question, "n": len(response.sources)})
    st.session_state["recent_queries"] = recent[:10]

    memory = get_conversation_memory()
    memory.append(question=question, answer=response.answer)


def clear_conversation() -> None:
    """Reset chat history, last response, and conversation memory."""
    st.session_state["chat_history"] = []
    st.session_state["last_response"] = None
    memory = st.session_state.get("conversation_memory")
    if memory is not None:
        memory.clear()


def consume_prefill() -> str:
    """Return the pending prefill value and clear it from state."""
    value = st.session_state.get("prefill", "")
    if value:
        st.session_state["prefill"] = ""
    return value


def consume_auto_submit() -> bool:
    """Return the pending auto_submit flag and clear it from state."""
    flag = bool(st.session_state.get("auto_submit", False))
    if flag:
        st.session_state["auto_submit"] = False
    return flag


def set_prefill(text: str, auto_submit: bool = False) -> None:
    """Queue a prefill value (with optional auto-submission) for the next run."""
    st.session_state["prefill"] = text
    st.session_state["auto_submit"] = auto_submit