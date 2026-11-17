"""Testes do mix de carga: classes das tools, mix padrão, fontes presentes, dicas do servidor."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from novomodelo_mcp_e2e.load.mix import (
    ALLOWED_TOOLS,
    BARRED_TOOLS,
    CATALOG,
    DEFAULT_TOOLS,
    ToolHints,
    barred_reason,
    describe_catalog,
    hints_from_tools,
    is_forbidden_tool,
    is_heavy_tool,
    select_specs,
    validate_tools,
    writes_files,
)

DETERM = "newave-determ/novomodelo-set-24-reduzido-calibrado-determ-2000"

BARRED = ["run_start", "run_status", "run_logs", "run_cancel", "install_novomodelo", "server_info"]
WRITES = [
    "bridge_convert_newave",
    "bridge_convert_decomp",
    "bridge_compare_newave",
    "bridge_compare_decomp",
    "bridge_dashboard",
    "deck_edit_json",
    "deck_edit_parquet",
    "case_init",
    "schema_export",
    "run_apply",
]
HEAVY = ["bridge_check_newave", "bridge_check_decomp", "bridge_convert_newave", "run_plan"]


def _touch(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    for name in (
        "config.json",
        "penalties.json",
        "scenarios/inflow_history.parquet",
        "system/hydro_geometry.parquet",
    ):
        _touch(tmp_path, f"{DETERM}/{name}")
    for name in (
        "training/metadata.json",
        "training/convergence.parquet",
        "simulation/costs/part.parquet",
    ):
        _touch(tmp_path, f"results/sample_run/{name}")
    return tmp_path


@pytest.fixture
def all_sources(tmp_path: Path) -> Path:
    """Toda fonte que alguma chamada do catálogo exige: um arquivo, ou uma pasta não vazia."""
    for template in CATALOG:
        for source in template.requires:
            _touch(tmp_path, source if Path(source).suffix else f"{source}/x.dat")
    return tmp_path


class TestToolClasses:
    @pytest.mark.parametrize("tool", BARRED)
    def test_solver_runs_and_network_tools_are_barred(self, tool: str) -> None:
        assert is_forbidden_tool(tool)
        assert tool in BARRED_TOOLS

    @pytest.mark.parametrize("tool", BARRED)
    def test_barred_tools_cannot_be_requested_and_the_reason_says_why(self, tool: str) -> None:
        with pytest.raises(ValueError, match="fora do catálogo da carga") as error:
            validate_tools([tool])
        assert barred_reason(tool) in str(error.value)
        with pytest.raises(ValueError):
            select_specs(Path("."), tools=[tool])

    @pytest.mark.parametrize("tool", WRITES)
    def test_writing_tools_are_in_the_catalog_and_marked_for_the_copy(self, tool: str) -> None:
        assert writes_files(tool) and not is_forbidden_tool(tool)
        assert tool in ALLOWED_TOOLS

    @pytest.mark.parametrize("tool", HEAVY)
    def test_bridge_and_run_plan_are_heavy_and_requestable(self, tool: str) -> None:
        assert is_heavy_tool(tool)
        assert validate_tools([tool]) == [tool]

    def test_catalog_holds_no_barred_tool(self) -> None:
        assert not [tool for tool in ALLOWED_TOOLS if is_forbidden_tool(tool)]
        assert not [t.id for t in CATALOG if is_forbidden_tool(t.tool)]

    def test_default_mix_is_only_light_read_only_tools(self) -> None:
        assert DEFAULT_TOOLS
        assert not [t for t in DEFAULT_TOOLS if writes_files(t) or is_heavy_tool(t)]
        assert set(DEFAULT_TOOLS) < set(ALLOWED_TOOLS)

    def test_run_start_reason_names_the_solver_and_the_jobs_lock(self) -> None:
        reason = barred_reason("run_start")
        assert "dispara o solver" in reason and "NOVOMODELO_MCP_MAX_JOBS=0" in reason
        assert "depende de um run" in barred_reason("run_logs")
        assert "usa a rede" in barred_reason("server_info")


class TestSelection:
    def test_without_tools_the_default_mix_is_selected(self, fixtures: Path) -> None:
        selection = select_specs(fixtures)
        tools = {spec.tool for spec in selection.specs}
        assert tools == set(DEFAULT_TOOLS)

    def test_spec_arguments_are_absolute_and_expanded(self, fixtures: Path) -> None:
        selection = select_specs(fixtures, tools=["deck_list", "deck_sql"])
        by_id = {spec.id: spec for spec in selection.specs}
        deck = by_id["deck_list#newave-determ"].arguments["case_dir"]
        assert Path(deck) == (fixtures / DETERM).resolve()
        assert "{FIXTURES" not in str(by_id)
        sql = by_id["deck_sql#inflow-amostra"].arguments["query"]
        assert (fixtures / DETERM).resolve().as_posix() in sql
        assert "\\" not in sql

    def test_bind_points_the_call_to_another_root(self, all_sources: Path, tmp_path: Path) -> None:
        copy = tmp_path / "s0" / "fixtures"
        spec = next(s for s in select_specs(all_sources, ["deck_edit_json"]).specs)
        bound = spec.bind(copy)
        assert Path(bound["path"]) == copy / "newave/novomodelo-mini/config.json"
        assert spec.arguments["path"].startswith(str(all_sources.resolve()))

    def test_case_init_gets_a_new_folder_per_call(self, tmp_path: Path) -> None:
        spec = select_specs(tmp_path, ["case_init"]).specs[0]
        first, second = spec.bind(tmp_path, 1), spec.bind(tmp_path, 2)
        assert first["directory"] != second["directory"]
        assert first["directory"].endswith("1") and second["directory"].endswith("2")

    def test_empty_directory_and_missing_file_are_skipped_with_reason(self, tmp_path: Path) -> None:
        (tmp_path / "newave" / "novomodelo-mini").mkdir(parents=True)
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
        selection = select_specs(
            fixtures, tools=["deck_list", "docs_list", "docs_search"], server_tools=hints
        )
        assert {spec.tool for spec in selection.specs} == {"docs_search"}
        reasons = {item.tool: item.reason for item in selection.excluded}
        assert "somente leitura" in reasons["deck_list"]
        assert "rede" in reasons["docs_list"]

    def test_a_writing_tool_announced_as_writing_stays_in_the_mix(self, all_sources: Path) -> None:
        hints = {"deck_edit_json": ToolHints(read_only=False, open_world=False)}
        selection = select_specs(all_sources, ["deck_edit_json"], server_tools=hints)
        assert [spec.tool for spec in selection.specs] == ["deck_edit_json"]

    def test_tool_missing_on_the_server_is_excluded(self, tmp_path: Path) -> None:
        selection = select_specs(tmp_path, tools=["docs_list"], server_tools={})
        assert selection.specs == []
        assert selection.excluded[0].reason == "tool ausente no servidor"

    def test_describe_catalog_reports_availability_classes_and_barred_tools(
        self, tmp_path: Path
    ) -> None:
        rows = {row["tool"]: row for row in describe_catalog(tmp_path)}
        assert rows["docs_list"]["available"] is True
        assert rows["docs_list"]["default"] is True
        assert rows["deck_list"]["available"] is False
        assert "fonte ausente" in rows["deck_list"]["reason"]
        assert rows["deck_list"]["group"] == "deck"
        assert rows["case_init"]["writes"] is True and rows["case_init"]["default"] is False
        assert rows["case_init"]["available"] is True
        assert rows["run_plan"]["heavy"] is True
        for tool in BARRED_TOOLS:
            assert rows[tool]["barred"] is True and rows[tool]["available"] is False
            assert rows[tool]["reason"] == barred_reason(tool)


def test_hints_from_tools_reads_the_mcp_annotations() -> None:
    tools = [
        SimpleNamespace(
            name="a", annotations=SimpleNamespace(readOnlyHint=True, openWorldHint=False)
        ),
        SimpleNamespace(
            name="b", annotations=SimpleNamespace(readOnlyHint=False, openWorldHint=None)
        ),
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

    def test_every_catalog_tool_is_local_and_read_only_unless_it_writes(self, server_tools) -> None:
        hints = hints_from_tools(server_tools.values())
        missing = [tool for tool in ALLOWED_TOOLS if tool not in hints]
        assert not missing, f"tools do catálogo que o servidor não registra: {missing}"
        offenders = {
            tool: hints[tool]
            for tool in ALLOWED_TOOLS
            if hints[tool].open_world or (not hints[tool].read_only and not writes_files(tool))
        }
        assert not offenders

    def test_barred_tools_are_registered_by_the_server(self, server_tools) -> None:
        assert set(BARRED_TOOLS) <= set(server_tools)

    def test_catalog_arguments_match_the_tool_signatures(self, server_tools) -> None:
        for template in CATALOG:
            schema = server_tools[template.tool].parameters
            known = set(schema.get("properties", {}))
            required = set(schema.get("required", []))
            given = set(template.arguments)
            assert given <= known, f"{template.id}: argumentos desconhecidos {given - known}"
            assert required <= given, f"{template.id}: faltam obrigatórios {required - given}"

    def test_selection_keeps_every_catalog_tool_with_the_server_hints(
        self, server_tools, all_sources: Path
    ) -> None:
        hints = hints_from_tools(server_tools.values())
        selection = select_specs(all_sources, ALLOWED_TOOLS, server_tools=hints)
        assert {spec.tool for spec in selection.specs} == set(ALLOWED_TOOLS)
        assert not [item for item in selection.excluded if "servidor" in item.reason]
