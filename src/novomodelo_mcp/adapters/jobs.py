"""Execução assíncrona de comandos longos (ex.: `novomodelo run`): estado, logs, cancelamento.

Multiplataforma (Windows, macOS, Linux) e independente do processo do servidor:
cada job é supervisionado por `_job_runner.py`, lançado DESTACADO (nova sessão
no POSIX; novo grupo sem console no Windows). O servidor controla o runner por
arquivos na pasta do job (sinal só no último recurso) e nunca usa `os.kill(pid, 0)`
(que no Windows MATA):

  <state_dir>/jobs/<job_id>/
    job.json     metadados (comando, caminhos, horários)
    stdout.log   stderr.log
    saida.log    os dois canais na ordem de chegada (o stderr marcado `[stderr] `)
    heartbeat    tocado pelo runner a cada ~2 s  -> liveness
    cancel       pedido de cancelamento          -> runner encerra a árvore
    exit_code    gravado pelo runner no fim      -> estado final

O estado sobrevive a restart do servidor. Sem regra de domínio.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..config import Settings
from . import _job_runner
from .state import atomic_write_text, file_lock, state_dir
from .subproc import NO_WINDOW

#: Jobs terminados há mais que isto são removidos ao iniciar um novo job.
KEEP_DAYS = 7
#: Heartbeat mais velho que isto (sem exit_code) => runner morreu ("lost").
STALE_S = max(15.0, 5 * _job_runner.HEARTBEAT_S)
#: Espera máxima para o runner sair depois de gravar o exit_code.
REAP_TIMEOUT_S = 5.0

_WIN = sys.platform == "win32"
_RUNNER = str(Path(_job_runner.__file__).resolve())
_JOB_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")

#: Runners lançados por ESTE servidor: estado autoritativo + colheita (sem zumbis).
_PROCS: dict[str, subprocess.Popen] = {}


def jobs_root(settings: Settings) -> Path:
    root = state_dir(settings) / "jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def valid_job_id(job_id: str) -> bool:
    return bool(_JOB_ID_RE.match(job_id or ""))


def _job_dir(settings: Settings, job_id: str) -> Path:
    return jobs_root(settings) / job_id


def read_meta(settings: Settings, job_id: str) -> dict[str, Any] | None:
    if not valid_job_id(job_id):
        return None
    try:
        meta = json.loads((_job_dir(settings, job_id) / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # Gravação interrompida ou edição à mão: um job sem o mínimo não pode travar os outros.
    if not isinstance(meta, dict) or not isinstance(meta.get("started_at"), int | float):
        return None
    return meta


def update_meta(settings: Settings, job_id: str, **fields: Any) -> None:
    meta = read_meta(settings, job_id)
    if meta is not None:
        meta.update(fields)
        atomic_write_text(_job_dir(settings, job_id) / "job.json",
                          json.dumps(meta, indent=2, ensure_ascii=False))


def _exit_code(d: Path) -> int | None:
    try:
        return int((d / "exit_code").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _mtime(p: Path) -> float | None:
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def job_state(settings: Settings, job_id: str) -> dict[str, Any] | None:
    """Estado atual: running | succeeded | failed | cancelled | lost."""
    meta = read_meta(settings, job_id)
    if meta is None:
        return None
    d = _job_dir(settings, job_id)
    rc = _exit_code(d)
    proc = _PROCS.get(job_id)
    if proc is not None and rc is not None:
        # O runner grava exit_code ANTES de sair: sem esta espera, um estado terminal
        # conviveria com o runner ainda segurando stdout/stderr.log — no Windows a
        # pasta do run não pode ser movida/apagada nessa janela.
        try:
            proc.wait(timeout=REAP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            pass
    own_alive = proc is not None and proc.poll() is None
    if proc is not None and not own_alive:
        _PROCS.pop(job_id, None)
    cancelled = (d / "cancel").exists()
    beat = _mtime(d / "heartbeat")
    if rc is not None:
        state = "cancelled" if cancelled else ("succeeded" if rc == 0 else "failed")
        end = _mtime(d / "exit_code")
    elif own_alive or (beat is not None and time.time() - beat < STALE_S) \
            or (beat is None and time.time() - meta["started_at"] < STALE_S):
        state, end = "running", None
    else:
        state = "cancelled" if cancelled else "lost"
        end = beat
    elapsed = (end or time.time()) - meta["started_at"]
    return {"job_id": job_id, "state": state, "exit_code": rc,
            "elapsed_seconds": round(max(0.0, elapsed), 1), **meta}


def list_jobs(settings: Settings) -> list[dict[str, Any]]:
    out = []
    for d in sorted(jobs_root(settings).iterdir()):
        if d.is_dir() and valid_job_id(d.name) and (st := job_state(settings, d.name)):
            out.append(st)
    return out


def running_jobs(settings: Settings) -> list[dict[str, Any]]:
    return [j for j in list_jobs(settings) if j["state"] == "running"]


def prune_jobs(settings: Settings, keep_days: float = KEEP_DAYS) -> list[str]:
    """Remove pastas de jobs TERMINADOS mais antigos que `keep_days`."""
    cutoff = time.time() - keep_days * 86400
    removed = []
    for j in list_jobs(settings):
        if j["state"] != "running" and j["started_at"] < cutoff:
            shutil.rmtree(_job_dir(settings, j["job_id"]), ignore_errors=True)
            removed.append(j["job_id"])
    return removed


def _spawn_kwargs() -> dict[str, Any]:
    if _WIN:
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP          # type: ignore[attr-defined]
                 | subprocess.CREATE_NO_WINDOW)               # type: ignore[attr-defined]
        return {"creationflags": flags}
    return {"start_new_session": True}


def start_job(settings: Settings, cmd: list[str], *, info: dict[str, Any] | None = None,
              max_running: int | None = None, cwd: str | None = None) -> dict[str, Any]:
    """Lança `cmd` em background e devolve os metadados do job na hora.

    `max_running`: recusa (RuntimeError) se já houver esse nº de jobs rodando. A
    checagem + lançamento é atômica entre processos (vários clientes MCP).
    """
    root = jobs_root(settings)
    with file_lock(root / ".start.lock"):
        if max_running is not None:
            busy = running_jobs(settings)
            if len(busy) >= max_running:
                raise RuntimeError(", ".join(j["job_id"] for j in busy))
        job_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
        d = root / job_id
        d.mkdir(parents=True)
        meta = {"job_id": job_id, "cmd": cmd, "started_at": time.time(),
                "job_dir": str(d), **(info or {})}
        atomic_write_text(d / "job.json", json.dumps(meta, indent=2, ensure_ascii=False))
        with open(d / "stdout.log", "wb") as out, open(d / "stderr.log", "wb") as err:
            # argv em lista e sem shell: os caminhos do agente chegam como argumentos
            # literais (absolutos, já validados pelo guard em tools.run), nunca interpretados.
            proc = subprocess.Popen([sys.executable, _RUNNER, str(d), *cmd],  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                                    stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                    cwd=cwd, **_spawn_kwargs())
        _PROCS[job_id] = proc
        update_meta(settings, job_id, pid=proc.pid)
    return {**meta, "pid": proc.pid}


def _tail(path: Path, lines: int, max_chars: int) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - max_chars * 4))
            text = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])[-max_chars:]


def job_logs(settings: Settings, job_id: str, *, lines: int = 100,
             max_chars: int = 20000) -> dict[str, Any] | None:
    if read_meta(settings, job_id) is None:
        return None
    d = _job_dir(settings, job_id)
    if (d / "saida.log").exists():
        return {"saida": _tail(d / "saida.log", lines, max_chars)}
    return {"stdout": _tail(d / "stdout.log", lines, max_chars),
            "stderr": _tail(d / "stderr.log", lines, max_chars)}


def job_stderr(settings: Settings, job_id: str, *, lines: int = 20,
               max_chars: int = 20000) -> str | None:
    """Só o stderr do run: os erros e avisos do novomodelo, em qualquer versão."""
    if read_meta(settings, job_id) is None:
        return None
    return _tail(_job_dir(settings, job_id) / "stderr.log", lines, max_chars)


def _force_kill_runner(pid: int, child_pid: int | None = None) -> None:
    """Último recurso, se o runner não responde: derruba o runner E a árvore dele."""
    if _WIN:
        subprocess.run([_job_runner._taskkill(), "/T", "/F", "/PID", str(int(pid))],  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                       capture_output=True, check=False, **NO_WINDOW)
        return
    # O runner e o comando lideram cada um a própria sessão.
    for leader in (pid, child_pid):
        if leader:
            try:
                os.killpg(int(leader), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def cancel_job(settings: Settings, job_id: str) -> dict[str, Any] | None:
    """Pede cancelamento ao runner (arquivo `cancel`) e espera ele encerrar a árvore."""
    st = job_state(settings, job_id)
    if st is None or st["state"] != "running":
        return st
    d = _job_dir(settings, job_id)
    (d / "cancel").touch()
    update_meta(settings, job_id, cancelled_at=time.time())
    deadline = time.time() + _job_runner.GRACE_S + 2 * _job_runner.HEARTBEAT_S + 2
    while time.time() < deadline:
        if _exit_code(d) is not None:
            break
        time.sleep(0.1)
    else:
        if st.get("pid"):
            child = (d / "child_pid").read_text(encoding="utf-8").strip() if (d / "child_pid").exists() else ""
            _force_kill_runner(st["pid"], int(child) if child.isdigit() else None)
    proc = _PROCS.get(job_id)
    if proc is not None:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    return job_state(settings, job_id)
