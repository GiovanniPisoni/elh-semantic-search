"""
Chat panel (left column of the chat view).
"""

from __future__ import annotations

import html as _html
import re

import streamlit as st

from elh_rag.ui import state
from elh_rag.ui.state import ChatMessage

_AVATAR_USER = "🧑"
_AVATAR_AI = "🤖"


def header_html() -> str:
    """Return the left-column header markup."""
    return (
        '<div class="col-header">'
        '<div class="col-header-title">ErASKmus AI</div>'
        '<div class="col-header-sub">Your personal housing assistant</div>'
        "</div>"
    )


def bubbles_html() -> str:
    """Return the scrollable chat-bubble area as HTML."""
    messages: list[ChatMessage] = state.get_chat_history()
    if not messages:
        return '<div class="col-scroll"></div>'

    last_user_idx = -1
    for i, msg in enumerate(messages):
        if msg.role == "user":
            last_user_idx = i

    parts: list[str] = ['<div class="col-scroll">']
    for i, msg in enumerate(messages):
        if msg.role == "user":
            anchor = '<a id="latest-question"></a>' if i == last_user_idx else ""
            parts.append(
                f"{anchor}"
                '<div class="bubble-row-user">'
                f'<div class="bubble-user">{_html.escape(msg.content)}</div>'
                f'<div class="avatar avatar-user">{_AVATAR_USER}</div>'
                "</div>"
            )
        else:
            body = _md_to_html(msg.content)
            parts.append(
                '<div class="bubble-row-ai">'
                f'<div class="avatar avatar-ai">{_AVATAR_AI}</div>'
                f'<div class="bubble-ai">{body}</div>'
                "</div>"
            )
    parts.append("</div>")
    return "".join(parts)


def _md_to_html(text: str) -> str:
    """Escape, then handle **bold**, leading '- ' bullets, and newlines."""
    escaped = _html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"^- ", "• ", escaped, flags=re.MULTILINE)
    return escaped.replace("\n", "<br>")


def render_input() -> tuple[bool, str]:
    """Render the Streamlit form. Returns ``(submitted, question)``."""
    with st.form(key="chat_input_form", clear_on_submit=True):
        col_input, col_submit = st.columns([10, 1])
        with col_input:
            question = st.text_input(
                "question",
                label_visibility="collapsed",
                placeholder="Ask anything about ELH housing...",
            )
        with col_submit:
            submitted = st.form_submit_button("➤")
    return submitted, (question or "").strip()
