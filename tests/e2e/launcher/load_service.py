"""Serviço das cargas disparadas pela UI (estado consultável por polling).

O motor (``tests.e2e.load.run``) roda num subprocesso próprio, não numa thread do
launcher: o cancelamento é matar uma única árvore (motor + os N servidores MCP, ou
no modo agent os N CLIs de agente com os seus servidores, sem depender de um
desligamento limpo de cada um) e a medição não disputa o event loop do HTTP. O motor
imprime eventos JSON em linhas; o launcher só os lê. Fechar o stdin do motor
(launcher encerrado) o faz parar sozinho.

Cada carga recebe uma ``--work-dir`` criada aqui (pastas das sessões e cópias das
fixtures), apagada depois que a árvore do motor termina: matar o motor no cancelamento não
lhe dá tempo de limpar.
"""

from __future__ import annotations

import collections
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from tests.e2e.launcher.process_tree import ProcessTree
from tests.e2e.launcher.run_gate import RunGate
from tests.e2e.load.agent_engine import AgentLoadConfig
from tests.e2e.load.engine import LoadConfig
from tests.e2e.load.sandbox import remove_tree

__all__ = ["LoadRunService", "LoadRunState", "build_command"]

LoadStatus = Literal["pending", "running", "done", "error", "cancelled"]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FINISHED: frozenset[str] = frozenset({"done", "error", "cancelled"})
_LOG_KEPT = 200
_LOG_SHOWN = 50
_READER_JOIN_S = 3.0
_WORK_DIR_PREFIX = "novomodelo-load-launcher-"


def _agent_arguments(config: AgentLoadConfig) -> list[str]:
    arguments = ["--mode", "agent"]
    if config.provider is not None:
        arguments += ["--provider", config.provider]
    if config.timeout_s is not None:
        arguments += ["--timeout", repr(float(config.timeout_s))]
    selection = config.selection
    if selection.case_id:
        arguments += ["--case", selection.case_id]
    elif selection.group:
        arguments += ["--group", selection.group]
    elif selection.tags:
        arguments += ["--tags", ",".join(selection.tags)]
    return arguments


def build_command(config: LoadConfig | AgentLoadConfig) -> list[str]:
    """Linha de comando do motor para ``config``; só valores já validados entram nela."""
    command = [
        sys.executable,
        "-m",
        "tests.e2e.load.run",
        "--json-progress",
        "--concurrency",
        str(config.concurrency),
        "--duration",
        repr(float(config.duration_s)),
    ]
    if config.iterations is not None:
        command += ["--iterations", str(config.iterations)]
    if isinstance(config, AgentLoadConfig):
        return command + _agent_arguments(config)
    command += ["--timeout", repr(float(config.timeout_s))]
    if config.tools is not None:
        command += ["--tools", ",".join(config.tools)]
    return command


@dataclass
class LoadRunState:
    """Estado de uma carga: ``progress`` é o último instantâneo emitido pelo motor."""

    run_id: str
    config: dict[str, Any]
    status: LoadStatus = "pending"
    load_id: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    started_at: str = ""
    finished_at: str | None = None
    progress: dict[str, Any] | None = None
    log: collections.deque[str] = field(default_factory=lambda: collections.deque(maxlen=_LOG_KEPT))

    def to_dict(self) -> dict[str, Any]:
        progress = self.progress or {}
        return {
            "run_id": self.run_id,
            "status": self.status,
            "phase": progress.get("phase"),
            "config": self.config,
            "load_id": self.load_id,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress": self.progress,
            "log": list(self.log)[-_LOG_SHOWN:],
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


class LoadRunService:
    """Dispara, acompanha e cancela cargas; divide a vaga de "um run por vez" via ``gate``."""

    def __init__(
        self,
        gate: RunGate,
        command_builder: Callable[[LoadConfig | AgentLoadConfig], list[str]] = build_command,
        cwd: Path = _REPO_ROOT,
    ) -> None:
        self._gate = gate
        self._command_builder = command_builder
        self._cwd = cwd
        self._runs: dict[str, LoadRunState] = {}
        self._trees: dict[str, ProcessTree] = {}
        self._lock = threading.Lock()

    def get(self, run_id: str) -> LoadRunState | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [state.to_dict() for state in self._runs.values()]

    def start_run(self, config: LoadConfig | AgentLoadConfig) -> LoadRunState:
        """Cria e dispara uma carga em background.

        Raises:
            RunAlreadyActiveError: Se outro run (de agente ou de carga) está ativo.
        """
        run_id = uuid.uuid4().hex[:12]
        state = LoadRunState(run_id=run_id, config=config.to_dict(), started_at=_now())
        self._gate.acquire(run_id)
        with self._lock:
            self._runs[run_id] = state
        try:
            work_dir = Path(tempfile.mkdtemp(prefix=_WORK_DIR_PREFIX)).resolve()
            command = [*self._command_builder(config), "--work-dir", str(work_dir)]
        except Exception as exc:
            self._fail(state, f"Falha ao preparar a carga: {exc}")
            raise
        threading.Thread(
            target=self._supervise,
            args=(state, command, work_dir),
            name=f"load-{run_id}",
            daemon=True,
        ).start()
        return state

    def cancel(self, run_id: str) -> LoadRunState | None:
        """Mata a árvore do motor (e com ela os agentes e servidores); nada é gravado.

        Idempotente: num run já encerrado devolve o estado sem mudar nada.
        """
        with self._lock:
            state = self._runs.get(run_id)
            if state is None or state.status in _FINISHED:
                return state
            state.cancel_requested = True
            state.log.append("Parada solicitada.")
            tree = self._trees.get(run_id)
        if tree is not None:
            tree.kill()
        return state

    def _supervise(self, state: LoadRunState, command: list[str], work_dir: Path) -> None:
        try:
            process = self._spawn(state, command)
            if process is None:
                return
            reader = threading.Thread(target=self._read_events, args=(state, process), daemon=True)
            reader.start()
            code = process.wait()
            reader.join(timeout=_READER_JOIN_S)
            self._close_streams(process, reader)
            self._finish(state, code)
        except Exception as exc:  # noqa: BLE001 - qualquer falha do supervisor vira estado "error"
            self._fail(state, f"Falha ao supervisionar a carga: {exc}")
        finally:
            with self._lock:
                tree = self._trees.pop(state.run_id, None)
            if tree is not None:
                tree.close()
            if not remove_tree(work_dir):
                with self._lock:
                    state.log.append(f"Pasta temporária não apagada: {work_dir}")
            self._gate.release(state.run_id)

    @staticmethod
    def _close_streams(process: subprocess.Popen[str], reader: threading.Thread) -> None:
        # Fechar o stdout com o leitor ainda preso nele bloqueia: um descendente
        # órfão pode segurar o pipe. A thread é daemon e termina quando o pipe fechar.
        streams = [process.stdin] if reader.is_alive() else [process.stdin, process.stdout]
        for stream in streams:
            if stream is not None:
                with contextlib.suppress(OSError):
                    stream.close()

    def _spawn(self, state: LoadRunState, command: list[str]) -> subprocess.Popen[str] | None:
        with self._lock:
            if state.cancel_requested:
                self._set_terminal(state, "cancelled", "Parada antes de iniciar; nada foi gravado.")
                return None
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self._cwd,
                env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
                start_new_session=os.name != "nt",
            )
            self._trees[state.run_id] = ProcessTree(process)
            state.status = "running"
            state.log.append("Carga iniciada.")
        return process

    def _read_events(self, state: LoadRunState, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue
            event = self._parse_event(line)
            with self._lock:
                if event is None:
                    state.log.append(line[:300])
                else:
                    self._apply_event(state, event)

    @staticmethod
    def _parse_event(line: str) -> dict[str, Any] | None:
        if not line.startswith("{"):
            return None
        try:
            data = json.loads(line)
        except ValueError:
            return None
        return data if isinstance(data, dict) and "event" in data else None

    @staticmethod
    def _apply_event(state: LoadRunState, event: dict[str, Any]) -> None:
        kind = event.pop("event")
        if kind == "progress":
            state.progress = event
        elif kind == "saved":
            state.load_id = event.get("load_id")
            state.log.append(f"Carga gravada: {state.load_id}")
        elif kind == "error":
            state.error = str(event.get("message", "erro desconhecido"))
            state.log.append(f"ERRO: {state.error}")

    def _finish(self, state: LoadRunState, code: int) -> None:
        with self._lock:
            if state.cancel_requested:
                self._set_terminal(state, "cancelled", "Parada pedida; carga não gravada.")
            elif code == 0 and state.load_id:
                self._set_terminal(state, "done", None)
            else:
                state.error = state.error or f"o motor de carga encerrou com código {code}"
                self._set_terminal(state, "error", None)

    def _fail(self, state: LoadRunState, message: str) -> None:
        with self._lock:
            state.error = message
            self._set_terminal(state, "error", f"ERRO: {message}")

    def _set_terminal(self, state: LoadRunState, status: LoadStatus, note: str | None) -> None:
        """Marca o fim do run e libera a vaga; chamar com ``self._lock`` já tomado."""
        state.status = status
        state.finished_at = _now()
        if note:
            state.log.append(note)
        self._gate.release(state.run_id)
