"""Testes das rotas do modo agent da carga: validação, provedor, seleção, casos e capacidade."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.e2e.launcher import app as app_mod
from tests.e2e.launcher.load_service import LoadRunService, build_command
from tests.e2e.load.agent_cases import CaseSelection
from tests.e2e.load.agent_engine import AgentLoadConfig
from tests.e2e.load.fakes import make_case

LOCAL = "http://127.0.0.1:5175"
HEADER = {"X-Launcher": "1"}
AGENT = {"mode": "agent", "concurrency": 2, "duration_seconds": 60}
CLAUDE = SimpleNamespace(id="claude", label="Claude Code")
CASES = [
    make_case("docs-list-all", tool="docs_list", tags=("docs", "list")),
    make_case("deck-edit-json", tool="deck_edit_json", tags=("deck", "edit")),
    make_case("bridge-check", tool="bridge_check_newave", tags=("bridge",)),
    make_case("run-start", tool="run_start", tags=("run",)),
]
STATE = SimpleNamespace(to_dict=lambda: {"run_id": "r1", "status": "pending"})


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_mod.create_app(), base_url=LOCAL)


@pytest.fixture(autouse=True)
def fake_catalog():
    with patch.object(app_mod, "load_cases", return_value=CASES):
        yield


def _post(client: TestClient, body: dict):
    with patch.object(LoadRunService, "start_run", return_value=STATE) as start:
        resp = client.post("/api/load-runs", json=body, headers=HEADER)
    return resp, start


def test_carga_com_agente_nao_sobe_agente_no_host(client: TestClient) -> None:
    fake = SimpleNamespace(stdin=None, stdout=iter(()), wait=lambda: 0)
    with patch("subprocess.Popen", return_value=fake) as popen:
        resp = client.post("/api/load-runs", json=AGENT, headers=HEADER)

    assert resp.status_code == 200
    command = popen.call_args.args[0]
    assert command[1:3] == ["-m", "tests.e2e.load.run"]
    assert command[command.index("--mode") + 1] == "agent"
    assert popen.call_args.kwargs.get("shell") is not True


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {**AGENT, "concurrency": 9},
            {**AGENT, "tools": ["docs_list"]},
            {**AGENT, "provider": "gpt"},
            {**AGENT, "group": "docs", "case_id": "docs-list-all"},
            {**AGENT, "case_id": "-x"},
            {**AGENT, "tags": ["Docs; rm"]},
            {**AGENT, "mode": "outro"},
            {"concurrency": 2, "duration_seconds": 10, "provider": "claude"},
            {"concurrency": 2, "duration_seconds": 10, "group": "docs"},
            {**AGENT, "command": "calc.exe"},
        ],
    )
    def test_invalid_agent_bodies_are_422_and_nothing_starts(
        self, client: TestClient, body: dict
    ) -> None:
        resp, start = _post(client, body)
        assert resp.status_code == 422
        start.assert_not_called()

    @pytest.mark.parametrize("mcp", ["../x.whl", "/tmp/x.whl", "x.whl; ls", "nada"])
    def test_mcp_outside_the_whitelist_is_422(self, client: TestClient, mcp: str) -> None:
        resp, start = _post(client, {**AGENT, "mcp": mcp})
        assert resp.status_code == 422
        start.assert_not_called()

    def test_wheel_without_the_configured_folder_is_422(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NOVOMODELO_LAUNCHER_PASTA_WHEELS", raising=False)
        resp, start = _post(client, {**AGENT, "mcp": "novomodelo_mcp-0.19.0-py3-none-any.whl"})
        assert resp.status_code == 422
        assert "NOVOMODELO_LAUNCHER_PASTA_WHEELS" in resp.json()["detail"]
        start.assert_not_called()

    @pytest.mark.parametrize(
        ("selection", "message"),
        [
            ({"case_id": "nao-existe"}, "caso desconhecido"),
            ({"group": "nope"}, "grupo desconhecido"),
            ({"case_id": "run-start"}, "dispara o solver"),
            ({"group": "run"}, "nenhum caso da seleção"),
        ],
    )
    def test_selection_without_runnable_cases_is_422(
        self, client: TestClient, selection: dict, message: str
    ) -> None:
        resp, start = _post(client, {**AGENT, **selection})
        assert resp.status_code == 422
        assert message in resp.json()["detail"]
        start.assert_not_called()


class TestStart:
    def test_valid_agent_body_reaches_the_service_with_the_default_provider(
        self, client: TestClient
    ) -> None:
        resp, start = _post(
            client, {**AGENT, "group": "docs", "iterations": 1, "timeout_seconds": 90}
        )
        assert resp.status_code == 200
        config = start.call_args.args[0]
        assert isinstance(config, AgentLoadConfig)
        assert config.provider == "claude"
        assert config.mcp is None
        assert config.selection == CaseSelection(group="docs")
        assert (config.concurrency, config.iterations, config.timeout_s) == (2, 1, 90.0)

    def test_agent_cap_is_inclusive(self, client: TestClient) -> None:
        resp, _ = _post(client, {**AGENT, "concurrency": 8})
        assert resp.status_code == 200

    def test_tools_mode_stays_the_default(self, client: TestClient) -> None:
        resp, start = _post(client, {"concurrency": 32, "duration_seconds": 10})
        assert resp.status_code == 200
        assert start.call_args.args[0].to_dict()["mode"] == "tools"


class TestCatalogRoutes:
    def test_load_cases_lists_availability_reasons_and_agent_limits(
        self, client: TestClient
    ) -> None:
        data = client.get("/api/load-cases").json()
        by_id = {c["id"]: c for c in data["cases"]}
        assert by_id["docs-list-all"]["available"] is True
        assert by_id["docs-list-all"]["group"] == "docs"
        assert by_id["deck-edit-json"]["available"] is False
        assert "negada" in by_id["deck-edit-json"]["reason"]
        assert by_id["deck-edit-json"]["writes"] is True
        assert by_id["bridge-check"]["heavy"] is True and by_id["bridge-check"]["available"] is True
        assert by_id["run-start"]["available"] is False
        assert "dispara o solver" in by_id["run-start"]["reason"]
        assert data["limits"]["max_concurrency"] == 8
        assert data["limits"]["default_timeout_seconds"] is None

    def test_capacity_passes_mode_and_provider(self, client: TestClient) -> None:
        with patch.object(
            app_mod, "estimate_capacity", return_value={"recommended": 2}
        ) as estimate:
            resp = client.get("/api/load-capacity", params={"mode": "agent", "provider": "claude"})
        assert resp.status_code == 200
        assert resp.json() == {"recommended": 2}
        assert estimate.call_args.args[:2] == ("agent", "claude")

    @pytest.mark.parametrize(
        ("params", "heavy", "writes"),
        [
            ({"mode": "agent", "case_id": "bridge-check"}, True, False),
            ({"mode": "agent", "group": "docs"}, False, False),
            ({"mode": "agent"}, True, False),
            ({"mode": "tools", "tools": "deck_edit_json,run_plan"}, True, True),
            ({"mode": "tools"}, False, False),
        ],
    )
    def test_capacity_profile_follows_the_selection(
        self, client: TestClient, tmp_path, params: dict, heavy: bool, writes: bool
    ) -> None:
        deck = tmp_path / "newave" / "novomodelo-mini"
        deck.mkdir(parents=True)
        (deck / "config.json").write_text("{}", encoding="utf-8")
        with (
            patch.object(app_mod, "estimate_capacity", return_value={}) as estimate,
            patch.object(app_mod, "_FIXTURES_DIR", tmp_path),
        ):
            resp = client.get("/api/load-capacity", params=params)
        assert resp.status_code == 200
        profile = estimate.call_args.kwargs["profile"]
        assert (profile.heavy, profile.writes) == (heavy, writes)

    @pytest.mark.parametrize(
        "params",
        [
            {"mode": "x"},
            {"mode": "agent", "provider": "gpt"},
            {"mode": "tools", "tools": "run_start"},
            {"mode": "tools", "group": "docs"},
            {"mode": "agent", "tools": "docs_list"},
            {"mode": "agent", "group": "docs", "case_id": "docs-list-all"},
            {"mode": "agent", "case_id": "nao-existe"},
            {"mode": "agent", "group": "Docs; rm"},
        ],
    )
    def test_capacity_rejects_invalid_mode_provider_or_selection(
        self, client: TestClient, params: dict
    ) -> None:
        assert client.get("/api/load-capacity", params=params).status_code == 422

    def test_capacity_of_a_group_with_only_writing_cases_has_no_copy_cost(
        self, client: TestClient
    ) -> None:
        resp = client.get("/api/load-capacity", params={"mode": "agent", "group": "deck"})
        assert resp.status_code == 200
        assert resp.json()["selection"]["writes"] is False

    def test_capacity_answers_without_history(self, client: TestClient, tmp_path) -> None:
        with patch.object(app_mod, "_RESULTS_DIR", tmp_path):
            data = client.get("/api/load-capacity", params={"mode": "tools"}).json()
        assert data["hard_cap"] == 32
        assert data["recommended"] >= 1
        assert data["per_session"]["source"] == "estimativa"

    def test_foreign_host_is_rejected(self) -> None:
        rebinding = TestClient(app_mod.create_app(), base_url="http://attacker.example:5175")
        assert rebinding.get("/api/load-cases").status_code == 400
        assert rebinding.get("/api/load-capacity").status_code == 400


class TestBuildCommand:
    def test_agent_command_carries_mode_provider_selection_and_optional_timeout(self) -> None:
        config = AgentLoadConfig(
            concurrency=2,
            duration_s=120,
            provider="claude",
            selection=CaseSelection(group="docs"),
            iterations=1,
        )
        command = build_command(config)
        assert command[:3] == [sys.executable, "-m", "tests.e2e.load.run"]
        assert command[command.index("--mode") + 1] == "agent"
        assert command[command.index("--provider") + 1] == "claude"
        assert command[command.index("--group") + 1] == "docs"
        assert command[command.index("--iterations") + 1] == "1"
        assert "--timeout" not in command
        assert "--tools" not in command

    @pytest.mark.parametrize(
        ("selection", "flag", "value"),
        [
            (CaseSelection(case_id="docs-list-all"), "--case", "docs-list-all"),
            (CaseSelection(tags=("docs", "list")), "--tags", "docs,list"),
        ],
    )
    def test_case_or_tags_selection(self, selection: CaseSelection, flag: str, value: str) -> None:
        config = AgentLoadConfig(concurrency=1, duration_s=10, selection=selection, timeout_s=45)
        command = build_command(config)
        assert command[command.index(flag) + 1] == value
        assert command[command.index("--timeout") + 1] == "45.0"
        assert "--provider" not in command
        assert "--mcp" not in command

    def test_wheel_is_resolved_inside_the_configured_folder(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wheel = tmp_path / "novomodelo_mcp-0.19.0-py3-none-any.whl"
        wheel.write_bytes(b"")
        monkeypatch.setenv("NOVOMODELO_LAUNCHER_PASTA_WHEELS", str(tmp_path))
        config = AgentLoadConfig(concurrency=1, duration_s=10, mcp=wheel.name)
        command = build_command(config)
        assert command[command.index("--mcp") + 1] == str(wheel.resolve())
        assert build_command(AgentLoadConfig(concurrency=1, duration_s=10, mcp="sem"))[-1] == "sem"
