"""Testes da seleção de casos do modo agent: grupos, filtros e o que fica fora da carga."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.e2e.load.agent_cases import (
    CaseSelection,
    case_group,
    case_is_heavy,
    case_writes,
    describe_cases,
    exclusion_reason,
    load_cases,
    plan_for_cases,
    select_cases,
    writes_files,
)
from tests.e2e.load.fakes import make_case
from tests.e2e.load.mix import ToolHints, is_forbidden_tool, is_heavy_tool

READ_ONLY = ToolHints(read_only=True, open_world=False)

DOCS = make_case("docs-list-all", tool="docs_list", tags=("docs", "list"))
SCHEMA = make_case("schema-list-all", tool="schema_list", tags=("schema", "list"))
EDIT = make_case("deck-edit-json", tool="deck_edit_json", tags=("deck", "edit"))
INFO = make_case("server-info-get", tool="server_info", tags=("meta",))
BRIDGE = make_case("bridge-check", tool="bridge_check_newave", tags=("bridge",))
RUN_START = make_case("run-start", tool="run_start", tags=("run",))
RUN_STATUS = make_case("run-status", tool="run_status", tags=("run",))
NO_MCP = make_case("general", tool=None, uses_mcp=False, tags=("general",))
# Grupo pela tool esperada (case), tags de outro assunto: o grupo não segue as tags.
DISAMBIGUATION = make_case(
    "case-vs-docs", tool=None, tools=["case_summary", "docs_list"], tags=("disambiguation",)
)
ALL = [DOCS, SCHEMA, EDIT, INFO, BRIDGE, RUN_START, NO_MCP, DISAMBIGUATION]


class TestGroups:
    def test_group_is_the_one_of_the_expected_tool(self) -> None:
        assert case_group(DOCS) == "docs"
        assert case_group(EDIT) == "deck"

    def test_with_several_accepted_tools_the_first_one_decides(self) -> None:
        assert case_group(DISAMBIGUATION) == "case"

    def test_case_without_tool_is_other(self) -> None:
        assert case_group(NO_MCP) == "other"


class TestExclusions:
    def test_read_only_case_with_its_source_present_runs(self) -> None:
        assert exclusion_reason(DOCS) is None

    def test_writing_case_runs_and_is_marked_for_the_per_session_copy(self) -> None:
        assert exclusion_reason(EDIT) is None
        assert case_writes(EDIT) and not case_writes(DOCS)

    def test_bridge_case_runs_and_is_marked_heavy(self) -> None:
        assert exclusion_reason(BRIDGE) is None
        assert case_is_heavy(BRIDGE) and not case_is_heavy(EDIT)

    def test_network_tool_is_excluded_with_the_reason(self) -> None:
        assert "usa a rede" in exclusion_reason(INFO)

    def test_run_start_is_excluded_because_it_starts_the_solver(self) -> None:
        reason = exclusion_reason(RUN_START)
        assert "dispara o solver" in reason
        assert "NOVOMODELO_MCP_MAX_JOBS=0" in reason

    def test_tools_that_need_a_run_are_excluded_with_the_reason(self) -> None:
        assert "depende de um run iniciado por run_start" in exclusion_reason(RUN_STATUS)

    def test_a_writing_tool_announced_as_writing_by_the_server_still_runs(self) -> None:
        hints = {"deck_edit_json": ToolHints(read_only=False, open_world=False)}
        assert exclusion_reason(EDIT, hints) is None

    def test_case_without_mcp_is_excluded(self) -> None:
        assert "não usa o MCP" in exclusion_reason(NO_MCP)

    def test_any_forbidden_tool_among_the_accepted_ones_excludes_the_case(self) -> None:
        mixed = make_case("mixed", tool=None, tools=["docs_list", "run_cancel"])
        assert "run_cancel" in exclusion_reason(mixed)

    def test_missing_source_excludes_the_case(self, tmp_path: Path) -> None:
        case = make_case("deck-list", tool="deck_list", requires=(str(tmp_path / "ausente"),))
        assert exclusion_reason(case).startswith("fonte ausente ou vazia")

    @pytest.mark.parametrize(
        ("hints", "reason"),
        [
            ({}, "ausente no servidor"),
            ({"docs_list": ToolHints(read_only=False, open_world=False)}, "somente leitura"),
            ({"docs_list": ToolHints(read_only=True, open_world=True)}, "rede"),
        ],
    )
    def test_server_hints_are_a_second_barrier(self, hints: dict, reason: str) -> None:
        assert reason in exclusion_reason(DOCS, hints)

    def test_with_matching_server_hints_the_case_runs(self) -> None:
        assert exclusion_reason(DOCS, {"docs_list": READ_ONLY}) is None


class TestSelection:
    def test_no_filter_selects_every_case_and_reports_the_excluded(self) -> None:
        result = select_cases(ALL, CaseSelection())
        assert [c.id for c in result.cases] == [
            "docs-list-all",
            "schema-list-all",
            "deck-edit-json",
            "bridge-check",
            "case-vs-docs",
        ]
        assert {e.id for e in result.excluded} == {"server-info-get", "run-start", "general"}

    def test_group_filters_by_the_expected_tool_group(self) -> None:
        result = select_cases(ALL, CaseSelection(group="case"))
        assert [c.id for c in result.cases] == ["case-vs-docs"]

    def test_tags_select_cases_with_any_of_them(self) -> None:
        result = select_cases(ALL, CaseSelection(tags=("list", "meta")))
        assert [c.id for c in result.cases] == ["docs-list-all", "schema-list-all"]
        assert [e.id for e in result.excluded] == ["server-info-get"]

    def test_single_case(self) -> None:
        assert [
            c.id for c in select_cases(ALL, CaseSelection(case_id="schema-list-all")).cases
        ] == ["schema-list-all"]

    def test_excluded_single_case_comes_back_empty_with_the_reason(self) -> None:
        result = select_cases(ALL, CaseSelection(case_id="run-start"))
        assert result.cases == []
        assert "dispara o solver" in result.excluded[0].reason

    @pytest.mark.parametrize(
        ("selection", "message"),
        [
            (CaseSelection(case_id="nao-existe"), "caso desconhecido"),
            (CaseSelection(group="nope"), "grupo desconhecido"),
            (CaseSelection(tags=("nenhuma",)), "nenhum caso com as tags"),
        ],
    )
    def test_unknown_selection_is_refused(self, selection: CaseSelection, message: str) -> None:
        with pytest.raises(ValueError, match=message):
            select_cases(ALL, selection)

    def test_only_one_selector_is_accepted(self) -> None:
        with pytest.raises(ValueError, match="só um"):
            CaseSelection(case_id="a", group="docs")

    def test_blank_tags_mean_no_tag_filter(self) -> None:
        assert CaseSelection(tags=(" ", "")).tags is None


class TestRealCatalog:
    """Contra o ``cases.yaml`` e o servidor do checkout: as barreiras não divergem."""

    def test_every_case_is_eligible_or_has_a_reason(self, tmp_path: Path) -> None:
        described = describe_cases(load_cases(tmp_path))
        assert described
        for item in described:
            assert item["available"] is (item["reason"] is None)

    def test_no_eligible_case_expects_a_forbidden_tool(self, tmp_path: Path) -> None:
        for case in select_cases(load_cases(tmp_path), CaseSelection()).cases:
            tools = case.expected.tools or [case.expected.tool]
            assert not any(is_forbidden_tool(t) for t in tools), case.id

    def test_writing_cases_name_a_destination_under_the_container_folder(
        self, tmp_path: Path
    ) -> None:
        from tests.e2e.executor.container import PASTA_ESTUDOS

        writing = [c for c in load_cases(tmp_path) if case_writes(c)]
        assert writing
        for case in writing:
            assert exclusion_reason(case) is None, case.id
            assert f"{PASTA_ESTUDOS}/" in case.query or "{caso:" in case.query, case.id

    def test_every_tool_the_server_announces_as_writing_is_copied_or_barred(self) -> None:
        from novomodelo_mcp.server import build_server

        for tool in build_server()._tool_manager.list_tools():
            hints = tool.annotations
            if hints.readOnlyHint is False:
                assert writes_files(tool.name) or is_forbidden_tool(tool.name), tool.name
            if hints.openWorldHint is True:
                assert is_forbidden_tool(tool.name), tool.name
            if writes_files(tool.name):
                assert hints.readOnlyHint is False, tool.name

    def test_heavy_tools_exist_on_the_server(self) -> None:
        from novomodelo_mcp.server import build_server

        names = {tool.name for tool in build_server()._tool_manager.list_tools()}
        heavy = {name for name in names if is_heavy_tool(name)}
        assert {"bridge_check_newave", "bridge_check_decomp", "run_plan"} <= heavy

    def test_only_solver_runs_network_and_cases_without_mcp_stay_out(self, tmp_path: Path) -> None:
        excluded = select_cases(load_cases(tmp_path), CaseSelection()).excluded
        for item in excluded:
            tools = item.tool.split("/")
            assert item.reason.startswith(("fonte ausente", "não usa o MCP")) or any(
                is_forbidden_tool(t) for t in tools
            ), item


class TestSandboxPlan:
    def test_a_selection_without_writing_cases_copies_nothing(self, tmp_path: Path) -> None:
        plan = plan_for_cases(tmp_path, [DOCS, BRIDGE])
        assert not plan.enabled and plan.subtrees == ()

    def test_the_copy_holds_the_case_folders_cited_in_prompts_and_sources(
        self, tmp_path: Path
    ) -> None:
        deck = tmp_path / "newave" / "novomodelo-mini"
        (deck / "output").mkdir(parents=True)
        (deck / "config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "decomp" / "outro").mkdir(parents=True)
        dashboard = make_case(
            "dashboard",
            tool="bridge_dashboard",
            requires=(str(deck / "output"),),
        )
        dashboard = replace(dashboard, query=f"Gere o dashboard de {deck}?")
        missing = make_case("ausente", tool="deck_list")
        missing = replace(missing, query=f"Liste {tmp_path / 'nonexistent'}")
        plan = plan_for_cases(tmp_path, [dashboard, missing, DOCS])
        assert plan.enabled
        assert plan.subtrees == ("newave/novomodelo-mini",)
        assert plan.copy_bytes == 2
