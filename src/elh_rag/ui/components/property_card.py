"""
Property card component.
"""

from __future__ import annotations

import html as _html
from typing import Any

_PRICE_FALLBACK = "—"


def _truncate(text: str, n: int) -> str:
    text = text.strip()
    if len(text) <= n:
        return text
    return text[:n].rstrip() + "…"


def _format_price(value: Any) -> str:
    if value is None:
        return _PRICE_FALLBACK
    try:
        return f"€ {float(value):.0f}/mo"
    except (TypeError, ValueError):
        return _PRICE_FALLBACK


def _format_distance(meters: Any) -> str:
    if meters is None:
        return ""
    try:
        m = int(meters)
    except (TypeError, ValueError):
        return ""
    if m >= 1000:
        return f"{m / 1000:.1f} km"
    return f"{m} m"


def render_property_card(data: dict[str, Any]) -> str:
    """Render a property card. Returns the HTML fragment."""
    title_raw = (
        data.get("room_name") or data.get("house_name") or data.get("flat_name") or "ELH Property"
    )
    title = _html.escape(str(title_raw))

    subtitle_raw = data.get("flat_name") or data.get("house_name") or ""
    subtitle = _html.escape(str(subtitle_raw)) if subtitle_raw and subtitle_raw != title_raw else ""

    loc_parts = [
        str(data.get("neighborhood") or ""),
        str(data.get("zone") or ""),
        str(data.get("city") or ""),
    ]
    location = _html.escape(", ".join(p for p in loc_parts if p)) or "Lisbon"

    description_raw = (
        data.get("excerpt") or data.get("description") or data.get("full_description") or ""
    )
    description = _html.escape(_truncate(str(description_raw), 240))

    price_value = data.get("price_per_month_eur") or data.get("monthly_rent_eur")
    price_str = _format_price(price_value)
    price_label = _html.escape(str(data.get("price_label") or ""))

    bath_label = "Private bath" if bool(data.get("private_bathroom")) else "Shared bath"

    metro_line = str(data.get("nearest_metro_line") or "")
    distance_str = _format_distance(data.get("distance_to_transport_m"))
    if metro_line and distance_str:
        metro_label = _html.escape(f"{metro_line} • {distance_str}")
    elif metro_line:
        metro_label = _html.escape(metro_line)
    elif distance_str:
        metro_label = _html.escape(distance_str)
    else:
        metro_label = ""

    subtitle_html = f'<div class="prop-subtitle">{subtitle}</div>' if subtitle else ""
    description_html = f'<div class="prop-desc">{description}</div>' if description else ""
    price_label_html = f'<div class="prop-price-label">{price_label}</div>' if price_label else ""
    metro_html = (
        f'<span class="prop-meta-item"><span class="prop-icon">🚇</span>{metro_label}</span>'
        if metro_label
        else ""
    )

    return (
        '<div class="prop-card">'
        '<div class="prop-img-wrap">'
        '<div class="prop-img-placeholder"><span class="prop-img-emoji">🏠</span></div>'
        f'<div class="prop-price-badge">{price_str}</div>'
        "</div>"
        '<div class="prop-body">'
        f'<div class="prop-title">{title}</div>'
        f"{subtitle_html}"
        f'<div class="prop-loc"><span class="prop-icon">📍</span>{location}</div>'
        f"{description_html}"
        f"{price_label_html}"
        '<div class="prop-separator"></div>'
        '<div class="prop-meta">'
        f'<span class="prop-meta-item"><span class="prop-icon">🚿</span>{_html.escape(bath_label)}</span>'
        f"{metro_html}"
        "</div>"
        "</div>"
        "</div>"
    )


def render_snippet_card(hit: dict[str, Any], corpus: str) -> str:
    """Render a snippet card from a RAG search hit."""
    text_raw = str(hit.get("text") or "")
    text = _html.escape(_truncate(text_raw, 280))

    score_value = hit.get("score", 0.0)
    try:
        score = float(score_value)
    except (TypeError, ValueError):
        score = 0.0
    score_str = f"{score:.2f}"

    meta = hit.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    loc_parts = [
        str(meta.get("flatname") or ""),
        str(meta.get("zone") or ""),
        str(meta.get("city") or ""),
    ]
    location = _html.escape(", ".join(p for p in loc_parts if p))

    corpus_label = _html.escape(corpus.replace("_", " ").upper())

    location_html = f'<span class="snippet-meta-item">📍 {location}</span>' if location else ""

    return (
        '<div class="snippet-card">'
        f'<div class="snippet-corpus">{corpus_label}</div>'
        f'<div class="snippet-text">"{text}"</div>'
        '<div class="snippet-meta">'
        f"{location_html}"
        f'<span class="snippet-meta-item">Score {score_str}</span>'
        "</div>"
        "</div>"
    )
