"""Motor de carga contra um servidor MCP falso via stdio real (SDK ``mcp``, sem novomodelo).

Novomodelo o que os fakes em processo não alcançam: o transporte stdio de verdade, o
timeout por chamada com recriação do cliente e o encerramento da árvore de
processos do servidor. Pula se o SDK ``mcp`` não está instalado. A carga contra o
servidor real roda só com ``LOAD_E2E_REAL=1``.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import sys
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from novomodelo_mcp_e2e.load import engine
from novomodelo_mcp_e2e.load.client import stdio_client_factory
from novomodelo_mcp_e2e.load.engine import LoadConfig, LoadRunner

FAKE_SERVER = Path(__file__).with_name("fake_mcp_server.py")
TOOLS = ("docs_list", "docs_search", "schema_list")


def _server_processes(marker: str) -> list[str]:
    """Linhas de comando dos processos vivos cujo comando contém ``marker``."""
    if os.name == "nt":
        script = (
            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*"
            + marker
            + "*' -and $_.ProcessId -ne $PID } | ForEach-Object { $_.ProcessId }"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        ).stdout
    else:
        out = subprocess.run(
            ["pgrep", "-f", marker], capture_output=True, text=True, timeout=30, check=False
        ).stdout
    return [line for line in out.splitlines() if line.strip()]


def _runner(marker: str, hang_after: int, **config) -> LoadRunner:
    values: dict[str, Any] = {"concurrency": 2, "duration_s": 3, "tools": TOOLS, "timeout_s": 2.0}
    values.update(config)
    factory = stdio_client_factory(
        sys.executable,
        [str(FAKE_SERVER), f"--marker={marker}"],
        {"FAKE_HANG_AFTER": str(hang_after)},
        open(os.devnull, "w", encoding="utf-8"),
    )
    return LoadRunner(LoadConfig(**values), Path("."), factory)


@pytest.fixture
def marker() -> Iterator[str]:
    value = f"load-it-{uuid.uuid4().hex}"
    yield value
    assert _server_processes(value) == [], "processos do servidor sobraram após a carga"


def test_real_stdio_load_measures_calls_and_leaves_no_server_behind(marker: str) -> None:
    outcome = asyncio.run(_runner(marker, hang_after=0).run())

    assert len(outcome.samples) > 20
    assert {s.outcome for s in outcome.samples} == {"ok"}
    assert {s.tool for s in outcome.samples} == set(TOOLS)
    assert outcome.duration_s >= 3
    initial = [s for s in outcome.startups if s["kind"] == "initial"]
    assert len(initial) == 2 and all(s["ms"] > 0 for s in initial)
    assert max(s.latency_ms for s in outcome.samples) < max(s["ms"] for s in initial)


def test_a_session_that_stops_answering_times_out_and_is_recreated(
    marker: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine, "DRAIN_GRACE_S", 3.0)
    outcome = asyncio.run(
        _runner(marker, hang_after=14, duration_s=4, concurrency=1, timeout_s=1.0).run()
    )

    timeouts = [s for s in outcome.samples if s.outcome == "timeout"]
    respawns = [s for s in outcome.startups if s["kind"] == "respawn"]
    assert timeouts
    assert respawns and all(entry["ok"] for entry in respawns)
    assert any(s.outcome == "ok" for s in outcome.samples)


def test_stopping_mid_run_terminates_every_server_process(marker: str) -> None:
    runner = _runner(marker, hang_after=0, duration_s=60, concurrency=2)
    started = threading.Event()

    def on_progress(snapshot: dict) -> None:
        if snapshot["phase"] == "running" and snapshot["calls"] > 3 and not started.is_set():
            started.set()
            runner.request_stop()

    runner._on_progress = on_progress
    outcome = asyncio.run(runner.run())

    assert outcome.interrupted
    assert outcome.duration_s < 30


def _cli(marker: str, results_dir: Path, extra: list[str]) -> subprocess.Popen:
    server = [sys.executable, str(FAKE_SERVER), f"--marker={marker}"]
    command_line = subprocess.list2cmdline(server) if os.name == "nt" else shlex.join(server)
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "novomodelo_mcp_e2e.load.run",
            "--json-progress",
            "--concurrency",
            "1",
            "--tools",
            ",".join(TOOLS),
            "--timeout",
            "5",
            "--results-dir",
            str(results_dir),
            "--server-command",
            command_line,
            *extra,
        ],
        cwd=Path(__file__).resolve().parents[3],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )


def test_cli_json_mode_end_to_end_writes_the_run_and_reports_events(
    marker: str, tmp_path: Path
) -> None:
    proc = _cli(marker, tmp_path, ["--duration", "2"])
    assert proc.stdin is not None and proc.stdout is not None
    events = [json.loads(line) for line in proc.stdout if line.startswith("{")]
    assert proc.wait(timeout=120) == 0
    proc.stdin.close()

    kinds = [event["event"] for event in events]
    assert kinds[-1] == "saved"
    assert "progress" in kinds
    assert {e["phase"] for e in events if e["event"] == "progress"} >= {"preflight", "running"}
    saved = json.loads(
        (tmp_path / "load" / f"{events[-1]['load_id']}.json").read_text(encoding="utf-8")
    )
    assert saved["totals"]["calls"] > 10
    assert saved["server"]["command"][0] == sys.executable
    assert (tmp_path / "load" / "index.json").exists()


def test_cli_stops_without_saving_when_the_launcher_closes_its_stdin(
    marker: str, tmp_path: Path
) -> None:
    proc = _cli(marker, tmp_path, ["--duration", "60"])
    assert proc.stdin is not None and proc.stdout is not None
    for line in proc.stdout:
        if line.startswith("{") and json.loads(line).get("phase") == "running":
            break
    proc.stdin.close()
    rest = proc.stdout.read()

    assert proc.wait(timeout=120) == 3
    assert '"event": "cancelled"' in rest
    assert not (tmp_path / "load").exists()


@pytest.mark.skipif(os.environ.get("LOAD_E2E_REAL") != "1", reason="defina LOAD_E2E_REAL=1")
def test_real_server_short_load(tmp_path: Path) -> None:
    from novomodelo_mcp_e2e.load.client import default_server_command
    from novomodelo_mcp_e2e.queries.mcp_workspace import WORKSPACE_ENV

    fixtures = Path(__file__).resolve().parent.parent / "fixtures"
    command, args = default_server_command()
    factory = stdio_client_factory(
        command, args, {WORKSPACE_ENV: str(fixtures)}, open(os.devnull, "w", encoding="utf-8")
    )
    config = LoadConfig(
        concurrency=1, duration_s=3, tools=("docs_list", "schema_list"), timeout_s=60
    )
    outcome = asyncio.run(LoadRunner(config, fixtures, factory).run())
    assert outcome.samples
    assert all(s.outcome == "ok" for s in outcome.samples)
