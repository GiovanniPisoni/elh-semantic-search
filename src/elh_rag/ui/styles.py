"""
CSS loader for the Streamlit UI.

Reads `.css` files from the `assets/` directory and injects them into the
page via a single `<style>` block. This keeps Python code free of CSS.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

_ASSETS_DIR = Path(__file__).parent / "assets"


def _read_css(name: str) -> str:
    """Read a CSS file from the assets directory."""
    path = _ASSETS_DIR / f"{name}.css"
    return path.read_text(encoding="utf-8")


def inject(*names: str) -> None:
    """Concatenate and inject one or more CSS files into the page."""
    combined = "\n".join(_read_css(n) for n in names)
    st.markdown(f"<style>{combined}</style>", unsafe_allow_html=True)
