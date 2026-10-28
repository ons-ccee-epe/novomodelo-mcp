"""Testes unitários dos pré-requisitos de fonte (requires) dos casos."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.queries.loader import CasesLoader
from tests.e2e.queries.models import ExpectedResult, QueryTestCase, TestResult
from tests.e2e.queries.preconditions import missing_sources, skipped_result
from tests.e2e.queries.store import ResultStore


def _case(requires: tuple[str, ...]) -> QueryTestCase:
    return QueryTestCase(
        id="c1",
        query="q",
        expected=ExpectedResult(uses_mcp=True, tool="bridge_convert_newave"),
        tags=("bridge",),
        requires=requires,
    )


def test_missing_source_is_reported(tmp_path: Path) -> None:
    absent = str(tmp_path / "newave-caso-reduzido")
    assert missing_sources(_case((absent,))) == [absent]


def test_empty_directory_counts_as_missing(tmp_path: Path) -> None:
    empty = tmp_path / "deck"
    empty.mkdir()
    assert missing_sources(_case((str(empty),))) == [str(empty)]


def test_present_directory_and_file_satisfy_requirement(tmp_path: Path) -> None:
    deck = tmp_path / "deck"
    deck.mkdir()
    (deck / "config.json").write_text("{}", encoding="utf-8")
    assert missing_sources(_case((str(deck), str(deck / "config.json")))) == []


def test_case_without_requires_never_skips() -> None:
    assert missing_sources(_case(())) == []


def test_skipped_result_names_the_missing_source(tmp_path: Path) -> None:
    absent = str(tmp_path / "x")
    tr = skipped_result(_case((absent,)), [absent])
    assert tr.status == "skip"
    assert absent in (tr.error_message or "")
    assert tr.mcp_used is False


def test_loader_expands_fixtures_in_requires(tmp_path: Path) -> None:
    cases_yaml = tmp_path / "cases.yaml"
    cases_yaml.write_text(
        "- id: convert\n"
        "  query: Converta {FIXTURES}/newave/deck\n"
        "  requires:\n"
        '    - "{FIXTURES}/newave/deck"\n'
        "  expected:\n"
        "    uses_mcp: true\n"
        "    tool: bridge_convert_newave\n",
        encoding="utf-8",
    )
    fixtures = tmp_path / "fixtures"
    [case] = CasesLoader(cases_yaml, fixtures).load()
    assert case.requires == (f"{fixtures.resolve()}/newave/deck",)


def _result(test_id: str, status: str, mcp_used: bool) -> TestResult:
    return TestResult(
        test_id=test_id,
        query="q",
        expected_tool="deck_list",
        expected_tools=None,
        actual_tool="deck_list" if mcp_used else None,
        all_tool_calls=[],
        status=status,
        latency_ms=100.0,
        tool_latency_ms=None,
        mcp_used=mcp_used,
        correct_tool=mcp_used,
        correct_result=mcp_used,
        agent_response="",
        error_message=None,
        tags=["deck"],
        validation_checks=[],
    )


def test_skipped_cases_count_but_do_not_lower_percentages(tmp_path: Path) -> None:
    store = ResultStore(tmp_path / "results", tmp_path / "metrics")
    batch = store.create_batch([_result("a", "pass", True), _result("b", "skip", False)])

    assert batch.total_tests == 2
    assert batch.skipped == 1
    assert batch.metrics.pct_mcp_used == pytest.approx(100.0)
    assert batch.metrics_by_tag["deck"].total == 1
