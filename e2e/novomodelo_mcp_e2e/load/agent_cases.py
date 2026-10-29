"""Casos por agente (``cases.yaml``) que podem entrar na carga do modo agent.

A carga roda os mesmos casos da esteira, só que em N sessões ao mesmo tempo. Fica de
fora, com o motivo (``mix.barred_reason``), o caso cuja tool esperada (``tool`` ou
qualquer uma de ``tools``) é barrada por ``mix.is_forbidden_tool``: o solver e os jobs
dele, e a rede. Um caso cuja tool grava (``mix.writes_files``) também fica de fora (``REASON_WRITES``): no
container da carga a tool fica negada, e a carga mediria a negação. Também ficam de fora o caso
que não usa o MCP (não exercita o servidor) e o caso cuja fonte (``requires``) falta. Com
as dicas do servidor (pré-voo), sai ainda a tool que ele anuncia com rede ou como escrita.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from novomodelo_mcp_e2e.load.mix import (
    Excluded,
    ToolHints,
    barred_reason,
    is_forbidden_tool,
    is_heavy_tool,
    writes_files,
)
from novomodelo_mcp_e2e.load.sandbox import SandboxPlan, plan_for
from novomodelo_mcp_e2e.queries.loader import CasesLoader
from novomodelo_mcp_e2e.queries.models import QueryTestCase
from novomodelo_mcp_e2e.queries.preconditions import missing_sources
from novomodelo_mcp_e2e.queries.store import TOOL_GROUPS

__all__ = [
    "CASES_PATH",
    "AgentSelection",
    "CaseSelection",
    "case_group",
    "case_is_heavy",
    "case_writes",
    "describe_cases",
    "exclusion_reason",
    "expected_tools",
    "load_cases",
    "plan_for_cases",
    "select_cases",
    "writes_files",
]

CASES_PATH = Path(__file__).resolve().parent.parent / "queries" / "cases.yaml"

OTHER_GROUP = "other"
REASON_WRITES = "tool que grava: no container ela fica negada; a carga mediria a negação"


def expected_tools(case: QueryTestCase) -> tuple[str, ...]:
    if case.expected.tool:
        return (case.expected.tool,)
    return tuple(case.expected.tools or ())


def case_group(case: QueryTestCase) -> str:
    """Grupo do caso: o da tool esperada (a primeira, se várias são aceitas)."""
    tools = expected_tools(case)
    return TOOL_GROUPS.get(tools[0], OTHER_GROUP) if tools else OTHER_GROUP


def case_writes(case: QueryTestCase) -> bool:
    """True se alguma tool esperada grava: a seleção com o caso roda na cópia por sessão."""
    return any(writes_files(tool) for tool in expected_tools(case))


def case_is_heavy(case: QueryTestCase) -> bool:
    """True se alguma tool esperada sobe o bridge ou a CLI do solver."""
    return any(is_heavy_tool(tool) for tool in expected_tools(case))


def plan_for_cases(fixtures_dir: str | Path, cases: Iterable[QueryTestCase]) -> SandboxPlan:
    """Plano da cópia por sessão: as subárvores citadas nos prompts e fontes dos casos, se
    algum deles grava; senão, sem cópia."""
    cases = list(cases)
    texts = [text for case in cases for text in (case.query, *case.requires)]
    return plan_for(fixtures_dir, texts, any(case_writes(case) for case in cases))


def exclusion_reason(
    case: QueryTestCase, server_tools: Mapping[str, ToolHints] | None = None
) -> str | None:
    """Por que o caso fica fora da carga, ou None se ele pode rodar em paralelo."""
    if not case.expected.uses_mcp:
        return "não usa o MCP: não exercita o servidor"
    for tool in expected_tools(case):
        if is_forbidden_tool(tool):
            return barred_reason(tool)
    if any(writes_files(tool) for tool in expected_tools(case)):
        return REASON_WRITES
    if server_tools is not None:
        for tool in expected_tools(case):
            hint = server_tools.get(tool)
            if hint is None:
                return f"{tool} ausente no servidor"
            if not hint.read_only:
                return REASON_WRITES
            if hint.open_world:
                return f"o servidor anuncia {tool} com acesso à rede"
    missing = missing_sources(case)
    if missing:
        return "fonte ausente ou vazia: " + ", ".join(missing)
    return None


@dataclass(frozen=True)
class CaseSelection:
    """Quais casos a carga roda: todos (nada definido), um grupo, tags (OU) ou um caso."""

    case_id: str | None = None
    group: str | None = None
    tags: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.tags is not None:
            tags = tuple(dict.fromkeys(t.strip() for t in self.tags if t and t.strip()))
            object.__setattr__(self, "tags", tags or None)
        chosen = [v for v in (self.case_id, self.group, self.tags) if v]
        if len(chosen) > 1:
            raise ValueError("escolha só um entre caso, grupo e tags")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.group,
            "tags": list(self.tags) if self.tags else None,
        }

    def describe(self) -> str:
        if self.case_id:
            return f"caso {self.case_id}"
        if self.group:
            return f"grupo {self.group}"
        if self.tags:
            return "tags " + ", ".join(self.tags)
        return "todos os casos"


@dataclass
class AgentSelection:
    cases: list[QueryTestCase] = field(default_factory=list)
    excluded: list[Excluded] = field(default_factory=list)


def load_cases(fixtures_dir: str | Path, cases_path: Path = CASES_PATH) -> list[QueryTestCase]:
    """Todos os casos do ``cases.yaml``, com ``{FIXTURES}`` expandido.

    Raises:
        CasesLoaderError: Se o YAML não carrega ou não valida.
    """
    return CasesLoader(cases_path, Path(fixtures_dir)).load()


def _matching(cases: list[QueryTestCase], selection: CaseSelection) -> list[QueryTestCase]:
    if selection.case_id:
        found = [c for c in cases if c.id == selection.case_id]
        if not found:
            raise ValueError(f"caso desconhecido: {selection.case_id}")
        return found
    if selection.group:
        groups = sorted({case_group(c) for c in cases})
        if selection.group not in groups:
            raise ValueError(f"grupo desconhecido: {selection.group} (grupos: {', '.join(groups)})")
        return [c for c in cases if case_group(c) == selection.group]
    if selection.tags:
        wanted = set(selection.tags)
        found = [c for c in cases if wanted & set(c.tags)]
        if not found:
            raise ValueError(f"nenhum caso com as tags: {', '.join(selection.tags)}")
        return found
    return list(cases)


def select_cases(
    cases: Iterable[QueryTestCase],
    selection: CaseSelection,
    server_tools: Mapping[str, ToolHints] | None = None,
) -> AgentSelection:
    """Casos da seleção que podem rodar em paralelo; os demais vão para ``excluded``.

    Raises:
        ValueError: Se o caso ou o grupo não existe, ou se as tags não casam com nenhum caso.
    """
    result = AgentSelection()
    for case in _matching(list(cases), selection):
        reason = exclusion_reason(case, server_tools)
        if reason is None:
            result.cases.append(case)
        else:
            tool = "/".join(expected_tools(case)) or OTHER_GROUP
            result.excluded.append(Excluded(case.id, tool, reason))
    return result


def describe_cases(cases: Iterable[QueryTestCase]) -> list[dict[str, Any]]:
    """Casos para a UI: grupo, tags, tool esperada e se podem entrar na carga (e por quê não)."""
    described = []
    for case in cases:
        reason = exclusion_reason(case)
        described.append(
            {
                "id": case.id,
                "query": case.query,
                "group": case_group(case),
                "tags": list(case.tags),
                "expected_tool": case.expected.tool,
                "expected_tools": case.expected.tools,
                "timeout_s": case.timeout_s,
                "available": reason is None,
                "reason": reason,
                "writes": case_writes(case),
                "heavy": case_is_heavy(case),
            }
        )
    return described
