"""Descoberta de binários e versões. Nenhuma lógica de domínio."""

from __future__ import annotations

import importlib.metadata as metadata
import shutil
import subprocess
import sysconfig
from pathlib import Path

from ..config import Settings
from ..names import BRIDGE_CLI, SOLVER_CLI
from .subproc import NO_WINDOW


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


def bridge_version(path: str | None, origin: str | None) -> str | None:
    """Versão do bridge no formato do `--version`; a do pacote vem dos metadados, sem
    lançar um processo que carrega o polars e a biblioteca só para dizê-la."""
    if origin == "pacote":
        try:
            return f"{BRIDGE_CLI} {metadata.version(BRIDGE_CLI)}"
        except metadata.PackageNotFoundError:
            pass
    return tool_version(path)


def find_bridge(settings: Settings) -> str | None:
    """Caminho do executável do bridge (ver `bridge_origin`)."""
    return bridge_origin(settings)[0]


def find_novomodelo(settings: Settings) -> str | None:
    """Caminho do executável do solver: NOVOMODELO_MCP_SOLVER_BIN, PATH, `~/.cargo/bin`.

    `~/.cargo/bin` é o destino padrão do instalador oficial: sem ele, o executável
    recém-instalado só seria achado depois de reiniciar o cliente com o PATH novo.
    """
    return (
        settings.solver_bin
        or shutil.which(SOLVER_CLI)
        or shutil.which(SOLVER_CLI, path=str(Path.home() / ".cargo" / "bin"))
    )


def tool_version(binpath: str | None) -> str | None:
    """Primeira linha da versão do binário, ou None se indisponível.

    Tenta `--version` (bridge) e, se falhar, o subcomando `version`
    (o CLI do solver expõe a versão como subcomando, não como flag).
    """
    if not binpath:
        return None
    for args in (["--version"], ["version"]):
        try:
            # argv em lista e sem shell; o binário vem da configuração ou do PATH, nunca do agente.
            proc = subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                [binpath, *args],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                **NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode == 0:
            out = (proc.stdout or proc.stderr or "").strip()
            if out:
                return out.splitlines()[0]
    return None
