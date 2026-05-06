"""
Chat panel (left column of the chat view).

Shows the conversation history as bubbles, plus a fixed input at the
bottom for follow-up questions.
"""

from __future__ import annotations

import html as _html

import streamlit as st

from elh_rag.ui import state
from elh_rag.ui.state import ChatMessage

_AI_AVATAR_SVG = """\
<svg width="14" height="14" viewBox="0 0 24 24" fill="none">
  <path d="M3 10.5L12 3L21 10.5V20C21 20.55 20.55 21 20 21H15V15H9V21H4C3.45 21 3 20.55 3 20V10.5Z"
        stroke="#1D4ED8" stroke-width="1.8" stroke-linejoin="round"/>
</svg>"""

_USER_AVATAR_CHAR = "&#128100;"


def _render_bubble(message: ChatMessage) -> str:
    """Render a single chat bubble as an HTML fragment."""
    if message.role == "user":
        content = _html.escape(message.content)
        return (
            '<div class="bubble-row-user">'
            f'<div class="bubble-user">{content}</div>'
            f'<div class="avatar-user">{_USER_AVATAR_CHAR}</div>'
            "</div>"
        )

    content = _html.escape(message.content).replace("\n", "<br>")
    return (
        '<div class="bubble-row-ai">'
        f'<div class="avatar-ai">{_AI_AVATAR_SVG}</div>'
        f'<div class="bubble-ai">{content}</div>'
        "</div>"
    )


def render_history() -> None:
    """Render the header and the full chat history."""
    history = state.get_chat_history()
    bubbles = "".join(_render_bubble(m) for m in history)

    st.markdown(
        f"""
<div class="chat-left-root">
  <div class="chat-left-header">
    <div class="chat-left-header-title">ErASKmus AI</div>
    <div class="chat-left-header-sub">Your personal housing assistant</div>
  </div>
  <div class="chat-left-bubbles">
    {bubbles}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_input() -> tuple[bool, str, st.delta_generator.DeltaGenerator]:
    """Render the fixed bottom input and return (submitted, question, loading_slot)."""
    loading_slot = st.empty()

    with st.form(key="chat_form", clear_on_submit=True):
        q_col, clear_col, btn_col = st.columns([10, 1, 1])
        with q_col:
            question = st.text_input(
                "question",
                value=state.consume_prefill(),
                placeholder="Ask another question...",
                label_visibility="collapsed",
            )
        with clear_col:
            clear_clicked = st.form_submit_button(
                "↻",
                use_container_width=True,
                help="Clear the conversation and start fresh",
            )
        with btn_col:
            submitted = st.form_submit_button("➤", type="primary", use_container_width=True)

    if state.consume_auto_submit():
        submitted = True

    if clear_clicked:
        state.clear_conversation()
        st.rerun()

    return submitted, question, loading_slot
