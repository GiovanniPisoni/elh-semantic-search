"""AST-based guardrail: no PII-bearing table may appear in Tool 5 SQL.

Decision D6.2 of the Phase 3 agent design.

Tool 5 (``get_booking_stats``) is restricted by GDPR to aggregate reads
over four tables only: ``reservation``, ``house``, ``room``, ``review``.
Five tables are explicitly off-limits because they contain or reference
personally identifiable information.

If this test fails:

1. The new SQL legitimately needs the forbidden table. That is a
   deliberate GDPR-relevant change, not a test bypass. Discuss with
   the team and update the Phase 3 design doc before allowlisting.

2. The match is a false positive — for example, an English string
   containing the word "users" in a non-SQL context. Reword the string
   or extend the allowlist with a narrowly-scoped exception.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

FORBIDDEN_TABLES: tuple[str, ...] = (
    "users",
    "payment",
    "email",
    "question",
    "reply",
)


_EXCLUDED_FILES: frozenset[str] = frozenset({"_safety.py"})


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = PROJECT_ROOT / "src" / "elh_rag" / "tools" / "get_booking_stats"


def _collect_docstring_node_ids(tree: ast.AST) -> set[int]:
    """Identify the ast.Constant nodes that are docstrings."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _iter_string_literals(tree: ast.AST):
    """Yield (lineno, text) for every str literal except docstrings.

    Covers:
      - plain string constants (``"..."``)
      - the literal text parts of f-strings (``f"SELECT FROM ..."``)
    """
    docstring_ids = _collect_docstring_node_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_ids:
                continue
            yield node.lineno, node.value
        elif isinstance(node, ast.JoinedStr):
            # f-string literal parts (ast.Constant inside JoinedStr.values)
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    yield part.lineno, part.value


def _scan_file(py_file: Path) -> list[tuple[str, int, str]]:
    """Return list of (table, lineno, snippet) violations in ``py_file``."""
    source = py_file.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_file))
    violations: list[tuple[str, int, str]] = []
    for lineno, text in _iter_string_literals(tree):
        for table in FORBIDDEN_TABLES:
            if re.search(rf"\b{re.escape(table)}\b", text, re.IGNORECASE):
                snippet = text.strip().replace("\n", " ")[:80]
                violations.append((table, lineno, snippet))
    return violations


def test_no_pii_table_references_in_get_booking_stats() -> None:
    """No forbidden PII table may appear in get_booking_stats source code."""
    py_files = sorted(f for f in PACKAGE_DIR.rglob("*.py") if f.name not in _EXCLUDED_FILES)
    assert py_files, f"No Python files found under {PACKAGE_DIR}"

    all_violations: list[str] = []
    for py_file in py_files:
        for table, lineno, snippet in _scan_file(py_file):
            rel = py_file.relative_to(PROJECT_ROOT)
            all_violations.append(f"  {rel}:{lineno}  table='{table}'  literal={snippet!r}")

    if all_violations:
        message = [
            "Forbidden PII table references found in get_booking_stats:",
            *all_violations,
            "",
            "Tool 5 is restricted by GDPR to aggregate-only reads over "
            "reservation/house/room/review (Phase 3 design decision D3.9). "
            "If a new metric legitimately requires one of these tables, "
            "that is a GDPR-relevant change requiring design review — "
            "do not bypass this test without team discussion.",
        ]
        pytest.fail("\n".join(message))


def test_pii_guard_actually_detects_violations(tmp_path: Path) -> None:
    """Meta-test: confirm the guard fires on synthetic violating code."""
    bad_file = tmp_path / "bad_module.py"
    bad_file.write_text(
        'SQL = "SELECT u.name FROM users u JOIN reservation r ON r.user_id = u.id"\n',
        encoding="utf-8",
    )
    violations = _scan_file(bad_file)
    assert violations, "guard failed to detect 'users' in a SELECT statement"
    tables_found = {v[0] for v in violations}
    assert "users" in tables_found


def test_pii_guard_ignores_docstrings(tmp_path: Path) -> None:
    """Meta-test: prose in module docstrings about 'users' must not trip."""
    ok_file = tmp_path / "ok_module.py"
    ok_file.write_text(
        '"""This module returns aggregates for end-users without PII."""\n'
        'SQL = "SELECT COUNT(*) FROM reservation"\n',
        encoding="utf-8",
    )
    violations = _scan_file(ok_file)
    assert violations == [], f"docstring mention should be ignored, got {violations}"


def test_pii_guard_respects_word_boundaries(tmp_path: Path) -> None:
    """Meta-test: identifier-like words (users_count, etc.) must not trip."""
    ok_file = tmp_path / "ok_module.py"
    ok_file.write_text(
        'SQL = "SELECT users_count, external_users FROM reservation"\n',
        encoding="utf-8",
    )
    violations = _scan_file(ok_file)
    assert violations == [], f"compound identifiers should not match \\busers\\b, got {violations}"


def test_pii_guard_catches_fstring_literal_parts(tmp_path: Path) -> None:
    """Meta-test: f-string literal segments must be scanned too."""
    bad_file = tmp_path / "bad_module.py"
    bad_file.write_text(
        'col = "x"\nSQL = f"SELECT {col} FROM payment p JOIN reservation r ON r.id = p.r_id"\n',
        encoding="utf-8",
    )
    violations = _scan_file(bad_file)
    assert violations, "guard failed to detect 'payment' in an f-string literal"
    tables_found = {v[0] for v in violations}
    assert "payment" in tables_found
