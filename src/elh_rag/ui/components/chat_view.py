"""
Chat view — custom HTML grid layout.

Replaces the previous ``st.columns()`` based layout. The entire 2-column
chat surface is emitted as a single ``st.markdown()`` blob; only the
form (input + submit) is a real Streamlit widget. CSS (chat.css §8)
position: fixed-positions the form at the bottom-left of the viewport
to visually occupy the .form-slot in the left column.

This sidesteps Streamlit 1.57's emotion-cache-class layer that was
overriding our CSS rules on ``[data-testid="stColumn"]``.
"""

from __future__ import annotations

import streamlit as st

from elh_rag.agent._models import AgentResponse
from elh_rag.ui.components import chat_panel, results_panel


def render(response: AgentResponse | None) -> tuple[bool, str]:
    """Render the chat view. Returns ``(submitted, question)``."""
    cards = results_panel.extract_cards(response)

    layout_html = (
        '<div class="chat-grid">'
        '<div class="chat-col chat-col-left">'
        '<div class="nav-buttons">'
        '<form method="get" action="" style="display:inline; margin:0;">'
        '<input type="hidden" name="action" value="home"/>'
        '<button type="submit" class="nav-btn" title="Back to welcome">🏠</button>'
        '</form>'
        '<form method="get" action="" style="display:inline; margin:0;">'
        '<input type="hidden" name="action" value="new_chat"/>'
        '<button type="submit" class="nav-btn" title="New chat">➕</button>'
        '</form>'
        '</div>'
        f"{chat_panel.header_html()}"
        f"{chat_panel.bubbles_html()}"
        '<div class="form-slot"></div>'
        "</div>"
        '<div class="chat-col chat-col-right">'
        f"{results_panel.header_html(len(cards))}"
        f"{results_panel.body_html(cards)}"
        f"{results_panel.footer_html()}"
        "</div>"
        "</div>"
    )
    st.markdown(layout_html, unsafe_allow_html=True)

    return chat_panel.render_input()
