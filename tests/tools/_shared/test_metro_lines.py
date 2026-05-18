"""Tests for the static metro line mapping."""

from __future__ import annotations

import pytest

from elh_rag.tools._shared.metro_lines import (
    ALL_METRO_LINE_INPUTS,
    ALL_METRO_LINES,
    LISBON_ZONE_TO_LINES,
    PORTO_LETTER_TO_COLOUR,
    PORTO_ZONE_TO_LINES,
    is_served_by_metro,
    lines_for_zone,
    normalize_line,
    zones_on_line,
)

# Sanity checks on the data


class TestDataIntegrity:
    def test_all_metro_lines_constant(self):
        assert ALL_METRO_LINES == ("blue", "yellow", "green", "red", "violet", "orange")

    def test_lisbon_uses_only_4_colours(self):
        """Lisbon network has 4 lines: blue, yellow, green, red.
        It must NEVER use violet or orange."""
        forbidden = {"violet", "orange"}
        for zone, lines in LISBON_ZONE_TO_LINES.items():
            assert not (set(lines) & forbidden), (
                f"Lisbon zone {zone!r} has forbidden lines: {set(lines) & forbidden}"
            )

    def test_porto_uses_only_known_colours(self):
        """Porto can use any of the 6 colours."""
        for zone, lines in PORTO_ZONE_TO_LINES.items():
            assert all(line in ALL_METRO_LINES for line in lines), (
                f"Porto zone {zone!r} has unknown line: {lines}"
            )

    def test_no_duplicate_lines_per_zone(self):
        """A zone shouldn't be listed under the same line twice."""
        for zone, lines in LISBON_ZONE_TO_LINES.items():
            assert len(lines) == len(set(lines)), f"Duplicate in Lisbon {zone}: {lines}"
        for zone, lines in PORTO_ZONE_TO_LINES.items():
            assert len(lines) == len(set(lines)), f"Duplicate in Porto {zone}: {lines}"


# lines_for_zone()


class TestLinesForZone:
    def test_lisbon_chiado_has_blue_and_green(self):
        result = lines_for_zone("Lisbon", "Chiado")
        assert result == ["blue", "green"]

    def test_lisbon_belem_not_served(self):
        """Belém is famously not served by metro."""
        assert lines_for_zone("Lisbon", "Belem") == []

    def test_lisbon_graca_not_served(self):
        """Graça also not served — only tram 28."""
        assert lines_for_zone("Lisbon", "Graca") == []

    def test_lisbon_estrela_not_served(self):
        assert lines_for_zone("Lisbon", "Estrela") == []

    def test_porto_boavista_is_a_hub(self):
        """Boavista has the Casa da Música interchange, served by 5 lines."""
        result = lines_for_zone("Porto", "Boavista")
        assert set(result) == {"blue", "red", "green", "violet", "orange"}

    def test_porto_ribeira_not_served(self):
        """Ribeira is the historic riverfront, no direct metro stop."""
        assert lines_for_zone("Porto", "Ribeira") == []

    def test_porto_paranhos_only_yellow_and_violet(self):
        result = lines_for_zone("Porto", "Paranhos")
        assert sorted(result) == ["violet", "yellow"]

    def test_unknown_city_returns_empty(self):
        assert lines_for_zone("Berlin", "Mitte") == []

    def test_unknown_zone_returns_empty(self):
        """We don't raise on unknown — we treat unknown as 'no metro'."""
        assert lines_for_zone("Lisbon", "Atlantis") == []

    def test_case_insensitive_city(self):
        assert lines_for_zone("LISBON", "Chiado") == ["blue", "green"]
        assert lines_for_zone("lisbon", "Chiado") == ["blue", "green"]

    def test_zone_case_must_match(self):
        """Zone matching is case-sensitive (DB stores with title case)."""
        # 'chiado' (lowercase) should NOT match 'Chiado'
        assert lines_for_zone("Lisbon", "chiado") == []

    def test_neighborhood_fallback_lisbon(self):
        """Telheiras is in NEIGHBORHOOD_TO_LINES, not in ZONE_TO_LINES.
        The function must fall back to the neighborhood mapping."""
        assert lines_for_zone("Lisbon", "Telheiras") == ["green"]

    def test_neighborhood_fallback_porto(self):
        """Foz is the short form of Foz do Douro; both should resolve correctly."""
        assert lines_for_zone("Porto", "Foz") == []
        assert lines_for_zone("Porto", "Foz do Douro") == []

    def test_results_are_sorted(self):
        """The returned list is always sorted (deterministic for SQL building)."""
        # Boavista: 5 lines, must come back in alphabetical order
        result = lines_for_zone("Porto", "Boavista")
        assert result == sorted(result)

    def test_empty_inputs(self):
        assert lines_for_zone("", "") == []
        assert lines_for_zone("Lisbon", "") == []
        assert lines_for_zone("", "Chiado") == []


# zones_on_line() — inverse lookup


class TestZonesOnLine:
    def test_lisbon_yellow_line_zones(self):
        result = zones_on_line("Lisbon", "yellow")
        assert "Principe Real" in result

    def test_lisbon_green_line_includes_central_zones(self):
        result = zones_on_line("Lisbon", "green")
        # Areas explicitly mapped to green
        for expected in ["Mouraria", "Intendente", "Anjos", "Arroios", "Alvalade"]:
            assert expected in result, f"{expected} should be on green line"

    def test_porto_orange_line(self):
        result = zones_on_line("Porto", "orange")
        # Boavista and Bonfim explicitly include orange
        assert "Boavista" in result
        assert "Bonfim" in result

    def test_unknown_line_returns_empty(self):
        assert zones_on_line("Lisbon", "purple") == []

    def test_unknown_city_returns_empty(self):
        assert zones_on_line("Berlin", "blue") == []

    def test_lisbon_violet_returns_empty(self):
        """Lisbon doesn't have a violet line."""
        assert zones_on_line("Lisbon", "violet") == []

    def test_results_are_sorted(self):
        result = zones_on_line("Lisbon", "green")
        assert result == sorted(result)

    def test_case_insensitive_line(self):
        assert zones_on_line("Lisbon", "GREEN") == zones_on_line("Lisbon", "green")


# is_served_by_metro()


class TestIsServedByMetro:
    @pytest.mark.parametrize(
        "city,zone",
        [
            ("Lisbon", "Chiado"),
            ("Lisbon", "Alvalade"),
            ("Lisbon", "Parque das Nacoes"),
            ("Porto", "Boavista"),
            ("Porto", "Cedofeita"),
            ("Porto", "Bonfim"),
        ],
    )
    def test_served(self, city, zone):
        assert is_served_by_metro(city, zone) is True

    @pytest.mark.parametrize(
        "city,zone",
        [
            ("Lisbon", "Belem"),
            ("Lisbon", "Graca"),
            ("Lisbon", "Estrela"),
            ("Porto", "Ribeira"),
            ("Porto", "Foz do Douro"),
            ("Porto", "Massarelos"),
        ],
    )
    def test_not_served(self, city, zone):
        assert is_served_by_metro(city, zone) is False

    def test_unknown_zone(self):
        assert is_served_by_metro("Lisbon", "Atlantis") is False


# normalize_line() — accepts colours and Porto letters


class TestNormalizeLine:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("blue", "blue"),
            ("BLUE", "blue"),
            ("Blue", "blue"),
            ("green", "green"),
            ("yellow", "yellow"),
            ("red", "red"),
            ("violet", "violet"),
            ("orange", "orange"),
        ],
    )
    def test_colour_passes_through(self, inp, expected):
        assert normalize_line(inp) == expected

    @pytest.mark.parametrize(
        "letter,colour",
        [
            ("A", "blue"),
            ("B", "red"),
            ("C", "green"),
            ("D", "yellow"),
            ("E", "violet"),
            ("F", "orange"),
        ],
    )
    def test_porto_letter_maps_to_colour(self, letter, colour):
        assert normalize_line(letter) == colour

    def test_lowercase_letter_also_works(self):
        """Letters case-insensitive too."""
        assert normalize_line("a") == "blue"
        assert normalize_line("f") == "orange"

    def test_with_whitespace(self):
        assert normalize_line("  green  ") == "green"
        assert normalize_line("  A  ") == "blue"

    def test_unknown_returns_empty(self):
        assert normalize_line("purple") == ""
        assert normalize_line("X") == ""
        assert normalize_line("") == ""

    def test_non_string_returns_empty(self):
        assert normalize_line(None) == ""  # type: ignore[arg-type]
        assert normalize_line(1) == ""  # type: ignore[arg-type]

    def test_porto_letter_mapping_is_complete(self):
        """All 6 Porto letters must map to valid colours."""
        assert set(PORTO_LETTER_TO_COLOUR.keys()) == set("ABCDEF")
        for colour in PORTO_LETTER_TO_COLOUR.values():
            assert colour in ALL_METRO_LINES

    def test_all_metro_line_inputs_includes_letters_and_colours(self):
        """The exposed input set must be 6 colours + 6 letters = 12."""
        assert len(ALL_METRO_LINE_INPUTS) == 12
        assert set(ALL_METRO_LINE_INPUTS) == (set(ALL_METRO_LINES) | set("ABCDEF"))
