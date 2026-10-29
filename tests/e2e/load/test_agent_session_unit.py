"""Testes do isolamento das sessões de agente: nenhuma grava onde outra lê."""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import pytest

from tests.e2e.launcher.providers import ProviderInfo
from tests.e2e.load.agent_cases import AgentSelection
from tests.e2e.load.agent_engine import PreflightResult
from tests.e2e.load.agent_session import AgentSessionRunner, SessionPaths, prepare_session
from tests.e2e.load.agent_setup import denied_tools, session_factory
from tests.e2e.load.fakes import make_case
from tests.e2e.load.mix import ToolHints
from tests.e2e.queries.runner import QueryRunner

SERVER = {
    "command": "novomodelo-mcp.exe",
    "args": ["--x"],
    "env": {
        "NOVOMODELO_MCP_WORKSPACE": "C:/fixtures",
    },
    "timeout": 960000,
    "autoApprove": ["docs_list"],
}
CLAUDE = ProviderInfo("claude", "Claude Code", "claude", True, "C:/bin/claude.exe")
KIRO = ProviderInfo("kiro-cli", "Kiro CLI", "kiro-cli", True, "C:/bin/kiro-cli.exe")


def _session_files(paths: SessionPaths) -> list[Path]:
    return [paths.tmp, paths.state, paths.kiro_workspace, paths.claude_config]


class TestPaths:
    def test_sessions_share_no_file_or_folder(self, tmp_path: Path) -> None:
        sessions = [prepare_session(tmp_path, i, SERVER, "claude") for i in range(3)]
        for a, b in combinations(sessions, 2):
            for mine in _session_files(a):
                for theirs in _session_files(b):
                    assert mine != theirs
                    assert not mine.is_relative_to(theirs) and not theirs.is_relative_to(mine)

    def test_environment_points_only_inside_the_session(self, tmp_path: Path) -> None:
        paths = prepare_session(tmp_path, 0, SERVER, "claude")
        env = paths.env()
        assert set(env) == {
            "NOVOMODELO_MCP_STATE_DIR",
            "TEMP",
            "TMP",
            "TMPDIR",
        }
        assert all(Path(value).is_relative_to(paths.root) for value in env.values())
        assert paths.tmp.is_dir() and paths.state.is_dir()


class TestConfigs:
    def test_kiro_session_gets_its_own_workspace_config(self, tmp_path: Path) -> None:
        paths = prepare_session(tmp_path, 1, SERVER, "kiro-cli")
        config = json.loads(
            (paths.kiro_workspace / ".kiro" / "settings" / "mcp.json").read_text(encoding="utf-8")
        )
        server = config["mcpServers"]["novomodelo"]
        assert server["command"] == "novomodelo-mcp.exe"
        assert server["timeout"] == 960000
        assert server["env"]["NOVOMODELO_MCP_WORKSPACE"] == "C:/fixtures"
        assert server["env"]["TEMP"] == str(paths.tmp)
        assert not paths.claude_config.exists()

    def test_claude_session_gets_its_own_mcp_config(self, tmp_path: Path) -> None:
        paths = prepare_session(tmp_path, 0, SERVER, "claude")
        server = json.loads(paths.claude_config.read_text(encoding="utf-8"))["mcpServers"][
            "novomodelo"
        ]
        assert set(server) == {"command", "args", "env"}
        assert server["env"]["NOVOMODELO_MCP_STATE_DIR"] == str(paths.state)
        assert not paths.kiro_workspace.exists()

    def test_the_shared_definition_is_not_mutated(self, tmp_path: Path) -> None:
        prepare_session(tmp_path, 0, SERVER, "kiro-cli")
        assert SERVER["env"] == {"NOVOMODELO_MCP_WORKSPACE": "C:/fixtures"}


class TestRunner:
    def test_kiro_runs_in_the_session_workspace(self, tmp_path: Path) -> None:
        paths = prepare_session(tmp_path, 0, SERVER, "kiro-cli")
        runner = AgentSessionRunner(KIRO, paths, tmp_path / "fixtures", denied_tools=["x"])
        assert runner.workspace_dir == paths.kiro_workspace

    def test_claude_runs_in_the_fixtures_like_the_esteira(self, tmp_path: Path) -> None:
        paths = prepare_session(tmp_path, 0, SERVER, "claude")
        runner = AgentSessionRunner(CLAUDE, paths, tmp_path / "fixtures")
        assert runner.workspace_dir == (tmp_path / "fixtures").resolve()

    def test_runner_does_not_rewrite_the_fixtures_workspace_config(self, tmp_path: Path) -> None:
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        paths = prepare_session(tmp_path, 0, SERVER, "kiro-cli")
        AgentSessionRunner(KIRO, paths, fixtures)
        assert not (fixtures / ".kiro").exists()


class TestFactory:
    def test_each_session_gets_its_own_runner_and_folder(self, tmp_path: Path) -> None:
        factory = session_factory(CLAUDE, tmp_path, SERVER, tmp_path / "fixtures", None)
        preflight = PreflightResult(AgentSelection(), {})
        first, second = factory(0, preflight), factory(1, preflight)
        assert first is not second
        assert first.paths.root != second.paths.root

    def test_tools_the_server_announces_as_writing_are_denied(self) -> None:
        hints = {
            "docs_list": ToolHints(read_only=True, open_world=False),
            "server_info": ToolHints(read_only=True, open_world=True),
            "deck_edit_json": ToolHints(read_only=False, open_world=False),
        }
        assert denied_tools(hints) == ["deck_edit_json"]
        assert denied_tools(None) == []


class TestMcpStartup:
    """Com N servidores subindo juntos, o limite padrão de subida do kiro-cli estoura."""

    def test_kiro_config_gets_the_startup_timeout_unless_it_has_one(self, tmp_path: Path) -> None:
        def startup(server: dict, index: int) -> int:
            paths = prepare_session(tmp_path, index, server, "kiro-cli")
            config = (paths.kiro_workspace / ".kiro" / "settings" / "mcp.json").read_text(
                encoding="utf-8"
            )
            return json.loads(config)["mcpServers"]["novomodelo"]["initializationTimeout"]

        from tests.e2e.load.client import STARTUP_TIMEOUT_S

        assert startup(SERVER, 0) == int(STARTUP_TIMEOUT_S * 1000)
        assert startup({**SERVER, "initializationTimeout": 5000}, 1) == 5000
        assert "initializationTimeout" not in SERVER


def _fixtures(root: Path) -> Path:
    deck = root / "fixtures" / "newave" / "novomodelo-caso-reduzido"
    deck.mkdir(parents=True)
    (deck / "config.json").write_text('{"a": 1}', encoding="utf-8")
    return (root / "fixtures").resolve()


def _writing_case(fixtures: Path):
    from dataclasses import replace

    case = make_case(
        "deck-edit-json",
        tool="deck_edit_json",
        requires=(str(fixtures / "newave" / "novomodelo-caso-reduzido"),),
    )
    return replace(
        case, query=f"No caso {fixtures / 'newave' / 'novomodelo-caso-reduzido'}, edite"
    )


class TestSandbox:
    """Com caso que grava, cada sessão roda na sua cópia; o servidor só enxerga a cópia."""

    def _plan(self, fixtures: Path):
        from tests.e2e.load.agent_cases import plan_for_cases

        return plan_for_cases(fixtures, [_writing_case(fixtures)])

    def test_the_server_of_each_session_sees_only_its_copy_and_runs_no_solver(
        self, tmp_path: Path
    ) -> None:
        fixtures = _fixtures(tmp_path)
        plan = self._plan(fixtures)
        sessions = [prepare_session(tmp_path / "run", i, SERVER, "claude", plan) for i in range(2)]
        roots = []
        for paths in sessions:
            server = json.loads(paths.claude_config.read_text(encoding="utf-8"))["mcpServers"]
            env = server["novomodelo"]["env"]
            assert env["NOVOMODELO_MCP_WORKSPACE"] == str(paths.sandbox.root)
            assert env["NOVOMODELO_MCP_MAX_JOBS"] == "0"
            assert paths.sandbox.root.is_relative_to(paths.root)
            assert (paths.sandbox.root / "newave/novomodelo-caso-reduzido/config.json").is_file()
            roots.append(paths.sandbox.root)
        assert roots[0] != roots[1]

    def test_kiro_session_config_points_to_the_copy_too(self, tmp_path: Path) -> None:
        fixtures = _fixtures(tmp_path)
        paths = prepare_session(tmp_path / "run", 0, SERVER, "kiro-cli", self._plan(fixtures))
        config = paths.kiro_workspace / ".kiro" / "settings" / "mcp.json"
        env = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["novomodelo"]["env"]
        assert env["NOVOMODELO_MCP_WORKSPACE"] == str(paths.sandbox.root)

    def test_without_writing_cases_the_session_keeps_the_fixtures_workspace(
        self, tmp_path: Path
    ) -> None:
        paths = prepare_session(tmp_path / "run", 0, SERVER, "claude", None)
        env = json.loads(paths.claude_config.read_text(encoding="utf-8"))["mcpServers"][
            "novomodelo"
        ]["env"]
        assert paths.sandbox is None
        assert env["NOVOMODELO_MCP_WORKSPACE"] == "C:/fixtures"
        assert env["NOVOMODELO_MCP_MAX_JOBS"] == "0"

    def test_the_prompt_points_to_the_copy_and_each_execution_starts_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fixtures = _fixtures(tmp_path)
        paths = prepare_session(tmp_path / "run", 0, SERVER, "claude", self._plan(fixtures))
        runner = AgentSessionRunner(CLAUDE, paths, fixtures)
        box = paths.sandbox.root
        seen: list[str] = []
        leftovers: list[bool] = []

        def execute(_self, test_case):
            seen.append(test_case.query)
            leftovers.append((box / "scratch" / "saida.json").exists())
            (box / "scratch" / "saida.json").write_text("{}", encoding="utf-8")
            (box / "newave/novomodelo-caso-reduzido/config.json").write_text(
                "{}", encoding="utf-8"
            )

        monkeypatch.setattr(QueryRunner, "execute", execute)
        case = _writing_case(fixtures)
        runner.execute(case)
        assert str(box / "newave" / "novomodelo-caso-reduzido") in seen[0]
        assert str(fixtures) not in seen[0]
        runner.execute(case)
        assert leftovers == [False, False]
        assert (fixtures / "newave/novomodelo-caso-reduzido/config.json").read_text(
            encoding="utf-8"
        ) == '{"a": 1}'
        paths.sandbox.reset()
        assert not (box / "scratch" / "saida.json").exists()
        assert (box / "newave/novomodelo-caso-reduzido/config.json").read_text(
            encoding="utf-8"
        ) == '{"a": 1}'

    def test_the_copy_time_is_reported_apart(self, tmp_path: Path) -> None:
        fixtures = _fixtures(tmp_path)
        paths = prepare_session(tmp_path / "run", 0, SERVER, "claude", self._plan(fixtures))
        assert AgentSessionRunner(CLAUDE, paths, fixtures).copy_ms is not None
        plain = prepare_session(tmp_path / "run2", 0, SERVER, "claude", None)
        assert AgentSessionRunner(CLAUDE, plain, fixtures).copy_ms is None

    def test_the_factory_registers_the_copies_for_the_summary(self, tmp_path: Path) -> None:
        fixtures = _fixtures(tmp_path)
        sandboxes: list = []
        factory = session_factory(
            CLAUDE, tmp_path / "run", SERVER, fixtures, None, sandboxes=sandboxes
        )
        preflight = PreflightResult(AgentSelection(), {}, sandbox_plan=self._plan(fixtures))
        factory(0, preflight)
        factory(1, preflight)
        assert [box.root.parent.name for box in sandboxes] == ["s0", "s1"]

    def test_with_the_copy_only_barred_writing_tools_are_denied_to_claude(self) -> None:
        hints = {
            "deck_edit_json": ToolHints(read_only=False, open_world=False),
            "case_init": ToolHints(read_only=False, open_world=False),
            "run_start": ToolHints(read_only=False, open_world=False),
            "instalar_novomodelo": ToolHints(read_only=False, open_world=True),
            "docs_list": ToolHints(read_only=True, open_world=False),
        }
        assert denied_tools(hints, sandboxed=True) == ["instalar_novomodelo", "run_start"]
        assert denied_tools(hints, sandboxed=False) == [
            "case_init",
            "deck_edit_json",
            "instalar_novomodelo",
            "run_start",
        ]
