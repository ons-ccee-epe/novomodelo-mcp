"""Descoberta de binários e versões. Nenhuma lógica de domínio."""
from __future__ import annotations

import shutil
import subprocess
import sysconfig
from pathlib import Path

from ..config import Settings
from ..names import BRIDGE_CLI, SOLVER_CLI


def bridge_origin(settings: Settings) -> tuple[str | None, str | None]:
    """(caminho, origem) do bridge: `variavel`, depois `pacote`, depois `path`.

    A variável vem antes do pacote: é o jeito de apontar outro bridge (e o falso
    dos testes) mesmo com o do pacote instalado.
    """
    if settings.bridge_bin:
        return settings.bridge_bin, "variavel"
    if packaged := shutil.which(BRIDGE_CLI, path=sysconfig.get_path("scripts")):
        return packaged, "pacote"
    on_path = shutil.which(BRIDGE_CLI)
    return on_path, "path" if on_path else None


def find_bridge(settings: Settings) -> str | None:
    """Caminho do executável do bridge (ver `bridge_origin`)."""
    return bridge_origin(settings)[0]


def find_novomodelo(settings: Settings) -> str | None:
    """Caminho do executável do solver: NOVOMODELO_MCP_SOLVER_BIN, PATH, `~/.cargo/bin`.

    `~/.cargo/bin` é o destino padrão do instalador oficial: sem ele, o executável
    recém-instalado só seria achado depois de reiniciar o cliente com o PATH novo.
    """
    return (settings.solver_bin or shutil.which(SOLVER_CLI)
            or shutil.which(SOLVER_CLI, path=str(Path.home() / ".cargo" / "bin")))


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
