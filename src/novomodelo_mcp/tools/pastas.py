"""Inclusão de pastas de estudo nas raízes do guard, a pedido do usuário."""

from __future__ import annotations

from ..adapters.envelope import as_error
from ..adapters.obs import log
from ..adapters.paths import include_folders
from ..config import Settings
from .annotations import WRITES


def register_pastas(mcp, settings: Settings) -> None:
    """Registra `incluir_pastas` no servidor `mcp`."""

    # Nunca READ_ONLY: é a única tool que amplia o guard, e a aprovação do cliente a
    # cada chamada é a confirmação do usuário (o `configurar` só libera as de leitura).
    @mcp.tool(annotations=WRITES)
    def incluir_pastas(pastas: list[str]) -> dict:
        """Inclui pastas de estudo na pasta de trabalho; vale na hora, sem reabrir o cliente.

        Use só depois de o usuário aceitar, com todas as pastas de uma vez (a
        `suggested_folder` de cada recusa). Recusa, com motivo, o que não é pasta, a
        pasta pessoal inteira, a raiz do disco e pastas de configuração de programas.
        A inclusão fica gravada para as próximas conversas.
        """
        try:
            result = include_folders(pastas, settings)
        except Exception as exc:  # noqa: BLE001 - never-raise: falha de lock/escrita vira envelope
            return as_error(exc)
        log(settings, "incluir_pastas", pastas=pastas, included=result.get("included"))
        return result
