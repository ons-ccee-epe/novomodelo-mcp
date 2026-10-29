"""Caso sem a fonte declarada em ``requires`` é pulado sem disparar o agente."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.e2e.launcher import service as service_mod
from tests.e2e.launcher.service import RunService, RunState
from tests.e2e.queries.models import ExpectedResult, QueryTestCase


def test_case_without_source_is_skipped_and_agent_not_started(tmp_path) -> None:
    case = QueryTestCase(
        id="bridge-convert-newave",
        query="q",
        expected=ExpectedResult(uses_mcp=True, tool="bridge_convert_newave"),
        requires=(str(tmp_path / "newave-caso-reduzido"),),
    )
    runner = MagicMock()
    store = MagicMock()
    svc = RunService()

    with (
        patch.object(service_mod, "ProviderQueryRunner", return_value=runner),
        patch.object(service_mod, "QueryValidator", MagicMock),
        patch.object(service_mod, "ResultStore", return_value=store),
        patch.object(RunService, "load_cases", return_value=[case]),
    ):
        provider = SimpleNamespace(id="kiro-cli", label="Kiro CLI")
        state = RunState(run_id="r1", provider=provider.id)
        svc._execute(state, provider, None, None, None)  # type: ignore[arg-type]

    assert state.status == "done"
    runner.execute.assert_not_called()
    assert [r["status"] for r in state.results] == ["skip"]
    assert "Fonte ausente" in state.results[0]["error_message"]
    [saved] = store.create_batch.call_args.args
    assert [r.status for r in saved] == ["skip"]
