"""Pré-voo e fábrica de sessões da carga do modo agent.

O pré-voo não gasta tokens: carrega os casos, aplica a seleção e as exclusões, sobe uma
vez o servidor MCP que o agente vai usar (a definição do ``~/.kiro/settings/mcp.json``,
a mesma da esteira, com o path guard restrito às fixtures) e lê as dicas das tools. Um
servidor que não sobe falha aqui, antes de qualquer sessão de agente. Se algum caso da
seleção grava, o pré-voo monta o plano da cópia das fixtures por sessão e confere o disco.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TextIO

from tests.e2e.launcher.providers import ProviderInfo
from tests.e2e.load.agent_cases import (
    CASES_PATH,
    AgentSelection,
    load_cases,
    plan_for_cases,
    select_cases,
)
from tests.e2e.load.agent_engine import AgentLoadConfig, PreflightResult, RunnerFactory
from tests.e2e.load.agent_session import AgentSessionRunner, prepare_session
from tests.e2e.load.client import STARTUP_TIMEOUT_S, stdio_client_factory
from tests.e2e.load.engine import LoadError
from tests.e2e.load.mix import ToolHints, is_forbidden_tool, writes_files
from tests.e2e.load.sandbox import SessionSandbox, check_disk
from tests.e2e.queries.loader import CasesLoaderError
from tests.e2e.queries.mcp_workspace import SERVER_NAME, server_config_for_workspace

__all__ = [
    "agent_server_config",
    "denied_tools",
    "make_preflight",
    "server_tool_lister",
    "session_factory",
]

ToolLister = Callable[[], Mapping[str, ToolHints]]

_REASONS_SHOWN = 5


def agent_server_config(fixtures_dir: Path) -> dict[str, Any]:
    """Definição do servidor que o agente usa, com o path guard restrito às fixtures.

    Raises:
        LoadError: Se o servidor ``novomodelo`` não está no ``~/.kiro/settings/mcp.json``.
    """
    server = server_config_for_workspace(fixtures_dir)
    if server is None:
        raise LoadError(
            f"servidor MCP '{SERVER_NAME}' não encontrado em ~/.kiro/settings/mcp.json: "
            "o agente não teria o MCP"
        )
    return server


def server_tool_lister(server: dict[str, Any], errlog: TextIO) -> ToolLister:
    """Sobe o servidor do agente uma vez e devolve as dicas das tools anunciadas."""
    env = {key: str(value) for key, value in (server.get("env") or {}).items()}
    factory = stdio_client_factory(server["command"], list(server.get("args") or []), env, errlog)

    async def list_once() -> Mapping[str, ToolHints]:
        async with factory(-1) as client:
            return await client.list_tools()

    def lister() -> Mapping[str, ToolHints]:
        try:
            return asyncio.run(asyncio.wait_for(list_once(), timeout=STARTUP_TIMEOUT_S))
        except Exception as exc:  # noqa: BLE001 - reportado como LoadError
            leaf: BaseException = exc
            while isinstance(leaf, BaseExceptionGroup) and leaf.exceptions:
                leaf = leaf.exceptions[0]
            raise LoadError(
                f"o servidor MCP do agente não iniciou: {type(leaf).__name__}: {leaf}"[:400]
            ) from exc

    return lister


def _no_cases(selection: AgentSelection, what: str) -> LoadError:
    reasons = "; ".join(f"{e.id}: {e.reason}" for e in selection.excluded[:_REASONS_SHOWN])
    return LoadError(
        f"nenhum caso da seleção ({what}) pode rodar na carga: {reasons or 'seleção vazia'}"
    )


def make_preflight(
    config: AgentLoadConfig,
    fixtures_dir: Path,
    list_tools: ToolLister,
    cases_path: Path = CASES_PATH,
    work_dir: Path | None = None,
) -> Callable[[], PreflightResult]:
    """Pré-voo: seleção estática primeiro (sem subir nada), depois as dicas do servidor e,
    se a seleção grava, o plano da cópia por sessão e o disco livre em ``work_dir``.
    """

    def preflight() -> PreflightResult:
        try:
            cases = load_cases(fixtures_dir, cases_path)
        except CasesLoaderError as exc:
            raise LoadError(f"cases.yaml inválido: {exc}") from exc
        what = config.selection.describe()
        try:
            static = select_cases(cases, config.selection)
        except ValueError as exc:
            raise LoadError(str(exc)) from exc
        if not static.cases:
            raise _no_cases(static, what)
        hints = dict(list_tools())
        final = select_cases(cases, config.selection, hints)
        if not final.cases:
            raise _no_cases(final, what)
        plan = plan_for_cases(fixtures_dir, final.cases)
        check_disk(plan, config.concurrency, work_dir or tempfile.gettempdir())
        return PreflightResult(final, hints, sandbox_plan=plan)

    return preflight


def denied_tools(
    server_tools: Mapping[str, ToolHints] | None, sandboxed: bool = False
) -> list[str]:
    """Tools que o servidor anuncia como escrita e a sessão não pode usar: o claude da carga
    as recebe negadas. Sem a cópia por sessão, todas; com ela, as barradas da carga e as
    que gravam sem ser das que rodam na cópia."""
    return sorted(
        tool
        for tool, hint in (server_tools or {}).items()
        if not hint.read_only
        and (not sandboxed or is_forbidden_tool(tool) or not writes_files(tool))
    )


def _sandboxed(preflight: PreflightResult) -> bool:
    plan = preflight.sandbox_plan
    return plan is not None and plan.enabled


def session_factory(
    provider: ProviderInfo,
    run_root: Path,
    server: dict[str, Any],
    fixtures_dir: Path,
    timeout_s: float | None,
    sandboxes: list[SessionSandbox] | None = None,
) -> RunnerFactory:
    """Fábrica de runners: cada chamada prepara a pasta (e a cópia) da sessão e devolve o
    runner dela; as cópias criadas vão para ``sandboxes``, para o resumo do run."""

    def factory(index: int, preflight: PreflightResult) -> AgentSessionRunner:
        paths = prepare_session(run_root, index, server, provider.id, preflight.sandbox_plan)
        if sandboxes is not None and paths.sandbox is not None:
            sandboxes.append(paths.sandbox)
        return AgentSessionRunner(
            provider,
            paths,
            fixtures_dir,
            timeout_seconds=timeout_s,
            denied_tools=denied_tools(preflight.server_tools, _sandboxed(preflight)),
        )

    return factory
