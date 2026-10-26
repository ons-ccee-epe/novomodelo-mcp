"""Mix de chamadas da carga: catálogo fechado de tools, com parâmetros de fixtures reais.

O catálogo é uma lista fechada (allow-list) e cada tool cai numa de três classes:

- **leve e somente leitura** (``deck_*`` de leitura, ``docs_*``, ``schema_list/get``,
  ``results_*``): o mix padrão, quando a carga não escolhe as tools;
- **grava** (``writes_files``: conversão, comparação, dashboard, edição de deck,
  ``case_init``, ``schema_export``, ``run_apply``): só roda com a cópia das fixtures por
  sessão (``sandbox.py``), e os caminhos dela apontam para a cópia;
- **pesada** (``is_heavy_tool``: ``bridge_*`` e ``run_plan``): sobe o bridge ou a CLI do
  solver a cada chamada, e o limitador cobra mais por sessão.

As que gravam e as pesadas só entram quando pedidas pelo nome. Ficam fora da carga, nos dois
modos, as de ``is_forbidden_tool`` (o solver e os jobs dele, e a rede), com o motivo em
``barred_reason``. Uma tool do catálogo entra no mix só se o servidor a anuncia sem
``openWorldHint`` e, se não for das que gravam, com ``readOnlyHint``.

Os caminhos vêm de ``cases.yaml`` (decks ``cobre-caso-reduzido`` e
``cobre-mar-26-rv2-reduzido``), do README das fixtures (``newave-determ`` e
``results/sample_run``) e dos exemplos nas docstrings das tools. Uma chamada cuja fonte
falta (ou é uma pasta vazia) é pulada, não falha. ``{CALL}`` vira um número por chamada:
``case_init`` recusa uma pasta que já existe, e o ``force`` dele é travado no servidor.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "ALLOWED_TOOLS",
    "BARRED_TOOLS",
    "CATALOG",
    "DEFAULT_TOOLS",
    "CallSpec",
    "CallTemplate",
    "Excluded",
    "Selection",
    "ToolHints",
    "barred_reason",
    "describe_catalog",
    "hints_from_tools",
    "is_forbidden_tool",
    "is_heavy_tool",
    "select_specs",
    "tool_group",
    "validate_tools",
    "writes_files",
]

FIXTURES_TOKEN = "{FIXTURES}"
FIXTURES_POSIX_TOKEN = "{FIXTURES_POSIX}"
CALL_TOKEN = "{CALL}"

_BARRED = re.compile(r"^(run_(start|cancel|status|logs)$|instalar_|server_info$|incluir_pastas$)")
_NETWORK = re.compile(r"^(server_info$|instalar_)")
_WIDENS_WORKSPACE = re.compile(r"^incluir_pastas$")
_SOLVER_RUN = re.compile(r"^run_start$")
_WRITES = re.compile(
    r"_convert_|^bridge_compare_|^bridge_dashboard$|^deck_edit_|^case_init$|^schema_export$"
    r"|^run_apply$"
)
_HEAVY = re.compile(r"^bridge_|^run_plan$")

# As barradas que o servidor registra hoje, para a UI listar com o motivo.
BARRED_TOOLS: tuple[str, ...] = (
    "run_start",
    "run_status",
    "run_logs",
    "run_cancel",
    "server_info",
    "instalar_novomodelo",
    "incluir_pastas",
)

_NEWAVE_AGO = "newave/cobre-caso-reduzido"
_NEWAVE_AGO_SRC = "newave/newave-caso-reduzido"
_DECOMP_MAR = "decomp/cobre-mar-26-rv2-reduzido"
_DECOMP_MAR_SRC = "decomp/decomp-mar-26-rv2-reduzido"
_NEWAVE_DETERM = "newave-determ/cobre-set-24-reduzido-calibrado-determ-2000"
_RESULTS_SAMPLE = "results/sample_run"
_RESULTS_NEWAVE_AGO = "newave/cobre-caso-reduzido/output"
_RESULTS_DECOMP_MAR = "decomp/cobre-mar-26-rv2-reduzido/output"
_SCRATCH = "scratch"

_INFLOW_HISTORY = f"{_NEWAVE_DETERM}/scenarios/inflow_history.parquet"


def is_forbidden_tool(tool: str) -> bool:
    """True para as tools fora da carga nos dois modos: o solver e os jobs dele, e a rede."""
    return _BARRED.search(tool) is not None


def writes_files(tool: str) -> bool:
    """True para as tools que gravam no caso: na carga, só rodam na cópia das fixtures por sessão."""
    return _WRITES.search(tool) is not None


def is_heavy_tool(tool: str) -> bool:
    """True para as tools que sobem o bridge ou a CLI do solver a cada chamada."""
    return _HEAVY.search(tool) is not None


def barred_reason(tool: str) -> str:
    """Por que uma tool de ``is_forbidden_tool`` fica fora da carga."""
    if _NETWORK.search(tool):
        return f"{tool} usa a rede: N sessões repetiriam a consulta externa"
    if _WIDENS_WORKSPACE.search(tool):
        return (
            f"{tool} amplia as pastas que o servidor aceita: a sessão sairia da cópia das "
            "fixtures e alcançaria as originais"
        )
    if _SOLVER_RUN.search(tool):
        return (
            f"{tool} dispara o solver (novomodelo run) destacado do servidor: o run leva minutos "
            "com os núcleos de performance e sobrevive à sessão, e N sessões saturariam a "
            "máquina (a carga mediria o solver, não o servidor); os servidores da carga rodam "
            "com NOVOMODELO_MCP_MAX_JOBS=0 e recusam runs"
        )
    return (
        f"{tool} depende de um run iniciado por run_start, que fica fora da carga: só "
        "mediria o erro de job inexistente"
    )


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

    @property
    def writes(self) -> bool:
        return writes_files(self.tool)


@dataclass(frozen=True)
class CallSpec:
    """Chamada pronta: ``arguments`` com os caminhos das fixtures originais.

    ``bind`` expande de novo o modelo contra outra raiz (a cópia da sessão) e numera a chamada.
    """

    id: str
    tool: str
    arguments: dict[str, Any]
    template: Mapping[str, Any] | None = field(default=None, compare=False, repr=False)

    @property
    def writes(self) -> bool:
        return writes_files(self.tool)

    @property
    def heavy(self) -> bool:
        return is_heavy_tool(self.tool)

    def bind(self, root: Path, call: int = 0) -> dict[str, Any]:
        if self.template is None:
            return self.arguments
        return _expand(dict(self.template), root, call)


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


def _heavy_read_calls() -> list[CallTemplate]:
    return [
        CallTemplate(
            "bridge_check_newave", "newave-ago26", {"src": f"{FIXTURES_TOKEN}/{_NEWAVE_AGO_SRC}"},
            (_NEWAVE_AGO_SRC,),
        ),
        CallTemplate(
            "bridge_check_decomp", "decomp-mar26", {"src": f"{FIXTURES_TOKEN}/{_DECOMP_MAR_SRC}"},
            (_DECOMP_MAR_SRC,),
        ),
        CallTemplate(
            "run_plan", "newave-ago26", {"case_dir": f"{FIXTURES_TOKEN}/{_NEWAVE_AGO}"},
            (f"{_NEWAVE_AGO}/config.json",),
        ),
        CallTemplate(
            "run_plan", "decomp-mar26", {"case_dir": f"{FIXTURES_TOKEN}/{_DECOMP_MAR}"},
            (f"{_DECOMP_MAR}/config.json",),
        ),
    ]


def _write_calls() -> list[CallTemplate]:
    """Chamadas que gravam na cópia da sessão; repetidas em laço, cada uma continua válida.

    As edições regravam o valor que as fixtures já têm, a conversão usa ``force`` (no
    bridge ele não é travado) e os relatórios são sobrescritos.
    """
    deck = f"{FIXTURES_TOKEN}/{_NEWAVE_AGO}"
    scratch = f"{FIXTURES_TOKEN}/{_SCRATCH}"
    config = (f"{_NEWAVE_AGO}/config.json",)
    newave_output = (f"{_RESULTS_NEWAVE_AGO}/training/metadata.json",)
    return [
        CallTemplate(
            "deck_edit_json",
            "newave-ago26/config.json",
            {
                "path": f"{deck}/config.json",
                "changes": [{"path": "training.selection.forward_passes", "value": 4}],
            },
            config,
        ),
        CallTemplate(
            "deck_edit_parquet",
            "newave-ago26/thermal_bounds",
            {
                "path": f"{deck}/constraints/thermal_bounds.parquet",
                "where": {"thermal_id": 0, "stage_id": 0},
                "set_values": {"max_generation_mw": 640.0},
            },
            (f"{_NEWAVE_AGO}/constraints/thermal_bounds.parquet",),
        ),
        CallTemplate(
            "run_apply", "newave-ago26", {"case_dir": deck, "overrides": {"forward_passes": 4}},
            config,
        ),
        CallTemplate(
            "case_init", "1dtoy",
            {"directory": f"{scratch}/case-init/{CALL_TOKEN}", "template": "1dtoy"},
        ),
        CallTemplate("schema_export", "scratch", {"output_dir": f"{scratch}/schemas"}),
        CallTemplate(
            "bridge_convert_newave",
            "newave-ago26",
            {
                "src": f"{FIXTURES_TOKEN}/{_NEWAVE_AGO_SRC}",
                "dst": f"{scratch}/convert-newave",
                "force": True,
            },
            (_NEWAVE_AGO_SRC,),
        ),
        CallTemplate(
            "bridge_convert_decomp",
            "decomp-mar26",
            {
                "src": f"{FIXTURES_TOKEN}/{_DECOMP_MAR_SRC}",
                "dst": f"{scratch}/convert-decomp",
                "force": True,
            },
            (_DECOMP_MAR_SRC,),
        ),
        CallTemplate(
            "bridge_compare_newave",
            "newave-ago26/html",
            {
                "newave_dir": f"{FIXTURES_TOKEN}/{_NEWAVE_AGO_SRC}",
                "output_dir": f"{FIXTURES_TOKEN}/{_RESULTS_NEWAVE_AGO}",
                "fmt": "html",
                "out_dir": f"{scratch}/compare-newave",
            },
            (_NEWAVE_AGO_SRC, *newave_output),
        ),
        CallTemplate(
            "bridge_compare_decomp",
            "decomp-mar26/html",
            {
                "decomp_dir": f"{FIXTURES_TOKEN}/{_DECOMP_MAR_SRC}",
                "output_dir": f"{FIXTURES_TOKEN}/{_RESULTS_DECOMP_MAR}",
                "fmt": "html",
                "out_dir": f"{scratch}/compare-decomp",
            },
            (_DECOMP_MAR_SRC, f"{_RESULTS_DECOMP_MAR}/training/metadata.json"),
        ),
        CallTemplate(
            "bridge_dashboard",
            "newave-ago26",
            {"case_dir": deck, "output": f"{scratch}/dashboard-newave.html"},
            newave_output,
        ),
    ]


CATALOG: tuple[CallTemplate, ...] = tuple(
    _deck_calls()
    + _parquet_calls()
    + _sql_calls()
    + _reference_calls()
    + _results_calls()
    + _heavy_read_calls()
    + _write_calls()
)

ALLOWED_TOOLS: tuple[str, ...] = tuple(dict.fromkeys(t.tool for t in CATALOG))

DEFAULT_TOOLS: tuple[str, ...] = tuple(
    t for t in ALLOWED_TOOLS if not writes_files(t) and not is_heavy_tool(t)
)

# O catálogo é a barreira principal: uma edição que cole aqui uma tool do solver ou da rede
# quebra o import, não só um teste.
_unsafe = [t for t in ALLOWED_TOOLS if is_forbidden_tool(t)]
if _unsafe:
    raise RuntimeError(f"catálogo de carga com tool barrada (solver ou rede): {_unsafe}")


def _is_present(path: Path) -> bool:
    # Diretório vazio conta como ausente, como em queries.preconditions: é o que
    # sobra de um clone sem as fixtures (gitignored).
    if path.is_file():
        return True
    return path.is_dir() and any(path.iterdir())


def _expand(value: Any, fixtures: Path, call: int = 0) -> Any:
    if isinstance(value, str):
        posix = fixtures.as_posix().replace("'", "''")
        return (
            value.replace(FIXTURES_POSIX_TOKEN, posix)
            .replace(FIXTURES_TOKEN, str(fixtures))
            .replace(CALL_TOKEN, str(call))
        )
    if isinstance(value, Mapping):
        return {k: _expand(v, fixtures, call) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_expand(v, fixtures, call) for v in value]
    return value


def validate_tools(tools: Iterable[str]) -> list[str]:
    """Nomes sem repetição, na ordem dada.

    Raises:
        ValueError: Se alguma tool não está no catálogo da carga.
    """
    names = list(dict.fromkeys(tools))
    unknown = [t for t in names if t not in ALLOWED_TOOLS]
    if unknown:
        barred = [t for t in unknown if is_forbidden_tool(t)]
        detail = "; ".join(barred_reason(t) for t in barred)
        raise ValueError(
            f"tools fora do catálogo da carga: {', '.join(unknown)}"
            + (f" ({detail})" if detail else "")
            + f" (permitidas: {', '.join(ALLOWED_TOOLS)})"
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
        # Uma tool tida como de leitura que passe a gravar sairia da cópia por sessão.
        if not hint.read_only and not template.writes:
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
        fixtures_dir: Raiz das fixtures (as originais; a cópia de cada sessão espelha esta).
        tools: Subconjunto a usar; ``None`` usa o mix padrão (``DEFAULT_TOOLS``).
        server_tools: Dicas anunciadas pelo servidor. Com elas, sai do mix a tool que o
            servidor não declara local, ou que grava sem ser das que rodam na cópia.

    Raises:
        ValueError: Se ``tools`` pede algo fora do catálogo.
    """
    wanted = set(validate_tools(tools)) if tools is not None else set(DEFAULT_TOOLS)
    fixtures = Path(fixtures_dir).resolve()
    selection = Selection()
    for template in CATALOG:
        if template.tool not in wanted:
            continue
        reason = _reject_reason(template, fixtures, server_tools)
        if reason is not None:
            selection.excluded.append(Excluded(template.id, template.tool, reason))
            continue
        selection.specs.append(
            CallSpec(
                template.id,
                template.tool,
                _expand(dict(template.arguments), fixtures),
                template=dict(template.arguments),
            )
        )
    return selection


def describe_catalog(fixtures_dir: str | Path) -> list[dict[str, Any]]:
    """Tools do catálogo (quantas chamadas disponíveis, se gravam, se são pesadas, se são do
    mix padrão) e as barradas da carga, com o motivo."""
    selection = select_specs(fixtures_dir, ALLOWED_TOOLS)
    available: dict[str, int] = {}
    for spec in selection.specs:
        available[spec.tool] = available.get(spec.tool, 0) + 1
    reasons: dict[str, str] = {}
    for item in selection.excluded:
        reasons.setdefault(item.tool, item.reason)
    rows = [
        {
            "tool": tool,
            "group": tool_group(tool),
            "calls": available.get(tool, 0),
            "available": available.get(tool, 0) > 0,
            "reason": None if available.get(tool, 0) else reasons.get(tool),
            "writes": writes_files(tool),
            "heavy": is_heavy_tool(tool),
            "default": tool in DEFAULT_TOOLS,
            "barred": False,
        }
        for tool in ALLOWED_TOOLS
    ]
    rows += [
        {
            "tool": tool,
            "group": tool_group(tool),
            "calls": 0,
            "available": False,
            "reason": barred_reason(tool),
            "writes": False,
            "heavy": False,
            "default": False,
            "barred": True,
        }
        for tool in BARRED_TOOLS
    ]
    return rows
