"""Descoberta de binários e versões. Nenhuma lógica de domínio."""
from __future__ import annotations

import shutil
import subprocess

from ..config import Settings
from ..names import BRIDGE_CLI, SOLVER_CLI


def find_bridge(settings: Settings) -> str | None:
    """Caminho do executável do bridge (NOVOMODELO_MCP_BRIDGE_BIN tem prioridade)."""
    return settings.bridge_bin or shutil.which(BRIDGE_CLI)


def find_cobre(settings: Settings) -> str | None:
    """Caminho do executável do solver (NOVOMODELO_MCP_SOLVER_BIN tem prioridade)."""
    return settings.solver_bin or shutil.which(SOLVER_CLI)


def tool_version(binpath: str | None) -> str | None:
    """Primeira linha da versão do binário, ou None se indisponível.

    Tenta `--version` (bridge) e, se falhar, o subcomando `version`
    (o CLI do solver expõe a versão como subcomando, não como flag).
    """
    if not binpath:
        return None
    for args in (["--version"], ["version"]):
        try:
            proc = subprocess.run(
                [binpath, *args], capture_output=True, text=True, timeout=15
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode == 0:
            out = (proc.stdout or proc.stderr or "").strip()
            if out:
                return out.splitlines()[0]
    return None
