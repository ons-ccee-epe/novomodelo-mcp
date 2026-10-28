"""Estado persistente do servidor (jobs, calibração): diretório por plataforma + escrita segura.

Diretório (primeiro que valer):
  NOVOMODELO_MCP_STATE_DIR
  Windows: %LOCALAPPDATA%\\novomodelo-mcp
  macOS:   ~/Library/Application Support/novomodelo-mcp
  Linux:   $XDG_STATE_HOME/novomodelo-mcp  (padrão ~/.local/state/novomodelo-mcp)

Nunca usa o diretório temporário do sistema: ele é limpo pelo SO e o estado dos
runs precisa sobreviver a restarts. Stdlib pura.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..config import Settings

APP = "novomodelo-mcp"


def default_state_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / APP


def state_dir(settings: Settings) -> Path:
    root = Path(settings.state_dir).expanduser() if settings.state_dir else default_state_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root


def atomic_write_text(path: Path, text: str, *, retries: int = 20) -> None:
    """tmp + os.replace. No Windows, `replace` falha se outro processo está lendo o
    alvo naquele instante — repete por um curto período antes de desistir."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == retries - 1:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


@contextmanager
def file_lock(path: Path, *, timeout: float = 10.0, stale_after: float = 60.0) -> Iterator[None]:
    """Lock entre processos por criação exclusiva de arquivo (portável).

    Lock órfão (processo morreu segurando) é quebrado após `stale_after` segundos.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > stale_after:
                    path.unlink(missing_ok=True)
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"lock ocupado: {path}") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)
