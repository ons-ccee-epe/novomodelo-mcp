"""Registro dos lançamentos: lista em `lancamentos.json`, a baseline do próximo go/no-go."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from novomodelo_mcp_e2e.resultado.armazenamento import _gravar_json

NOME_ARQUIVO = "lancamentos.json"


class LancamentosCorrompido(ValueError):
    """`lancamentos.json` existe mas não é uma lista JSON de objetos."""


def _ler(resultados: Path) -> list[dict[str, Any]]:
    arquivo = resultados / NOME_ARQUIVO
    if not arquivo.exists():
        return []
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except ValueError as erro:
        raise LancamentosCorrompido(f"{NOME_ARQUIVO} não é JSON válido: {erro}") from erro
    if not isinstance(dados, list) or not all(isinstance(item, dict) for item in dados):
        raise LancamentosCorrompido(f"{NOME_ARQUIVO} deve ser uma lista de objetos")
    return dados


def marcar_lancamento(resultados: Path, rodada: str, versao: str, config: str) -> None:
    lista = _ler(resultados)
    lista.append(
        {
            "versao": versao,
            "rodada": rodada,
            "config": config,
            "marcado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        }
    )
    _gravar_json(resultados / NOME_ARQUIVO, lista)  # type: ignore[arg-type]


def ultimo_lancamento(resultados: Path) -> dict[str, Any] | None:
    lista = _ler(resultados)
    return lista[-1] if lista else None
