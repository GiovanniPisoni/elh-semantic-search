"""Tests for ``elh_rag.tools._kb``."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from elh_rag.tools._kb import (
    IndexedEntry,
    KBEntry,
    KBStore,
    _audience_matches,
    _cosine_similarity,
    load_entries,
)

# Helpers


def _entry(
    id: str = "test_1",
    *,
    category: str = "general",
    audience: str = "student",
    canonical: str = "Test question?",
    variants: list[str] | None = None,
    answer: str = "Test answer.",
    sources: list[str] | None = None,
    related: list[str] | None = None,
) -> KBEntry:
    return KBEntry(
        id=id,
        category=category,
        audience=audience,  # type: ignore[arg-type]
        canonical_question=canonical,
        question_variants=variants or [],
        answer=answer,
        sources=sources or [],
        related=related or [],
    )


def _indexed(entry: KBEntry, embeddings: list[list[float]]) -> IndexedEntry:
    return IndexedEntry(entry=entry, variant_embeddings=embeddings)


# Cosine similarity


class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors_score_minus_one(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="length mismatch"):
            _cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


# Audience matcher


class TestAudienceMatches:
    @pytest.mark.parametrize(
        "entry_aud,requested,expected",
        [
            ("student", "student", True),
            ("student", "landlord", False),
            ("student", "both", True),
            ("landlord", "student", False),
            ("landlord", "landlord", True),
            ("landlord", "both", True),
            ("both", "student", True),
            ("both", "landlord", True),
            ("both", "both", True),
        ],
    )
    def test_matching_table(self, entry_aud, requested, expected):
        assert _audience_matches(entry_aud, requested) is expected


# YAML loader


class TestLoadEntries:
    def test_loads_real_kb_yaml(self):
        """The shipped policies.yaml must parse and validate cleanly."""
        entries = load_entries()  # default path
        assert len(entries) >= 20
        # Every entry has at least the canonical question
        for e in entries:
            assert e.id
            assert e.canonical_question
            assert e.answer
            assert e.audience in {"student", "landlord", "both"}

    def test_load_with_explicit_path(self, tmp_path: Path):
        kb_file = tmp_path / "tiny.yaml"
        kb_file.write_text(
            yaml.safe_dump(
                {
                    "entries": [
                        {
                            "id": "x",
                            "category": "test",
                            "audience": "student",
                            "canonical_question": "q?",
                            "answer": "a",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        entries = load_entries(kb_file)
        assert len(entries) == 1
        assert entries[0].id == "x"

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_entries(tmp_path / "nope.yaml")

    def test_malformed_top_level_raises(self, tmp_path: Path):
        kb_file = tmp_path / "bad.yaml"
        kb_file.write_text("just-a-string", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a mapping"):
            load_entries(kb_file)

    def test_entries_not_a_list_raises(self, tmp_path: Path):
        kb_file = tmp_path / "bad.yaml"
        kb_file.write_text(yaml.safe_dump({"entries": "not a list"}), encoding="utf-8")
        with pytest.raises(ValueError, match="'entries' must be a list"):
            load_entries(kb_file)

    def test_dangling_related_ref_warns(self, tmp_path: Path, caplog):
        kb_file = tmp_path / "dangling.yaml"
        kb_file.write_text(
            yaml.safe_dump(
                {
                    "entries": [
                        {
                            "id": "a",
                            "category": "x",
                            "audience": "student",
                            "canonical_question": "q?",
                            "answer": "a",
                            "related": ["nonexistent"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with caplog.at_level("WARNING"):
            load_entries(kb_file)
        assert any("unknown related id" in r.message for r in caplog.records)

    def test_invalid_audience_raises_validation_error(self, tmp_path: Path):
        from pydantic import ValidationError

        kb_file = tmp_path / "bad.yaml"
        kb_file.write_text(
            yaml.safe_dump(
                {
                    "entries": [
                        {
                            "id": "a",
                            "category": "x",
                            "audience": "alien",
                            "canonical_question": "q?",
                            "answer": "a",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValidationError):
            load_entries(kb_file)


# KBStore search


class TestKBStoreSearch:
    def test_finds_match_above_threshold(self):
        # 2 entries with distinctive embeddings
        e1 = _entry(id="cancellation", canonical="cancel?")
        e2 = _entry(id="payment", canonical="pay?")
        store = KBStore(
            [
                _indexed(e1, [[1.0, 0.0, 0.0]]),
                _indexed(e2, [[0.0, 1.0, 0.0]]),
            ]
        )
        results = store.search([1.0, 0.0, 0.0], audience="student", top_k=3, threshold=0.5)
        assert len(results) == 1
        assert results[0][0].id == "cancellation"
        assert results[0][1] == pytest.approx(1.0)

    def test_returns_top_k_sorted_descending(self):
        e1 = _entry(id="a")
        e2 = _entry(id="b")
        e3 = _entry(id="c")
        # Query [1,0]: e1 perfect, e2 angle ~45°, e3 orthogonal
        store = KBStore(
            [
                _indexed(e1, [[1.0, 0.0]]),
                _indexed(e2, [[0.7071, 0.7071]]),  # ~0.707 cosine vs [1,0]
                _indexed(e3, [[0.0, 1.0]]),
            ]
        )
        results = store.search([1.0, 0.0], top_k=2, threshold=0.5)
        assert [r[0].id for r in results] == ["a", "b"]
        # e3 below threshold -> excluded
        assert results[0][1] > results[1][1]

    def test_threshold_filters_low_matches(self):
        e1 = _entry(id="weak")
        store = KBStore([_indexed(e1, [[0.0, 1.0]])])
        # Query orthogonal to entry -> score 0
        results = store.search([1.0, 0.0], threshold=0.5)
        assert results == []

    def test_max_score_across_variants_used(self):
        """If any variant scores high, the entry matches — even if others don't."""
        e1 = _entry(id="multi", variants=["v1", "v2"])
        # 1st variant orthogonal, 2nd perfect
        store = KBStore([_indexed(e1, [[0.0, 1.0], [1.0, 0.0]])])
        results = store.search([1.0, 0.0], threshold=0.5)
        assert len(results) == 1
        assert results[0][1] == pytest.approx(1.0)

    def test_audience_filter_drops_landlord_entries_for_student(self):
        e_student = _entry(id="s", audience="student")
        e_landlord = _entry(id="l", audience="landlord")
        e_both = _entry(id="b", audience="both")
        store = KBStore(
            [
                _indexed(e_student, [[1.0, 0.0]]),
                _indexed(e_landlord, [[1.0, 0.0]]),
                _indexed(e_both, [[1.0, 0.0]]),
            ]
        )
        results = store.search([1.0, 0.0], audience="student", threshold=0.5)
        ids = {r[0].id for r in results}
        assert ids == {"s", "b"}

    def test_audience_both_returns_every_entry(self):
        e_student = _entry(id="s", audience="student")
        e_landlord = _entry(id="l", audience="landlord")
        store = KBStore(
            [
                _indexed(e_student, [[1.0, 0.0]]),
                _indexed(e_landlord, [[1.0, 0.0]]),
            ]
        )
        results = store.search([1.0, 0.0], audience="both", threshold=0.5)
        assert len(results) == 2

    def test_empty_store_returns_empty(self):
        store = KBStore([])
        results = store.search([1.0, 0.0], threshold=0.5)
        assert results == []

    def test_entry_with_no_embeddings_skipped_gracefully(self):
        """Defensive: an entry with empty variant_embeddings should not crash."""
        e = _entry(id="empty")
        store = KBStore([_indexed(e, [])])
        results = store.search([1.0, 0.0], threshold=0.5)
        assert results == []

    def test_get_returns_entry_by_id(self):
        e1 = _entry(id="findme")
        store = KBStore([_indexed(e1, [[1.0]])])
        assert store.get("findme") is e1
        assert store.get("nonexistent") is None

    def test_len_reflects_entry_count(self):
        store = KBStore([_indexed(_entry(id=f"e{i}"), [[1.0]]) for i in range(5)])
        assert len(store) == 5
