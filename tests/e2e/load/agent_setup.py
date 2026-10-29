"""Pré-voo e fábrica de sessões da carga do modo agent.

O pré-voo não gasta tokens: carrega os casos, aplica a seleção e as exclusões e lê as
dicas das tools do servidor deste checkout (``executor.container.tools_do_servidor``,
sem subir processo). Cada sessão é um ``ExecutorSessionRunner``: o agente roda no
container do executor, com a cópia própria do caso.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from tests.e2e.config import Config
from tests.e2e.executor.container import tools_do_servidor
from tests.e2e.executor.imagens import ConfigMCP
from tests.e2e.load.agent_cases import (
    CASES_PATH,
    AgentSelection,
    load_cases,
    select_cases,
)
from tests.e2e.load.agent_engine import AgentLoadConfig, PreflightResult, RunnerFactory
from tests.e2e.load.agent_session import AGENTE_DO_PROVEDOR, ExecutorSessionRunner
from tests.e2e.load.engine import LoadError
from tests.e2e.load.mix import ToolHints
from tests.e2e.queries.loader import CasesLoaderError

__all__ = [
    "denied_tools",
    "make_preflight",
    "server_tool_hints",
    "session_factory",
]

ToolLister = Callable[[], Mapping[str, ToolHints]]

_REASONS_SHOWN = 5


def server_tool_hints() -> Mapping[str, ToolHints]:
    """As dicas das tools do servidor; uma anotação ausente conta como escrita e rede."""
    return {
        nome: ToolHints(read_only=bool(a.so_leitura), open_world=True if a.rede is None else a.rede)
        for nome, a in tools_do_servidor().items()
    }


def _no_cases(selection: AgentSelection, what: str) -> LoadError:
    reasons = "; ".join(f"{e.id}: {e.reason}" for e in selection.excluded[:_REASONS_SHOWN])
    return LoadError(
        f"nenhum caso da seleção ({what}) pode rodar na carga: {reasons or 'seleção vazia'}"
    )


def make_preflight(
    config: AgentLoadConfig,
    fixtures_dir: Path,
    list_tools: ToolLister = server_tool_hints,
    cases_path: Path = CASES_PATH,
) -> Callable[[], PreflightResult]:
    """Pré-voo: seleção estática primeiro, depois as dicas do servidor deste checkout."""

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
        return PreflightResult(final, hints)

    return preflight


def denied_tools(server_tools: Mapping[str, ToolHints] | None) -> list[str]:
    """Tools que o servidor anuncia como escrita: ficam negadas no container da carga."""
    return sorted(tool for tool, hint in (server_tools or {}).items() if not hint.read_only)


def session_factory(
    provider: str,
    config_mcp: ConfigMCP,
    cfg: Config,
    run_root: Path,
    timeout_s: float | None,
) -> RunnerFactory:
    """Fábrica de runners: cada sessão tem a sua pasta de registros sob ``run_root``."""
    agente = AGENTE_DO_PROVEDOR[provider]

    def factory(index: int, preflight: PreflightResult) -> ExecutorSessionRunner:
        return ExecutorSessionRunner(
            agente, config_mcp, cfg, run_root / f"s{index}", timeout_s=timeout_s
        )

    return factory
