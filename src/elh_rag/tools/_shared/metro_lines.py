"""Static mapping from ELH zones/neighbourhoods to metro lines.

The DB does not store metro-line membership; we use the curated
mapping here, keyed on the zone/neighbourhood names that appear in
the populateElh dataset (Wikipedia-derived).

Convention:
Lines are named by **colour** (not by Lisbon's traditional names or
Porto's letter codes) for consistency across cities:

    "blue", "yellow", "green", "red", "violet", "orange"

* Lisbon uses only the first four colours.
* Porto's six lines are mapped:
    A → blue
    B → red
    C → green
    D → yellow
    E → violet
    F → orange

A zone may be served by multiple lines; the mapping returns a list.
A zone *not* served by metro (e.g. Belém in Lisbon) returns ``[]``.

Last reviewed: 2026-05-06.
"""

from __future__ import annotations

from typing import Literal

# The canonical line names used internally (and for the static maps below).
MetroLine = Literal["blue", "yellow", "green", "red", "violet", "orange"]

# Internal canonical colours (subset of what users may type).
ALL_METRO_LINES: tuple[str, ...] = (
    "blue",
    "yellow",
    "green",
    "red",
    "violet",
    "orange",
)

# User-facing aliases. Lisbon uses colours; Porto uses letters in
# signage/maps but colours in everyday speech. We accept both.
PORTO_LETTER_TO_COLOUR: dict[str, str] = {
    "A": "blue",
    "B": "red",
    "C": "green",
    "D": "yellow",
    "E": "violet",
    "F": "orange",
}

# Full set of values acceptable in tool inputs (colours + letters).
ALL_METRO_LINE_INPUTS: tuple[str, ...] = (
    "blue",
    "yellow",
    "green",
    "red",
    "violet",
    "orange",
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
)


def normalize_line(raw: str) -> str:
    """Normalize a user-facing line name to the canonical colour."""
    if not isinstance(raw, str):
        return ""
    stripped = raw.strip()
    # Try uppercase letter mapping first (Porto)
    upper = stripped.upper()
    if upper in PORTO_LETTER_TO_COLOUR:
        return PORTO_LETTER_TO_COLOUR[upper]
    # Then try lowercase colour
    lower = stripped.lower()
    if lower in ALL_METRO_LINES:
        return lower
    return ""


# LISBON — 4 lines, 56 stations
#
# Network reference (Wikipedia, 2026):
#   Blue (Linha Azul):     Reboleira ↔ Santa Apolónia (via Marquês de
#                          Pombal, Restauradores, Baixa-Chiado)
#   Yellow (Linha Amarela): Odivelas ↔ Rato (via Saldanha, Marquês de
#                          Pombal, Avenida)
#   Green (Linha Verde):   Telheiras ↔ Cais do Sodré (via Alvalade,
#                          Areeiro, Alameda, Rossio, Baixa-Chiado)
#   Red (Linha Vermelha):  Aeroporto ↔ São Sebastião (via Oriente,
#                          Olaias, Alameda)
#
# Notable absences (zone NOT reached by metro):
#   * Belém (no metro service — tram only)
#   * Bairro Alto (closest station: Baixa-Chiado, requires walking up)
#   * Alfama high part (closest: Santa Apolónia or Martim Moniz)
#   * Mouraria (closest: Martim Moniz on Green)
#   * Graça (no metro, only tram 28)
#   * Estrela (no metro, only tram)
#   * Santos (no metro, but Cais do Sodré nearby on Green)

LISBON_ZONE_TO_LINES: dict[str, list[str]] = {
    # Centre — historic & touristic
    "Alfama": ["blue"],  # Santa Apolónia (low part)
    "Bairro Alto": ["blue", "green"],  # Baixa-Chiado (walking)
    "Chiado": ["blue", "green"],  # Baixa-Chiado direct
    "Mouraria": ["green"],  # Martim Moniz
    "Intendente": ["green"],  # Intendente station
    "Anjos": ["green"],  # Anjos station
    "Arroios": ["green"],  # Arroios station
    "Graca": [],  # not served — tram 28 only
    "Estrela": [],  # not served — tram only
    "Santos": ["green"],  # Cais do Sodré nearby
    # Centre-north
    "Principe Real": ["yellow"],  # Rato station nearby
    "Alvalade": ["green"],  # Alvalade station
    # West / waterfront
    "Belem": [],  # not served by metro
    # East — Expo area
    "Parque das Nacoes": ["red"],  # Oriente station
}

LISBON_NEIGHBORHOOD_TO_LINES: dict[str, list[str]] = {
    "Alcantara": [],  # not served
    "Campo de Ourique": [],  # not served (closest: Rato)
    "Areeiro": ["green"],  # Areeiro station
    "Roma": ["green"],  # Areeiro/Alvalade nearby
    "Telheiras": ["green"],  # Telheiras (terminus)
    "Benfica": ["blue"],  # Colégio Militar / Carnide
}


# PORTO — 6 lines, 82 stations
#
# Network reference (Wikipedia, 2026):
#   A (blue):   Senhor de Matosinhos ↔ Estádio do Dragão
#   B (red):    Póvoa do Varzim ↔ Estádio do Dragão
#   C (green):  ISMAI ↔ Campanhã
#   D (yellow): Hospital São João ↔ Santo Ovídio (the "central" line,
#               crosses the Douro to Vila Nova de Gaia)
#   E (violet): Aeroporto ↔ Estádio do Dragão
#   F (orange): Senhora da Hora ↔ Fânzeres
#
# Key interchanges:
#   Trindade   — A, B, C, E, F (central hub)
#   Casa da Música — A, B, C, E, F (Boavista)
#   Bolhão     — A, B, C, E, F (centre)
#   Campanhã   — A, B, C, E, F (terminus, train station)

PORTO_ZONE_TO_LINES: dict[str, list[str]] = {
    "Ribeira": [],  # not directly served (closest: São Bento, walk)
    "Foz do Douro": [],  # not served by metro (bus only)
    "Cedofeita": ["red", "violet", "orange"],  # Lapa, Carolina Michaelis
    "Boavista": ["blue", "red", "green", "violet", "orange"],  # Casa da Música hub
    "Bonfim": ["blue", "red", "green", "violet", "orange"],  # Heroísmo / Campo 24 Agosto
    "Campanha": ["blue", "red", "green", "violet", "orange"],  # Campanhã terminus
    "Massarelos": [],  # not served (tram only)
    "Paranhos": ["yellow", "violet"],  # Pólo Universitário, Salgueiros
    "Ramalde": ["blue"],  # Ramalde station
}

PORTO_NEIGHBORHOOD_TO_LINES: dict[str, list[str]] = {
    "Miragaia": [],  # not served
    "Foz": [],  # = Foz do Douro
    "Lordelo": [],  # not served
    "Nevogilde": [],  # not served
}


# Public API


def lines_for_zone(city: str, zone: str) -> list[str]:
    """Return the list of metro lines serving a zone in a given city."""
    city_norm = (city or "").strip().lower()
    zone_norm = (zone or "").strip()

    if city_norm == "lisbon":
        lines = LISBON_ZONE_TO_LINES.get(zone_norm)
        if lines is None:
            lines = LISBON_NEIGHBORHOOD_TO_LINES.get(zone_norm, [])
    elif city_norm == "porto":
        lines = PORTO_ZONE_TO_LINES.get(zone_norm)
        if lines is None:
            lines = PORTO_NEIGHBORHOOD_TO_LINES.get(zone_norm, [])
    else:
        return []

    return sorted(lines)


def zones_on_line(city: str, line: str) -> list[str]:
    """Return all zones in ``city`` served by ``line``."""
    line_norm = (line or "").strip().lower()
    if line_norm not in ALL_METRO_LINES:
        return []

    city_norm = (city or "").strip().lower()
    if city_norm == "lisbon":
        zone_map = LISBON_ZONE_TO_LINES
        nhood_map = LISBON_NEIGHBORHOOD_TO_LINES
    elif city_norm == "porto":
        zone_map = PORTO_ZONE_TO_LINES
        nhood_map = PORTO_NEIGHBORHOOD_TO_LINES
    else:
        return []

    matches: set[str] = set()
    for name, lines in zone_map.items():
        if line_norm in lines:
            matches.add(name)
    for name, lines in nhood_map.items():
        if line_norm in lines:
            matches.add(name)
    return sorted(matches)


def is_served_by_metro(city: str, zone: str) -> bool:
    """Return True if ``zone`` in ``city`` is served by at least one metro line."""
    return len(lines_for_zone(city, zone)) > 0
