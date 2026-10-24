"""Mix de chamadas da carga: só tools somente leitura, com parâmetros de fixtures reais.

O catálogo é uma lista fechada (allow-list). Uma tool entra no mix só se estiver
no catálogo E o servidor a anunciar com ``readOnlyHint`` e sem ``openWorldHint``:
``run_plan`` e ``solver_version``, por exemplo, são somente leitura mas disparam
o solver/CLI e ficam de fora do catálogo.

Os caminhos vêm de ``cases.yaml`` (decks ``cobre-caso-reduzido`` e
``cobre-mar-26-rv2-reduzido``, que o ``cases.yaml`` ainda usa), do README das
fixtures (``newave-determ`` e ``results/sample_run``) e dos exemplos nas docstrings
das tools. Uma chamada cuja fonte falta (ou é uma pasta vazia) é pulada, não falha.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "ALLOWED_TOOLS",
    "CATALOG",
    "CallSpec",
    "CallTemplate",
    "Excluded",
    "Selection",
    "ToolHints",
    "describe_catalog",
    "hints_from_tools",
    "is_forbidden_tool",
    "select_specs",
    "tool_group",
    "validate_tools",
]

FIXTURES_TOKEN = "{FIXTURES}"
FIXTURES_POSIX_TOKEN = "{FIXTURES_POSIX}"

# Gravam arquivos, disparam o solver/conversão ou usam a rede.
_FORBIDDEN = re.compile(
    r"^(run_|instalar_|deck_edit_|bridge_|case_init$|schema_export$|server_info$)|_convert_"
)

_NEWAVE_AGO = "newave/cobre-caso-reduzido"
_DECOMP_MAR = "decomp/cobre-mar-26-rv2-reduzido"
_NEWAVE_DETERM = "newave-determ/cobre-set-24-reduzido-calibrado-determ-2000"
_RESULTS_SAMPLE = "results/sample_run"
_RESULTS_NEWAVE_AGO = "newave/cobre-caso-reduzido/output"

_INFLOW_HISTORY = f"{_NEWAVE_DETERM}/scenarios/inflow_history.parquet"


def is_forbidden_tool(tool: str) -> bool:
    """True para tools que gravam, disparam solver/conversão ou usam a rede."""
    return _FORBIDDEN.search(tool) is not None


def tool_group(tool: str) -> str:
    """Grupo da tool: o prefixo antes do primeiro ``_`` (``deck``, ``docs``...)."""
    return tool.split("_", 1)[0]


@dataclass(frozen=True)
class CallTemplate:
    """Chamada com ``{FIXTURES}`` por expandir; ``requires`` são fontes relativas às fixtures."""

    tool: str
    label: str
    arguments: Mapping[str, Any]
    requires: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return f"{self.tool}#{self.label}"


@dataclass(frozen=True)
class CallSpec:
    """Chamada pronta: argumentos com caminhos absolutos."""

    id: str
    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolHints:
    """Dicas MCP que o servidor anuncia para uma tool."""

    read_only: bool
    open_world: bool


@dataclass(frozen=True)
class Excluded:
    id: str
    tool: str
    reason: str


@dataclass
class Selection:
    specs: list[CallSpec] = field(default_factory=list)
    excluded: list[Excluded] = field(default_factory=list)


def _deck_calls() -> list[CallTemplate]:
    calls: list[CallTemplate] = []
    for label, deck in (
        ("newave-ago26", _NEWAVE_AGO),
        ("decomp-mar26", _DECOMP_MAR),
        ("newave-determ", _NEWAVE_DETERM),
    ):
        calls.append(
            CallTemplate(
                "deck_list", label, {"case_dir": f"{FIXTURES_TOKEN}/{deck}"}, (f"{deck}/config.json",)
            )
        )
        for name in ("config.json", "penalties.json"):
            calls.append(
                CallTemplate(
                    "deck_read_json",
                    f"{label}/{name}",
                    {"path": f"{FIXTURES_TOKEN}/{deck}/{name}"},
                    (f"{deck}/{name}",),
                )
            )
    return calls


def _parquet_calls() -> list[CallTemplate]:
    calls: list[CallTemplate] = []
    for tool, label, deck, name in (
        ("deck_read_parquet", "newave-ago26/stages", _NEWAVE_AGO, "stages.parquet"),
        ("deck_read_parquet", "newave-determ/inflow_history", _NEWAVE_DETERM,
         "scenarios/inflow_history.parquet"),
        ("deck_describe_parquet", "newave-ago26/buses", _NEWAVE_AGO, "system/buses.parquet"),
        ("deck_describe_parquet", "newave-determ/hydro_geometry", _NEWAVE_DETERM,
         "system/hydro_geometry.parquet"),
    ):
        calls.append(
            CallTemplate(tool, label, {"path": f"{FIXTURES_TOKEN}/{deck}/{name}"}, (f"{deck}/{name}",))
        )
    return calls


def _sql_calls() -> list[CallTemplate]:
    source = f"read_parquet('{FIXTURES_POSIX_TOKEN}/{_INFLOW_HISTORY}')"
    return [
        CallTemplate(
            "deck_sql", "inflow-amostra", {"query": f"SELECT * FROM {source} LIMIT 10"},
            (_INFLOW_HISTORY,),
        ),
        CallTemplate(
            "deck_sql",
            "inflow-agregado",
            {
                "query": (
                    "SELECT hydro_id, min(value_m3s) AS min_v, max(value_m3s) AS max_v, "
                    f"count(*) AS n FROM {source} GROUP BY hydro_id ORDER BY min_v LIMIT 20"
                )
            },
            (_INFLOW_HISTORY,),
        ),
    ]


def _reference_calls() -> list[CallTemplate]:
    return [
        CallTemplate("docs_list", "todas", {}),
        CallTemplate("docs_search", "sddp", {"consulta": "SDDP"}),
        CallTemplate("docs_search", "convergence", {"consulta": "convergence"}),
        CallTemplate("docs_read", "cli-reference", {"page": "reference/cli-reference"}),
        CallTemplate("schema_list", "todos", {}),
        CallTemplate("schema_get", "config", {"tipo": "config"}),
        CallTemplate("schema_get", "stages", {"tipo": "stages"}),
    ]


def _results_calls() -> list[CallTemplate]:
    calls: list[CallTemplate] = []
    for label, output in (("sample-run", _RESULTS_SAMPLE), ("newave-ago26", _RESULTS_NEWAVE_AGO)):
        args = {"output_dir": f"{FIXTURES_TOKEN}/{output}"}
        calls += [
            CallTemplate("results_status", label, args, (f"{output}/training/metadata.json",)),
            CallTemplate(
                "results_convergence", label, args, (f"{output}/training/convergence.parquet",)
            ),
            CallTemplate("results_list_entities", label, args, (f"{output}/simulation/costs",)),
            CallTemplate(
                "results_query",
                label,
                {**args, "entity": "costs", "limit": 5},
                (f"{output}/simulation/costs",),
            ),
        ]
    return calls


CATALOG: tuple[CallTemplate, ...] = tuple(
    _deck_calls() + _parquet_calls() + _sql_calls() + _reference_calls() + _results_calls()
)

ALLOWED_TOOLS: tuple[str, ...] = tuple(dict.fromkeys(t.tool for t in CATALOG))

# O catálogo é a barreira principal: uma edição que cole uma tool de escrita aqui
# quebra o import, não só um teste.
_unsafe = [t for t in ALLOWED_TOOLS if is_forbidden_tool(t)]
if _unsafe:
    raise RuntimeError(f"catálogo de carga com tool que grava ou usa a rede: {_unsafe}")


def _is_present(path: Path) -> bool:
    # Diretório vazio conta como ausente, como em queries.preconditions: é o que
    # sobra de um clone sem as fixtures (gitignored).
    if path.is_file():
        return True
    return path.is_dir() and any(path.iterdir())


def _expand(value: Any, fixtures: Path) -> Any:
    if isinstance(value, str):
        posix = fixtures.as_posix().replace("'", "''")
        return value.replace(FIXTURES_POSIX_TOKEN, posix).replace(FIXTURES_TOKEN, str(fixtures))
    if isinstance(value, Mapping):
        return {k: _expand(v, fixtures) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_expand(v, fixtures) for v in value]
    return value


def validate_tools(tools: Iterable[str]) -> list[str]:
    """Nomes sem repetição, na ordem dada.

    Raises:
        ValueError: Se alguma tool não está no mix somente leitura.
    """
    names = list(dict.fromkeys(tools))
    unknown = [t for t in names if t not in ALLOWED_TOOLS]
    if unknown:
        raise ValueError(
            f"tools fora do mix somente leitura: {', '.join(unknown)} "
            f"(permitidas: {', '.join(ALLOWED_TOOLS)})"
        )
    return names


def hints_from_tools(tools: Iterable[Any]) -> dict[str, ToolHints]:
    """Dicas de cada tool no formato do ``list_tools`` do MCP (ou do FastMCP)."""
    hints: dict[str, ToolHints] = {}
    for tool in tools:
        annotations = getattr(tool, "annotations", None)
        hints[tool.name] = ToolHints(
            read_only=getattr(annotations, "readOnlyHint", None) is True,
            open_world=getattr(annotations, "openWorldHint", None) is True,
        )
    return hints


def _reject_reason(
    template: CallTemplate, fixtures: Path, server_tools: Mapping[str, ToolHints] | None
) -> str | None:
    if server_tools is not None:
        hint = server_tools.get(template.tool)
        if hint is None:
            return "tool ausente no servidor"
        if not hint.read_only:
            return "servidor não a anuncia como somente leitura"
        if hint.open_world:
            return "servidor a anuncia com acesso à rede"
    absent = [r for r in template.requires if not _is_present(fixtures / r)]
    if absent:
        return "fonte ausente ou vazia: " + ", ".join(absent)
    return None


def select_specs(
    fixtures_dir: str | Path,
    tools: Iterable[str] | None = None,
    server_tools: Mapping[str, ToolHints] | None = None,
) -> Selection:
    """Chamadas do mix: catálogo filtrado por ``tools``, fontes presentes e dicas do servidor.

    Args:
        fixtures_dir: Raiz das fixtures (vira o workspace do servidor).
        tools: Subconjunto a usar; ``None`` usa todo o catálogo.
        server_tools: Dicas anunciadas pelo servidor. Com elas, uma tool que o
            servidor não declara somente leitura sai do mix; sem elas só vale o catálogo.

    Raises:
        ValueError: Se ``tools`` pede algo fora do mix somente leitura.
    """
    wanted = set(validate_tools(tools)) if tools is not None else None
    fixtures = Path(fixtures_dir).resolve()
    selection = Selection()
    for template in CATALOG:
        if wanted is not None and template.tool not in wanted:
            continue
        reason = _reject_reason(template, fixtures, server_tools)
        if reason is not None:
            selection.excluded.append(Excluded(template.id, template.tool, reason))
            continue
        selection.specs.append(
            CallSpec(template.id, template.tool, _expand(dict(template.arguments), fixtures))
        )
    return selection


def describe_catalog(fixtures_dir: str | Path) -> list[dict[str, Any]]:
    """Tools do catálogo com quantas chamadas estão disponíveis e, se nenhuma, o motivo."""
    selection = select_specs(fixtures_dir)
    available: dict[str, int] = {}
    for spec in selection.specs:
        available[spec.tool] = available.get(spec.tool, 0) + 1
    reasons: dict[str, str] = {}
    for item in selection.excluded:
        reasons.setdefault(item.tool, item.reason)
    return [
        {
            "tool": tool,
            "group": tool_group(tool),
            "calls": available.get(tool, 0),
            "available": available.get(tool, 0) > 0,
            "reason": None if available.get(tool, 0) else reasons.get(tool),
        }
        for tool in ALLOWED_TOOLS
    ]
