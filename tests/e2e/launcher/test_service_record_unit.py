"""O resultado publicado ao vivo é o mesmo registro gravado na bateria."""

from __future__ import annotations

from dataclasses import asdict

from tests.e2e.launcher.service import RunService, RunState
from tests.e2e.queries.models import ExpectedResult, QueryTestCase, TestResult


def test_record_publishes_the_full_test_result() -> None:
    tr = TestResult(
        test_id="docs-list-all",
        query="Liste as páginas",
        expected_tool="docs_list",
        expected_tools=None,
        actual_tool="docs_list",
        all_tool_calls=[
            {"name": "docs_list", "args": {"__tool_use_purpose": "listar"}, "tool_id": "t1"}
        ],
        status="pass",
        latency_ms=1200.0,
        tool_latency_ms=300.0,
        mcp_used=True,
        correct_tool=True,
        correct_result=True,
        agent_response="x" * 1000,
        error_message=None,
        tags=["docs"],
        validation_checks=[{"name": "uses_mcp", "passed": True, "message": "MCP usado: docs_list"}],
    )
    case = QueryTestCase(
        id="docs-list-all", query="q", expected=ExpectedResult(uses_mcp=True, tool="docs_list")
    )
    state = RunState(run_id="r1", provider="kiro-cli")

    RunService()._record(state, case, tr)

    assert state.completed == 1
    assert state.results == [asdict(tr)]
    assert len(state.results[0]["agent_response"]) == 1000
