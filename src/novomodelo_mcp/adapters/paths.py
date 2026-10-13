"""Guard de caminho: confina leitura/escrita à raiz permitida (NOVOMODELO_MCP_WORKSPACE).

Modelo de ameaça: um agente de IA controla os caminhos passados às tools. Mesmo
offline, o servidor lê/escreve com os privilégios do usuário. Este guard trata a
entrada como não confiável.

- Sem `NOVOMODELO_MCP_WORKSPACE`: opera irrestrito (o `server_info` sinaliza isso).
- Com raiz(es) configurada(s) (separadas por os.pathsep): qualquer caminho fora
  delas é RECUSADO (fail-closed). `resolve()` neutraliza symlinks e `..`.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..config import Settings
from .envelope import error


def allowed_roots(settings: Settings) -> list[Path]:
    raw = settings.workspace
    if not raw:
        return []
    roots: list[Path] = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if not part:
            continue
        try:
            roots.append(Path(part).expanduser().resolve())
        except OSError:
            continue
    return roots


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def ensure_in_workspace(*paths: str | None, settings: Settings) -> dict | None:
    """None se todos os caminhos estão dentro da raiz (ou se não há raiz);
    senão, um envelope de erro. Chamada no topo de toda tool que recebe caminho.
    """
    roots = allowed_roots(settings)
    if not roots:
        return None  # irrestrito
    for p in paths:
        if p is None:
            continue
        try:
            rp = Path(p).expanduser().resolve()
        except OSError as exc:
            return error(22, f"caminho invalido: {p}", str(exc))
        if not any(_within(rp, root) for root in roots):
            return error(13, f"caminho fora do workspace permitido: {p}",
                         f"raizes: {[str(r) for r in roots]}")
    return None
