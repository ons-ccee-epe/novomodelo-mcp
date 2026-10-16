"""Runner de job: supervisiona UM comando e registra o resultado na pasta do job.

Executado como script (`python _job_runner.py <job_dir> <cmd...>`), destacado do
servidor — sobrevive a restart/queda do servidor MCP. Stdlib pura; idêntico em
Windows, macOS e Linux (nenhum sinal POSIX é necessário para o controle):

  heartbeat   tocado a cada HEARTBEAT_S enquanto o comando roda (liveness)
  child_pid   PID do comando (diagnóstico)
  cancel      se aparecer, o runner encerra o comando (terminate -> kill após GRACE_S)
  exit_code   gravado atomicamente quando o comando termina
  saida.log   stdout e stderr do comando na ordem de chegada, o stderr marcado
              `[stderr] ` (além de stdout.log e stderr.log, cada canal sozinho)
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HEARTBEAT_S = 2.0
GRACE_S = 10.0
_WIN = sys.platform == "win32"


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    for _ in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: alvo aberto por um leitor
            time.sleep(0.05)
    os.replace(tmp, path)


def _taskkill() -> str:
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")
    return exe if os.path.exists(exe) else "taskkill"


def _kill_tree(proc: subprocess.Popen, *, force: bool) -> None:
    if _WIN:
        # TerminateProcess não alcança netos; taskkill /T derruba a árvore toda.
        subprocess.run([_taskkill(), "/T", "/F", "/PID", str(int(proc.pid))],  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                       capture_output=True, check=False)
    elif force:
        proc.kill()
    else:
        proc.terminate()


STDERR_MARK = b"[stderr] "


def _pump(stream, own, merged, lock: threading.Lock, mark: bytes) -> None:
    for line in iter(stream.readline, b""):
        with lock:
            own.write(line)
            own.flush()
            merged.write(mark + line)
            merged.flush()


def main(argv: list[str]) -> int:
    job_dir, cmd = Path(argv[1]), argv[2:]
    cancel, beat = job_dir / "cancel", job_dir / "heartbeat"

    if not _WIN:
        # Sinal externo (ex.: shutdown) vira pedido de cancelamento ordenado.
        signal.signal(signal.SIGTERM, lambda *_: cancel.touch())

    flags = subprocess.CREATE_NO_WINDOW if _WIN else 0  # type: ignore[attr-defined]
    try:
        # argv em lista e sem shell, montada pelo servidor (tools.run) com caminhos absolutos.
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                                stderr=subprocess.PIPE, creationflags=flags)
    except OSError as exc:
        message = f"runner: falha ao iniciar {cmd[:1]}: {exc}\n".encode()
        sys.stderr.buffer.write(message)
        sys.stderr.flush()
        (job_dir / "saida.log").write_bytes(STDERR_MARK + message)
        _write(job_dir / "exit_code", "127")
        return 127
    _write(job_dir / "child_pid", str(proc.pid))
    merged, lock = open(job_dir / "saida.log", "ab"), threading.Lock()
    pumps = [threading.Thread(target=_pump, args=(proc.stdout, sys.stdout.buffer, merged, lock, b""),
                              daemon=True),
             threading.Thread(target=_pump, args=(proc.stderr, sys.stderr.buffer, merged, lock,
                                                  STDERR_MARK), daemon=True)]
    for pump in pumps:
        pump.start()

    cancel_sent: float | None = None
    while True:
        beat.touch()
        try:
            rc = proc.wait(timeout=HEARTBEAT_S)
            break
        except subprocess.TimeoutExpired:
            pass
        if cancel.exists():
            if cancel_sent is None:
                _kill_tree(proc, force=False)
                cancel_sent = time.monotonic()
            elif time.monotonic() - cancel_sent > GRACE_S:
                _kill_tree(proc, force=True)
    # Um neto que herdou os pipes pode segurá-los abertos: espera pouco e segue.
    for pump in pumps:
        pump.join(timeout=5)
    merged.close()
    _write(job_dir / "exit_code", str(rc))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
