"""Testes do mix de carga: só tools somente leitura, fontes presentes, dicas do servidor."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.e2e.load.mix import (
    ALLOWED_TOOLS,
    CATALOG,
    ToolHints,
    describe_catalog,
    hints_from_tools,
    is_forbidden_tool,
    select_specs,
    validate_tools,
)

DETERM = "newave-determ/cobre-set-24-reduzido-calibrado-determ-2000"

WRITE_OR_SOLVER_TOOLS = [
    "run_plan",
    "run_apply",
    "run_start",
    "run_status",
    "run_logs",
    "run_cancel",
    "bridge_convert_newave",
    "bridge_convert_decomp",
    "bridge_compare_newave",
    "bridge_dashboard",
    "deck_edit_json",
    "deck_edit_parquet",
    "case_init",
    "schema_export",
    "instalar_novomodelo",
    "server_info",
]


def _touch(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    for name in ("config.json", "penalties.json", "scenarios/inflow_history.parquet",
                 "system/hydro_geometry.parquet"):
        _touch(tmp_path, f"{DETERM}/{name}")
    for name in ("training/metadata.json", "training/convergence.parquet",
                 "simulation/costs/part.parquet"):
        _touch(tmp_path, f"results/sample_run/{name}")
    return tmp_path


class TestForbiddenTools:
    @pytest.mark.parametrize("tool", WRITE_OR_SOLVER_TOOLS)
    def test_write_solver_and_network_tools_are_forbidden(self, tool: str) -> None:
        assert is_forbidden_tool(tool)

    @pytest.mark.parametrize("tool", WRITE_OR_SOLVER_TOOLS)
    def test_forbidden_tools_cannot_be_requested(self, tool: str) -> None:
        with pytest.raises(ValueError, match="fora do mix somente leitura"):
            validate_tools([tool])
        with pytest.raises(ValueError):
            select_specs(Path("."), tools=[tool])

    def test_catalog_holds_no_forbidden_tool(self) -> None:
        assert not [tool for tool in ALLOWED_TOOLS if is_forbidden_tool(tool)]
        assert not [t.id for t in CATALOG if is_forbidden_tool(t.tool)]


class TestSelection:
    def test_all_sources_present_selects_deck_docs_schema_and_results(self, fixtures: Path) -> None:
        selection = select_specs(fixtures)
        tools = {spec.tool for spec in selection.specs}
        assert tools == set(ALLOWED_TOOLS)

    def test_spec_arguments_are_absolute_and_expanded(self, fixtures: Path) -> None:
        selection = select_specs(fixtures, tools=["deck_list", "deck_sql"])
        by_id = {spec.id: spec for spec in selection.specs}
        deck = by_id["deck_list#newave-determ"].arguments["case_dir"]
        assert Path(deck) == (fixtures / DETERM).resolve()
        assert "{FIXTURES" not in str(by_id)
        sql = by_id["deck_sql#inflow-amostra"].arguments["query"]
        assert (fixtures / DETERM).resolve().as_posix() in sql
        assert "\\" not in sql

    def test_empty_directory_and_missing_file_are_skipped_with_reason(self, tmp_path: Path) -> None:
        (tmp_path / "newave" / "cobre-caso-reduzido").mkdir(parents=True)
        selection = select_specs(tmp_path, tools=["deck_list", "deck_read_json"])
        assert selection.specs == []
        reasons = {item.id: item.reason for item in selection.excluded}
        assert "fonte ausente ou vazia" in reasons["deck_list#newave-ago26"]
        assert "config.json" in reasons["deck_read_json#newave-ago26/config.json"]

    def test_tools_filter_limits_the_mix(self, fixtures: Path) -> None:
        selection = select_specs(fixtures, tools=["docs_search", "schema_list"])
        assert {spec.tool for spec in selection.specs} == {"docs_search", "schema_list"}

    def test_reference_tools_need_no_fixtures(self, tmp_path: Path) -> None:
        selection = select_specs(tmp_path, tools=["docs_list", "docs_search", "docs_read"])
        assert len(selection.specs) == 4
        assert selection.excluded == []

    def test_server_hints_drop_a_tool_that_is_not_read_only(self, fixtures: Path) -> None:
        hints = {
            "deck_list": ToolHints(read_only=False, open_world=False),
            "docs_list": ToolHints(read_only=True, open_world=True),
            "docs_search": ToolHints(read_only=True, open_world=False),
        }
        selection = select_specs(fixtures, tools=["deck_list", "docs_list", "docs_search"],
                                 server_tools=hints)
        assert {spec.tool for spec in selection.specs} == {"docs_search"}
        reasons = {item.tool: item.reason for item in selection.excluded}
        assert "somente leitura" in reasons["deck_list"]
        assert "rede" in reasons["docs_list"]

    def test_tool_missing_on_the_server_is_excluded(self, tmp_path: Path) -> None:
        selection = select_specs(tmp_path, tools=["docs_list"], server_tools={})
        assert selection.specs == []
        assert selection.excluded[0].reason == "tool ausente no servidor"

    def test_describe_catalog_reports_availability_and_reason(self, tmp_path: Path) -> None:
        rows = {row["tool"]: row for row in describe_catalog(tmp_path)}
        assert rows["docs_list"]["available"] is True
        assert rows["deck_list"]["available"] is False
        assert "fonte ausente" in rows["deck_list"]["reason"]
        assert rows["deck_list"]["group"] == "deck"


def test_hints_from_tools_reads_the_mcp_annotations() -> None:
    tools = [
        SimpleNamespace(name="a", annotations=SimpleNamespace(readOnlyHint=True, openWorldHint=False)),
        SimpleNamespace(name="b", annotations=SimpleNamespace(readOnlyHint=False, openWorldHint=None)),
        SimpleNamespace(name="c", annotations=None),
    ]
    hints = hints_from_tools(tools)
    assert hints["a"] == ToolHints(True, False)
    assert hints["b"] == ToolHints(False, False)
    assert hints["c"] == ToolHints(False, False)


@pytest.fixture(scope="module")
def server_tools():
    server_module = pytest.importorskip("novomodelo_mcp.server")
    return {tool.name: tool for tool in server_module.build_server()._tool_manager.list_tools()}


class TestAgainstTheRealServer:
    """O servidor é construído em processo (sem subir stdio nem tocar a rede)."""

    def test_every_allowed_tool_is_read_only_and_local(self, server_tools) -> None:
        hints = hints_from_tools(server_tools.values())
        missing = [tool for tool in ALLOWED_TOOLS if tool not in hints]
        assert not missing, f"tools do catálogo que o servidor não registra: {missing}"
        offenders = {
            tool: hints[tool]
            for tool in ALLOWED_TOOLS
            if not hints[tool].read_only or hints[tool].open_world
        }
        assert not offenders

    def test_catalog_arguments_match_the_tool_signatures(self, server_tools) -> None:
        for template in CATALOG:
            schema = server_tools[template.tool].parameters
            known = set(schema.get("properties", {}))
            required = set(schema.get("required", []))
            given = set(template.arguments)
            assert given <= known, f"{template.id}: argumentos desconhecidos {given - known}"
            assert required <= given, f"{template.id}: faltam obrigatórios {required - given}"

    def test_selection_keeps_every_catalog_tool_with_the_server_hints(
        self, server_tools, fixtures: Path
    ) -> None:
        hints = hints_from_tools(server_tools.values())
        selection = select_specs(fixtures, server_tools=hints)
        assert {spec.tool for spec in selection.specs} == set(ALLOWED_TOOLS)
        assert not [item for item in selection.excluded if "servidor" in item.reason]
