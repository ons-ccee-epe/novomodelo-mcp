"""Testes do serviço de cargas do launcher: ciclo de vida, cancelamento e a trava compartilhada."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from novomodelo_mcp_e2e.launcher.load_service import LoadRunService, build_command
from novomodelo_mcp_e2e.launcher.run_gate import RunAlreadyActiveError, RunGate
from novomodelo_mcp_e2e.load.engine import LoadConfig

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

# Motor falso que grava na --work-dir (como a cópia das fixtures) e fica esperando.
_WRITES_IN_WORK_DIR_AND_WAITS = """
import json, pathlib, sys, time
work = pathlib.Path(sys.argv[sys.argv.index("--work-dir") + 1])
(work / "s0" / "fixtures").mkdir(parents=True)
(work / "s0" / "fixtures" / "config.json").write_text("{}")
print(json.dumps({"event": "progress", "phase": "running", "work_dir": str(work)}), flush=True)
time.sleep(120)
"""

_WRITES_IN_WORK_DIR_AND_SAVES = _WRITES_IN_WORK_DIR_AND_WAITS.replace(
    "time.sleep(120)", 'print(json.dumps({"event": "saved", "load_id": "20261024_100000_abc1234"}))'
)


# Motor falso que conta o que herdou do ambiente e cita um caminho absoluto do host.
_REPORTS_ENV_AND_PATH = """
import json, os, sys
nomes = ("CHAVE_FALSA_DO_HOST", "NOVOMODELO_BATERIA_X")
print("herdou=" + ",".join(k for k in nomes if k in os.environ), flush=True)
print("lendo /dados/pessoa/caso/a.json", flush=True)
print(json.dumps({"event": "error", "message": "falhou em /dados/pessoa/caso"}), flush=True)
sys.exit(1)
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
        assert command[:3] == [sys.executable, "-m", "novomodelo_mcp_e2e.load.run"]
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

    def test_engine_gets_only_the_allowed_environment_and_the_log_hides_host_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHAVE_FALSA_DO_HOST", "valor-falso")
        monkeypatch.setenv("NOVOMODELO_BATERIA_X", "1")
        state = _service(_REPORTS_ENV_AND_PATH).start_run(CONFIG)
        assert _wait_until(lambda: state.status == "error")
        view = state.to_dict()
        assert "herdou=NOVOMODELO_BATERIA_X" in view["log"]
        assert "lendo <caminho>" in view["log"]
        assert "/dados/pessoa" not in " ".join(view["log"]) + str(view["error"])

    def test_a_silent_crash_reports_the_exit_code(self) -> None:
        svc = _service(_CRASHES_SILENTLY)
        state = svc.start_run(CONFIG)
        assert _wait_until(lambda: state.status == "error")
        assert state.error is not None
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
        assert state.progress is not None
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

    def test_cancel_removes_the_work_dir_the_engine_could_not_clean(self) -> None:
        svc = _service(_WRITES_IN_WORK_DIR_AND_WAITS)
        state = svc.start_run(CONFIG)
        assert _wait_until(lambda: (state.progress or {}).get("work_dir"))
        assert state.progress is not None
        work_dir = Path(state.progress["work_dir"])
        assert (work_dir / "s0" / "fixtures" / "config.json").is_file()

        svc.cancel(state.run_id)
        assert _wait_until(lambda: state.status == "cancelled")
        assert _wait_until(lambda: not work_dir.exists(), timeout=15), "a pasta do run sobrou"

    def test_a_finished_run_also_leaves_no_work_dir(self) -> None:
        svc = _service(_WRITES_IN_WORK_DIR_AND_SAVES)
        state = svc.start_run(CONFIG)
        assert _wait_until(lambda: state.status == "done")
        assert state.progress is not None
        work_dir = Path(state.progress["work_dir"])
        assert _wait_until(lambda: not work_dir.exists(), timeout=15), "a pasta do run sobrou"

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
