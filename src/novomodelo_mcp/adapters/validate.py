"""Validacao leve de parametros das tools de comparacao (pre-bridge).

Barra entradas invalidas ANTES de invocar o novomodelo-bridge, com uma mensagem de
erro clara para o agente, em vez de delegar a falha a CLI. Sao funcoes puras:
recebem o valor cru do parametro e devolvem um envelope de erro (formato unico
de :mod:`novomodelo_mcp.adapters.envelope`) ou ``None`` quando o valor e valido.

Escopo deliberadamente minimo (zero regra de negocio): apenas as invariantes
que a CLI documenta e que sao baratas de checar aqui:

* ``tolerance`` (quando fornecida): numero no intervalo aberto-fechado
  ``(0.0, 1.0]``.
* ``fmt`` (quando fornecido): token pertencente ao conjunto aceito pela CLI
  ``{console, html, csv, parquet, json, all}``.

O codigo de saida dos envelopes de erro segue a convencao da CLI para entrada
invalida (``2``), coerente com o ``compare``/``_parse_formats`` do novomodelo-bridge.
"""
from __future__ import annotations

from typing import Any

from .envelope import error

#: Tokens de ``--format`` aceitos pelo novomodelo-bridge (compare newave/decomp).
#: Espelha ``_VALID_CLI_FORMATS`` da CLI: console,html,csv,parquet,json,all.
VALID_FORMATS: frozenset[str] = frozenset(
    {"console", "html", "csv", "parquet", "json", "all"}
)

#: Codigo de saida para entrada invalida (convencao EINVAL/CLI compare == 2).
_INVALID_INPUT_EXIT: int = 2


def validate_tolerance(tolerance: float | int | None) -> dict[str, Any] | None:
    """Valida ``tolerance``; ``None`` se valida, senao um envelope de erro.

    Regra: quando fornecida, deve ser um numero no intervalo ``(0.0, 1.0]``
    (limite inferior aberto, superior fechado). ``bool`` e recusado
    explicitamente (em Python e subtipo de ``int``, mas nao e tolerancia).
    """
    if tolerance is None:
        return None
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        return error(
            _INVALID_INPUT_EXIT,
            "tolerance invalida: informe um numero no intervalo (0.0, 1.0].",
            f"recebido: {tolerance!r}",
        )
    value = float(tolerance)
    if not (0.0 < value <= 1.0):
        return error(
            _INVALID_INPUT_EXIT,
            "tolerance fora do intervalo (0.0, 1.0].",
            f"recebido: {value!r}",
        )
    return None


def validate_fmt(fmt: str | None) -> dict[str, Any] | None:
    """Valida o token ``fmt``; ``None`` se valido, senao um envelope de erro.

    Regra: quando fornecido, deve ser uma string pertencente a
    :data:`VALID_FORMATS`. Mantem a compatibilidade com a assinatura atual das
    tools (``fmt: str``), sem ampliar para multiplos formatos.
    """
    if fmt is None:
        return None
    if not isinstance(fmt, str) or fmt not in VALID_FORMATS:
        allowed = ", ".join(sorted(VALID_FORMATS))
        return error(
            _INVALID_INPUT_EXIT,
            f"format invalido: use um de [{allowed}].",
            f"recebido: {fmt!r}",
        )
    return None


def validate_compare_inputs(
    tolerance: float | int | None, fmt: str | None
) -> dict[str, Any] | None:
    """Valida os parametros de comparacao; ``None`` se todos validos.

    Retorna o PRIMEIRO envelope de erro encontrado (tolerance antes de fmt),
    para ser chamado no topo das tools de compare, antes de ``run_bridge``.
    """
    return validate_tolerance(tolerance) or validate_fmt(fmt)
