"""Tests for ``elh_rag.tools._kanon``."""

from __future__ import annotations

from dataclasses import dataclass

from elh_rag.tools.get_booking_stats import K_THRESHOLD, filter_by_k_anonymity


@dataclass
class _Stub:
    """Minimal object with a sample_size attribute."""

    label: str
    sample_size: int


class TestKAnonymityFilter:
    def test_threshold_constant_is_five(self):
        """The phase3.md GDPR commitment pins k=5."""
        assert K_THRESHOLD == 5

    def test_empty_input(self):
        kept, suppressed = filter_by_k_anonymity([])
        assert kept == []
        assert suppressed == 0

    def test_all_kept_when_above_threshold(self):
        points = [_Stub("a", 10), _Stub("b", 5), _Stub("c", 100)]
        kept, suppressed = filter_by_k_anonymity(points)
        assert kept == points
        assert suppressed == 0

    def test_all_suppressed_when_below_threshold(self):
        points = [_Stub("a", 4), _Stub("b", 1), _Stub("c", 0)]
        kept, suppressed = filter_by_k_anonymity(points)
        assert kept == []
        assert suppressed == 3

    def test_mixed_keeps_above_threshold_drops_below(self):
        points = [
            _Stub("safe1", 10),
            _Stub("unsafe1", 4),
            _Stub("safe2", 5),  # boundary: kept
            _Stub("unsafe2", 3),
        ]
        kept, suppressed = filter_by_k_anonymity(points)
        labels = [p.label for p in kept]
        assert labels == ["safe1", "safe2"]
        assert suppressed == 2

    def test_threshold_boundary_inclusive(self):
        """``sample_size == K_THRESHOLD`` is kept, not suppressed."""
        points = [_Stub("at_threshold", K_THRESHOLD)]
        kept, suppressed = filter_by_k_anonymity(points)
        assert len(kept) == 1
        assert suppressed == 0

    def test_custom_threshold(self):
        points = [_Stub("a", 8), _Stub("b", 12), _Stub("c", 20)]
        kept, suppressed = filter_by_k_anonymity(points, threshold=10)
        assert len(kept) == 2
        assert suppressed == 1
        assert {p.label for p in kept} == {"b", "c"}

    def test_object_without_sample_size_defaults_to_zero(self):
        """Defensive: a malformed object without the attr is suppressed."""

        class _NoAttr:
            pass

        points = [_NoAttr(), _Stub("ok", 10)]
        kept, suppressed = filter_by_k_anonymity(points)
        assert len(kept) == 1
        assert suppressed == 1
