"""Testes do serviço de cargas do launcher: ciclo de vida, cancelamento e a trava compartilhada."""
from __future__ import annotations

import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.e2e.launcher import service as service_mod
from tests.e2e.launcher.load_service import LoadRunService, build_command
from tests.e2e.launcher.run_gate import RunAlreadyActiveError, RunGate
from tests.e2e.launcher.service import RunService
from tests.e2e.load.engine import LoadConfig

CONFIG = LoadConfig(concurrency=2, duration_s=5, tools=("docs_list", "deck_list"), timeout_s=30)

# Motor falso: emite eventos no formato do motor real e termina como ele terminaria.
_COMPLETES = """
import json, sys
print(json.dumps({"event": "progress", "phase": "running", "elapsed_seconds": 1.0,
                  "calls": 10, "p95_ms": 12.5, "series": []}), flush=True)
print("ruído de stderr que não é JSON", flush=True)
print(json.dumps({"event": "saved", "load_id": "20261024_100000_abc1234"}), flush=True)
"""

_FAILS = """
import json, sys
print(json.dumps({"event": "error", "message": "o servidor MCP não iniciou: x"}), flush=True)
sys.exit(1)
"""

_CRASHES_SILENTLY = "import sys; sys.exit(4)"

# O motor real tem o servidor como filho: o neto prova que a árvore inteira morre.
_SPAWNS_CHILD_AND_WAITS = """
import json, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
print(json.dumps({"event": "progress", "phase": "running", "child_pid": child.pid}), flush=True)
time.sleep(120)
"""


def _service(script: str, gate: RunGate | None = None) -> LoadRunService:
    return LoadRunService(
        gate or RunGate(), command_builder=lambda _config: [sys.executable, "-c", script]
    )


def _wait_until(predicate, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=False
        ).stdout
        return str(pid) in out
    try:
        import os

        os.kill(pid, 0)
    except OSError:
        return False
    return True


class TestBuildCommand:
    def test_command_carries_only_validated_values(self) -> None:
        command = build_command(CONFIG)
        assert command[:3] == [sys.executable, "-m", "tests.e2e.load.run"]
        assert "--json-progress" in command
        assert command[command.index("--concurrency") + 1] == "2"
        assert command[command.index("--duration") + 1] == "5.0"
        assert command[command.index("--timeout") + 1] == "30.0"
        assert command[command.index("--tools") + 1] == "docs_list,deck_list"
        assert "--iterations" not in command

    def test_iterations_and_all_tools_default(self) -> None:
        command = build_command(LoadConfig(concurrency=1, duration_s=3, iterations=7))
        assert command[command.index("--iterations") + 1] == "7"
        assert "--tools" not in command


class TestLifecycle:
    def test_a_completed_load_publishes_progress_and_the_saved_id(self) -> None:
        gate = RunGate()
        svc = _service(_COMPLETES, gate)

        state = svc.start_run(CONFIG)
        assert _wait_until(lambda: state.status == "done")

        view = state.to_dict()
        assert view["load_id"] == "20261024_100000_abc1234"
        assert view["progress"]["calls"] == 10
        assert view["phase"] == "running"
        assert view["config"]["concurrency"] == 2
        assert view["finished_at"]
        assert any("ruído" in line for line in view["log"])
        assert gate.owner is None

    def test_an_engine_error_becomes_an_error_state_with_its_message(self) -> None:
        svc = _service(_FAILS)
        state = svc.start_run(CONFIG)
        assert _wait_until(lambda: state.status == "error")
        assert state.error == "o servidor MCP não iniciou: x"
        assert state.load_id is None

    def test_a_silent_crash_reports_the_exit_code(self) -> None:
        svc = _service(_CRASHES_SILENTLY)
        state = svc.start_run(CONFIG)
        assert _wait_until(lambda: state.status == "error")
        assert "código 4" in state.error

    def test_the_run_is_listed_and_retrievable(self) -> None:
        svc = _service(_COMPLETES)
        state = svc.start_run(CONFIG)
        assert svc.get(state.run_id) is state
        assert [r["run_id"] for r in svc.list()] == [state.run_id]
        assert svc.get("nao-existe") is None
        assert _wait_until(lambda: state.status == "done")


class TestCancel:
    def test_cancel_kills_the_engine_and_its_whole_process_tree_and_frees_the_slot(self) -> None:
        gate = RunGate()
        svc = _service(_SPAWNS_CHILD_AND_WAITS, gate)
        state = svc.start_run(CONFIG)
        assert _wait_until(lambda: (state.progress or {}).get("child_pid"))
        child_pid = state.progress["child_pid"]
        assert _pid_alive(child_pid)

        started = time.monotonic()
        svc.cancel(state.run_id)
        assert _wait_until(lambda: state.status == "cancelled")

        assert time.monotonic() - started < 20
        assert _wait_until(lambda: not _pid_alive(child_pid), timeout=15), "o neto sobrou"
        assert state.load_id is None
        assert gate.owner is None
        assert "não gravada" in state.to_dict()["log"][-1]

    def test_cancel_on_a_finished_run_is_a_noop(self) -> None:
        svc = _service(_COMPLETES)
        state = svc.start_run(CONFIG)
        assert _wait_until(lambda: state.status == "done")

        assert svc.cancel(state.run_id) is state
        assert state.status == "done"
        assert state.cancel_requested is False

    def test_cancel_of_an_unknown_run_returns_none(self) -> None:
        assert _service(_COMPLETES).cancel("nao-existe") is None


class TestSharedGate:
    def test_a_load_is_refused_while_an_agent_run_holds_the_slot(self) -> None:
        gate = RunGate()
        gate.acquire("agente-1")
        with pytest.raises(RunAlreadyActiveError, match="agente-1"):
            _service(_COMPLETES, gate).start_run(CONFIG)

    def test_an_agent_run_is_refused_while_a_load_holds_the_slot(self) -> None:
        gate = RunGate()
        load = _service(_SPAWNS_CHILD_AND_WAITS, gate)
        state = load.start_run(CONFIG)
        try:
            agent = RunService(gate=gate)
            provider = SimpleNamespace(id="kiro-cli", label="Kiro CLI")
            with pytest.raises(RunAlreadyActiveError, match=state.run_id):
                agent.start_run(provider=provider)  # type: ignore[arg-type]
        finally:
            load.cancel(state.run_id)
            assert _wait_until(lambda: state.status == "cancelled")

    def test_a_second_load_is_refused_and_the_slot_returns_after_the_first_ends(self) -> None:
        gate = RunGate()
        svc = _service(_SPAWNS_CHILD_AND_WAITS, gate)
        first = svc.start_run(CONFIG)
        with pytest.raises(RunAlreadyActiveError):
            svc.start_run(CONFIG)
        svc.cancel(first.run_id)
        assert _wait_until(lambda: first.status == "cancelled")

        svc2 = _service(_COMPLETES, gate)
        second = svc2.start_run(CONFIG)
        assert _wait_until(lambda: second.status == "done")

    def test_the_agent_service_frees_the_slot_when_its_run_ends(self) -> None:
        gate = RunGate()
        agent = RunService(gate=gate)
        provider = SimpleNamespace(id="kiro-cli", label="Kiro CLI")
        with patch.object(RunService, "load_cases", return_value=[]):
            state = agent.start_run(provider=provider)  # type: ignore[arg-type]
            assert _wait_until(lambda: state.status == "error")
        assert gate.owner is None
        assert service_mod.RunAlreadyActiveError is RunAlreadyActiveError
