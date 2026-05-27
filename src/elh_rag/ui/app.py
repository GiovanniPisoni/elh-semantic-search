"""
ErASKmus — Streamlit entry point.
"""

from __future__ import annotations

import logging
import os

import streamlit as st
import streamlit.components.v1 as components

from elh_rag.agent._models import AgentResponse
from elh_rag.agent.context import AgentContext
from elh_rag.agent.loop import InputValidationError, run_agent_turn
from elh_rag.ui import state, styles
from elh_rag.ui.components import chat_view, welcome_view

# Page config

st.set_page_config(
    page_title="ErASKmus — ELH AI",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)


USE_MOCK_AGENT = os.environ.get("ELH_USE_MOCK_AGENT", "false").lower() in ("1", "true", "yes")


# Shared resources

@st.cache_resource
def get_agent_context() -> AgentContext:
    """Cached AgentContext — survives across Streamlit reruns."""
    return AgentContext.build()


def run_agent_query(question: str) -> AgentResponse | None:
    """Execute one agent turn, handling input-validation and runtime errors.

    Returns ``None`` on failure; a friendly ``st.error`` is rendered in-place.
    """
    history = state.get_conversation_history()
    try:
        ctx = get_agent_context()
        return run_agent_turn(question, ctx, conversation_history=history)
    except InputValidationError as e:
        st.error(f"Invalid input: {e}")
        return None
    except Exception as e:
        st.error(f"Something went wrong. Please try again. (Details: {type(e).__name__})")
        logging.exception("Agent call failed")
        return None


def _emit_scroll_to_latest() -> None:
    """Bug 3 plumbing: smooth-scroll the latest user bubble into view."""
    if state.consume_scroll_to_latest():
        components.html(
            """<script>
            const el = parent.document.getElementById('latest-question');
            if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
            </script>""",
            height=0,
        )


# Main


def main() -> None:
    state.init()

    action = st.query_params.get("action")
    if action == "home":
        for key in list(st.session_state.keys()):
            del st.session_state[key]

        st.query_params.clear()
        state.init()
        st.rerun()
    elif action == "new_chat":
        state.start_new_chat()
        st.query_params.clear()
        st.rerun()

    styles.inject("base")

    if state.should_show_chat_view():
        styles.inject("chat")
        submitted, question = chat_view.render(state.get_last_response())
    else:
        styles.inject("welcome")
        submitted, question = welcome_view.render()

    if submitted and question.strip():
        with st.spinner("Thinking..."):
            response = run_agent_query(question.strip())
        if response is not None:
            state.record_query(question.strip(), response)
            state.request_scroll_to_latest()
            st.rerun()

    _emit_scroll_to_latest()


if __name__ == "__main__":
    main()
