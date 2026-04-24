"""
Chat view: the 2-column result screen (mockups #2–#4).

Left column: chat header + bubbles + bottom input.
Right column: results header + scrollable property cards.
"""
from __future__ import annotations

import streamlit as st

from elh_rag.schemas import RAGResponse
from elh_rag.ui.components import chat_panel, results_panel


def render(
    response: RAGResponse,
) -> tuple[bool, str, st.delta_generator.DeltaGenerator]:
    """Render the chat view. Returns (submitted, question, loading_slot)."""
    col_left, col_right = st.columns([1, 1], gap="small")

    with col_left:
        chat_panel.render_history()
        submitted, question, loading_slot = chat_panel.render_input()

    with col_right:
        results_panel.render(response)

    return submitted, question, loading_slot