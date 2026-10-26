"""Envelope de erro compartilhado por adaptadores e tools — fonte única.

Elimina a duplicação de `_error` entre bridge.py/novomodelo.py e o número mágico
de truncagem de detalhe espalhado pelo código.
"""
from __future__ import annotations

from typing import Any

#: Teto de caracteres de detalhe (stderr/mensagem) repassado ao agente.
MAX_DETAIL_CHARS = 2000


def error(code: int, message: str, detail: str = "", **extra: Any) -> dict[str, Any]:
    """Envelope de erro padrão: {status, exit_code, diagnostics}, mais os campos de `extra`."""
    diagnostics = [message]
    if detail:
        diagnostics.append(detail[:MAX_DETAIL_CHARS])
    return {"status": "error", "exit_code": code, "diagnostics": diagnostics, **extra}


def as_error(exc: BaseException, *, code: int = 1) -> dict[str, Any]:
    """Converte uma exceção num envelope de erro, sem derrubar o servidor."""
    return {"status": "error", "exit_code": code,
            "diagnostics": [f"{type(exc).__name__}: {exc}"[:MAX_DETAIL_CHARS]]}
