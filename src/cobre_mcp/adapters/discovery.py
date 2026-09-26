"""Descoberta de binários e versões. Nenhuma lógica de domínio."""
from __future__ import annotations

import shutil
import subprocess

from ..config import Settings


def find_bridge(settings: Settings) -> str | None:
    """Caminho do executável `cobre-bridge` (env COBRE_BRIDGE_BIN tem prioridade)."""
    return settings.bridge_bin or shutil.which("cobre-bridge")


def find_cobre(settings: Settings) -> str | None:
    """Caminho do executável `cobre` (env COBRE_BIN tem prioridade)."""
    return settings.cobre_bin or shutil.which("cobre")


def tool_version(binpath: str | None) -> str | None:
    """Primeira linha da versão do binário, ou None se indisponível.

    Tenta `--version` (cobre-bridge) e, se falhar, o subcomando `version`
    (o CLI do cobre expõe a versão como subcomando, não como flag).
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
