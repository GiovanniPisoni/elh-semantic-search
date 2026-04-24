"""
ErASKmus — Streamlit entry point.
"""
from __future__ import annotations

import time

import streamlit as st
import streamlit.components.v1 as components

from elh_rag.pipeline import RAGPipeline
from elh_rag.schemas import RAGResponse
from elh_rag.ui import state, styles
from elh_rag.ui.animations import DONE_HTML, LOADING_HTML
from elh_rag.ui.components import chat_view, sidebar, welcome_view


# Page config

st.set_page_config(
    page_title="ErASKmus — ELH AI",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# Shared resources


@st.cache_resource
def get_pipeline() -> RAGPipeline:
    """Cached pipeline instance — survives across reruns."""
    return RAGPipeline()


def run_query(
    question: str, filters: sidebar.SidebarFilters
) -> RAGResponse:
    """Execute a single RAG query with the current sidebar filters."""
    return get_pipeline().query(
        question,
        top_k=filters.top_k,
        city_filter=filters.city,
        min_rating=filters.min_rating,
        conversation_memory=state.get_conversation_memory(),
    )


def show_loading_then_done(slot: st.delta_generator.DeltaGenerator) -> None:
    """Show the loading animation for the duration of the given slot."""
    with slot:
        components.html(LOADING_HTML, height=32, scrolling=False)


def show_done(slot: st.delta_generator.DeltaGenerator) -> None:
    with slot:
        components.html(DONE_HTML, height=32, scrolling=False)


# Main


def main() -> None:
    state.init()
    styles.inject("base")

    filters = sidebar.render()

    if state.has_response():
        styles.inject("chat")
        response = state.get_last_response()
        assert response is not None
        submitted, question, loading_slot = chat_view.render(response)
    else:
        styles.inject("welcome")
        submitted, question, loading_slot = welcome_view.render()

    if submitted and question.strip():
        show_loading_then_done(loading_slot)
        response = run_query(question.strip(), filters)
        show_done(loading_slot)
        time.sleep(0.3)
        state.record_query(question.strip(), response)
        st.rerun()


if __name__ == "__main__":
    main()