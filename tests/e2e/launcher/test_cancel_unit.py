"""Testes unitários da parada de runs: RunService.cancel."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.e2e.launcher import service as service_mod
from tests.e2e.launcher.service import RunService, RunState
from tests.e2e.queries.models import ExpectedResult, QueryTestCase, TestResult


def _case(case_id: str) -> QueryTestCase:
    return QueryTestCase(
        id=case_id,
        query="q",
        expected=ExpectedResult(uses_mcp=True, tool="server_info"),
        tags=[],
    )


def _wait_until(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class _BlockingRunner:
    """Runner falso: o 1º caso termina; o 2º bloqueia até cancel()."""

    instances: list[_BlockingRunner] = []

    def __init__(self, **_kwargs) -> None:
        self.release = threading.Event()
        self.executed: list[str] = []
        _BlockingRunner.instances.append(self)

    def execute(self, case: QueryTestCase):
        self.executed.append(case.id)
        if len(self.executed) == 1:
            return SimpleNamespace(status="completed")
        self.release.wait(timeout=10)
        return SimpleNamespace(status="cancelled")

    def cancel(self) -> None:
        self.release.set()

    def close(self) -> None:
        pass


def _fake_test_result(case, _result, _validation):
    return TestResult(
        test_id=case.id,
        query=case.query,
        expected_tool=case.expected.tool,
        expected_tools=None,
        actual_tool=case.expected.tool,
        all_tool_calls=[],
        status="pass",
        latency_ms=1.0,
        tool_latency_ms=None,
        mcp_used=True,
        correct_tool=True,
        correct_result=True,
        agent_response="",
        error_message=None,
        tags=[],
        validation_checks=[],
    )


def test_service_cancel_stops_remaining_cases_and_skips_batch() -> None:
    _BlockingRunner.instances.clear()
    store = MagicMock()
    cases = [_case("c1"), _case("c2"), _case("c3")]
    svc = RunService()

    with (
        patch.object(service_mod, "ProviderQueryRunner", _BlockingRunner),
        patch.object(service_mod, "QueryValidator", MagicMock),
        patch.object(service_mod, "ResultStore", return_value=store),
        patch.object(service_mod, "_build_test_result", _fake_test_result),
        patch.object(RunService, "load_cases", return_value=cases),
    ):
        provider = SimpleNamespace(id="kiro-cli", label="Kiro CLI")
        state = RunState(run_id="r1", provider=provider.id)
        svc._runs[state.run_id] = state
        threading.Thread(
            target=svc._execute, args=(state, provider, None, None, None), daemon=True
        ).start()
        assert _wait_until(lambda: state.current == "c2")

        svc.cancel(state.run_id)
        assert _wait_until(lambda: state.status == "cancelled")

    assert state.completed == 1
    assert [r["test_id"] for r in state.results] == ["c1"]
    assert _BlockingRunner.instances[0].executed == ["c1", "c2"]
    store.save_batch.assert_not_called()
    store.append_metrics.assert_not_called()


def test_service_cancel_on_finished_run_is_a_noop() -> None:
    svc = RunService()
    state = service_mod.RunState(run_id="r1", provider="kiro-cli", status="done")
    svc._runs["r1"] = state

    assert svc.cancel("r1") is state
    assert state.status == "done"
    assert state.cancel_requested is False


def test_service_cancel_unknown_run_returns_none() -> None:
    assert RunService().cancel("nao-existe") is None
