"""Teto de tamanho das respostas com linhas (`NOVOMODELO_MCP_MAX_RESPONSE_KB`)."""
from __future__ import annotations

import json
from typing import Any

from ..config import Settings


def row_limit(settings: Settings) -> int:
    """Linhas que caberiam no teto se cada uma tivesse o mínimo de 16 bytes: o máximo
    que vale buscar (um `limit` enorme não traz milhões de linhas para a memória)."""
    return max(1, settings.max_response_kb * 1024 // 16)


def response_bytes(envelope: Any) -> int:
    """Tamanho da resposta como o cliente a recebe (o FastMCP serializa com indent=2)."""
    return len(json.dumps(envelope, ensure_ascii=False, indent=2, default=str).encode("utf-8"))


def fit_to_budget(envelope: dict[str, Any], settings: Settings, key: str,
                  reserve: int = 0) -> dict[str, Any]:
    """Corta `envelope[key]` (lista de linhas) até a resposta caber em `max_response_kb`.

    O teto é de tamanho, não de linhas: o cliente recusa a resposta grande inteira (o
    Claude Code acima de ~25 mil tokens), e uma linha larga pesa dezenas de vezes uma
    estreita. `cortado_por_tamanho` diz quanto veio; `truncated` passa a true.
    `reserve`: bytes que o chamador ainda vai acrescentar (ex.: o `proximo_passo`).
    """
    rows = envelope.get(key)
    budget = settings.max_response_kb * 1024 - reserve
    if not isinstance(rows, list) or response_bytes(envelope) <= budget:
        return envelope

    def cut(n: int) -> dict[str, Any]:
        out = {**envelope, key: rows[:n], "truncated": True,
               "cortado_por_tamanho": {"teto_kb": settings.max_response_kb,
                                       "linhas_devolvidas": n, "linhas_antes_do_corte": len(rows)}}
        if "row_count" in out:
            out["row_count"] = n
        return out

    lo, hi = 0, len(rows)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if response_bytes(cut(mid)) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return cut(lo)
