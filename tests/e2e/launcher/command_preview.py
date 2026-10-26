"""Comando equivalente a um disparo, para a UI mostrar antes de rodar."""

from __future__ import annotations

import dataclasses
import shlex
from pathlib import Path
from typing import Any

from tests.e2e.launcher.providers import ProviderInfo, build_command
from tests.e2e.queries.models import QueryTestCase
from tests.e2e.queries.store import conjunto_from_filters

_TERMINAL_BASE = "python -m tests.e2e.queries.run_queries"
_QUERY_PLACEHOLDER = "<pergunta>"
_CONFIG_PLACEHOLDER = "<config-mcp-temporaria>"


def _is_placeholder(arg: str) -> bool:
    return arg in (_QUERY_PLACEHOLDER, _CONFIG_PLACEHOLDER)


def _join(args: list[str]) -> str:
    # shlex.join aspa os marcadores <...>; eles precisam aparecer legíveis.
    return " ".join(arg if _is_placeholder(arg) else shlex.quote(arg) for arg in args)


def _terminal(provider: ProviderInfo, tags: list[str] | None, case_id: str | None) -> str | None:
    if provider.id != "kiro-cli":
        return None
    if case_id:
        return f"{_TERMINAL_BASE} --case {shlex.quote(case_id)}"
    if tags:
        return f"{_TERMINAL_BASE} --tags {' '.join(shlex.quote(t) for t in tags)}"
    return _TERMINAL_BASE


def command_preview(
    provider: ProviderInfo,
    tags: list[str] | None,
    case_id: str | None,
    cases: list[QueryTestCase],
) -> dict[str, Any]:
    """Comando de terminal (só kiro-cli) e comando do agente que o disparo executaria.

    Args:
        provider: Provedor resolvido.
        tags: Filtro por tags, na ordem recebida.
        case_id: Um único caso.
        cases: Casos que o filtro seleciona.
    """
    terminal = _terminal(provider, tags, case_id)
    query = cases[0].query if len(cases) == 1 else _QUERY_PLACEHOLDER
    command = build_command(
        dataclasses.replace(provider, path=None),
        query,
        mcp_config_path=Path(_CONFIG_PLACEHOLDER),
    )
    return {
        "conjunto": conjunto_from_filters(tags, case_id),
        "total": len(cases),
        "terminal": terminal,
        "terminal_note": None
        if terminal
        else f"O run_queries só executa com o kiro-cli; não há equivalente de terminal para {provider.label}.",
        "agent": _join(command),
    }
