"""Comando equivalente a um disparo de rodada, para a UI mostrar antes de rodar."""

from __future__ import annotations

from typing import Any

from tests.e2e.launcher.service import RodadaRequest, comando_equivalente

__all__ = ["command_preview"]


def command_preview(req: RodadaRequest) -> dict[str, Any]:
    """O comando de `rodar` que o disparo executaria, sem caminho do host nem segredo.

    Args:
        req: Pedido já validado; nada é iniciado nem gravado.
    """
    return comando_equivalente(req)
