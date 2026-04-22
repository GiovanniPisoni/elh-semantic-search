"""
Property card component: renders a single retrieved source as an ELH listing.
"""
from __future__ import annotations

import html as _html

from elh_rag.schemas import RetrievalResult


_PRICE_POOL = [350, 380, 420, 450, 490, 520, 390, 410, 460, 505]
_ROOMS_POOL = [1, 1, 1, 2, 2, 3]
_BATHS_POOL = [1, 1, 2]

_HOUSE_ICON_SVG = """\
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M3 10.5L12 3L21 10.5V20C21 20.55 20.55 21 20 21H15V15H9V21H4C3.45 21 3 20.55 3 20V10.5Z"
        stroke="#1D4ED8" stroke-width="1.6" stroke-linejoin="round" fill="#DBEAFE"/>
</svg>"""

_PIN_ICON_SVG = """\
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5
           a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z" fill="currentColor"/>
</svg>"""

_BED_ICON_SVG = """\
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M2 11v8h2v-2h16v2h2v-5a3 3 0 0 0-3-3H2zm4-5a3 3 0 0 0-3 3v1h8V9a3 3 0 0 0-3-3H6z"
        fill="currentColor"/>
</svg>"""

_BATH_ICON_SVG = """\
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M7 3a3 3 0 0 0-3 3v6H2v2a4 4 0 0 0 2 3.46V19a1 1 0 0 0 2 0v-1h12v1a1 1 0 0 0
           2 0v-1.54A4 4 0 0 0 22 14v-2h-2V6a3 3 0 0 0-5.83-1h-.17L13 6h-2V5a1 1 0 0 0-1-1H9a1
           1 0 0 0-1 1v1H6V6a1 1 0 0 1 1-1h1V3H7z" fill="currentColor"/>
</svg>"""


def _pick(pool: list[int], seed: str) -> int:
    """Deterministically pick an item from a pool based on a string seed."""
    if not seed:
        return pool[0]
    idx = sum(ord(c) for c in seed) % len(pool)
    return pool[idx]


def render(result: RetrievalResult) -> str:
    """Return the HTML for a single property card."""
    meta = result.metadata

    flatname = getattr(meta, "flatname", "")
    roomname = getattr(meta, "roomname", "")
    title_raw = " — ".join(filter(None, [flatname, roomname])) or "ELH Property"
    title = _html.escape(title_raw)

    zone = getattr(meta, "zone", "")
    location_raw = ", ".join(filter(None, [zone, meta.city])) or "Lisbon"
    location = _html.escape(location_raw)

    review_text = getattr(meta, "review_text_original", "")
    desc_raw = (review_text or result.text or "").strip()
    desc = _html.escape(desc_raw[:140]) + ("…" if len(desc_raw) > 140 else "")

    seed = meta.id or title_raw
    price = _pick(_PRICE_POOL, seed)
    rooms = _pick(_ROOMS_POOL, seed)
    baths = _pick(_BATHS_POOL, seed)

    return f"""
<div class="prop-card">
  <div class="prop-img-wrap">
    <div class="prop-img-placeholder">{_HOUSE_ICON_SVG}</div>
    <div class="prop-price-badge">€ {price}/month</div>
  </div>
  <div class="prop-body">
    <div class="prop-title">{title}</div>
    <div class="prop-loc">{_PIN_ICON_SVG}{location}</div>
    <div class="prop-desc">{desc}</div>
    <div class="prop-separator"></div>
    <div class="prop-meta">
      <span class="prop-meta-item">{_BED_ICON_SVG}{rooms} bed</span>
      <span class="prop-meta-item">{_BATH_ICON_SVG}{baths} bath</span>
    </div>
  </div>
</div>
"""