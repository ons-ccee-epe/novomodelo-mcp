"""Testes unitários da parada de runs: QueryRunner.cancel e RunService.cancel."""
from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.e2e.launcher import service as service_mod
from tests.e2e.launcher.service import RunService
from tests.e2e.queries.models import ExpectedResult, QueryTestCase, TestResult
from tests.e2e.queries.runner import QueryRunner

# O filho herda os pipes do pai: se só o pai morrer, o communicate fica preso
# até o filho acabar. O teste prova que a árvore inteira é encerrada.
_SPAWNS_CHILD_AND_SLEEPS = (
    "import subprocess, sys, time; "
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
    "time.sleep(60)"
)


def _case(case_id: str) -> QueryTestCase:
    return QueryTestCase(
        id=case_id,
        query="q",
        expected=ExpectedResult(uses_mcp=True, tool="server_info"),
        tags=[],
    )


def _sleeping_runner(timeout_seconds: float = 60) -> QueryRunner:
    with patch.object(QueryRunner, "_validate_kiro_cli"):
        runner = QueryRunner(timeout_seconds=timeout_seconds)
    runner._build_command = lambda query: [sys.executable, "-c", _SPAWNS_CHILD_AND_SLEEPS]  # type: ignore[method-assign]
    return runner


def _wait_until(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_cancel_interrupts_running_query_and_its_children() -> None:
    runner = _sleeping_runner()
    outcome: dict = {}
    worker = threading.Thread(target=lambda: outcome.update(result=runner.execute(_case("c1"))))
    started = time.monotonic()
    worker.start()
    assert _wait_until(lambda: runner._process is not None)

    runner.cancel()
    worker.join(timeout=20)

    assert not worker.is_alive(), "communicate ficou preso: a árvore de processos não foi encerrada"
    assert outcome["result"].status == "cancelled"
    assert time.monotonic() - started < 20


def test_timeout_kills_process_tree_and_reports_timeout() -> None:
    runner = _sleeping_runner(timeout_seconds=1)

    started = time.monotonic()
    result = runner.execute(_case("c1"))

    assert result.status == "timeout"
    assert time.monotonic() - started < 15


def test_cancelled_runner_refuses_next_queries_without_spawning() -> None:
    runner = _sleeping_runner()
    runner.cancel()

    with patch("subprocess.Popen") as popen:
        result = runner.execute(_case("c1"))

    assert result.status == "cancelled"
    popen.assert_not_called()


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
        state = svc.start_run(provider=provider)  # type: ignore[arg-type]
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
