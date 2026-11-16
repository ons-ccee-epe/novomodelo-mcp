"""Teto de tamanho das respostas com linhas (`NOVOMODELO_MCP_MAX_RESPONSE_KB`)."""

from __future__ import annotations

import copy
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


def fit_to_budget(
    envelope: dict[str, Any], settings: Settings, key: str, reserve: int = 0
) -> dict[str, Any]:
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
        out = {
            **envelope,
            key: rows[:n],
            "truncated": True,
            "cortado_por_tamanho": {
                "teto_kb": settings.max_response_kb,
                "linhas_devolvidas": n,
                "linhas_antes_do_corte": len(rows),
            },
        }
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


def _lists(obj: Any) -> list[tuple[dict[str, Any], str]]:
    """(dict dono, chave) de cada lista dentro de dicts, sem entrar nos itens das listas."""
    found: list[tuple[dict[str, Any], str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list):
                found.append((obj, k))
            elif isinstance(v, dict):
                found.extend(_lists(v))
    return found


def _keep_prefix_that_fits(
    out: dict[str, Any], owner: dict[str, Any], key: str, budget: int
) -> None:
    """Deixa em `owner[key]` o maior começo da lista com o qual `out` cabe em `budget`."""
    rows = owner[key]
    lo, hi = 0, len(rows)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        owner[key] = rows[:mid]
        if response_bytes(out) <= budget:
            lo = mid
        else:
            hi = mid - 1
    owner[key] = rows[:lo]


def shrink_to_budget(envelope: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Encolhe a maior lista aninhada até a resposta caber em `max_response_kb`.

    Para as respostas com várias listas (cortes da política, PAR(p), itens do resumo do
    caso): cada lista cortada ganha `truncado: true` no dict que a contém.
    """
    budget = settings.max_response_kb * 1024
    if response_bytes(envelope) <= budget:
        return envelope
    out = copy.deepcopy(envelope)
    out["cortado_por_tamanho"] = {"teto_kb": settings.max_response_kb}
    cortadas: set[int] = set()
    while response_bytes(out) > budget:
        candidatas = [
            (dono, k)
            for dono, k in _lists(out)
            if out.get("cortado_por_tamanho") is not dono
            and dono[k]
            and id(dono[k]) not in cortadas
        ]
        if not candidatas:
            break
        dono, k = max(candidatas, key=lambda c: response_bytes(c[0][c[1]]))
        dono["truncado"] = True
        _keep_prefix_that_fits(out, dono, k, budget)
        cortadas.add(id(dono[k]))
    return out


def _diagnostic_tables(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        d["table"]
        for d in envelope.get("diagnostics") or []
        if isinstance(d, dict)
        and isinstance(d.get("table"), dict)
        and isinstance(d["table"].get("rows"), list)
    ]


def shrink_tables_to_budget(envelope: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Encolhe as tabelas dos diagnósticos do bridge até a resposta caber em `max_response_kb`.

    A maior tabela perde as últimas linhas primeiro; cada tabela cortada ganha `truncado`
    e `linhas_total`, e todo diagnóstico continua na resposta. Se cortar as tabelas não
    basta, o `shrink_to_budget` corta a lista de diagnósticos.
    """
    budget = settings.max_response_kb * 1024
    if response_bytes(envelope) <= budget:
        return envelope
    out = copy.deepcopy(envelope)
    out["cortado_por_tamanho"] = {"teto_kb": settings.max_response_kb}
    cortadas: set[int] = set()
    while response_bytes(out) > budget:
        candidatas = [t for t in _diagnostic_tables(out) if t["rows"] and id(t) not in cortadas]
        if not candidatas:
            return shrink_to_budget(out, settings)
        table = max(candidatas, key=lambda t: response_bytes(t["rows"]))
        table["truncado"] = True
        table["linhas_total"] = len(table["rows"])
        _keep_prefix_that_fits(out, table, "rows", budget)
        cortadas.add(id(table))
    return out
