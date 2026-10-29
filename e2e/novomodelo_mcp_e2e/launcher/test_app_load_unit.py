"""Testes das rotas de carga do launcher: segurança, limites, trava única e serving de results/load."""

from __future__ import annotations

import json
import sys
import time
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from novomodelo_mcp_e2e.launcher import app as app_mod
from novomodelo_mcp_e2e.launcher.load_service import LoadRunService
from novomodelo_mcp_e2e.launcher.run_gate import RunGate

LOCAL = "http://127.0.0.1:5175"
HEADER = {"X-Launcher": "1"}
VALID = {"concurrency": 2, "duration_seconds": 10}

_SLEEPS = "import time; time.sleep(120)"
_EXITS = "import json; print(json.dumps({'event': 'saved', 'load_id': '20261024_100000_abc1234'}))"


def _build_client(script: str, gate: RunGate | None = None) -> tuple[TestClient, RunGate]:
    gate = gate or RunGate()
    factory = partial(
        LoadRunService, command_builder=lambda _config: [sys.executable, "-c", script]
    )
    with (
        patch.object(app_mod, "RunGate", return_value=gate),
        patch.object(app_mod, "LoadRunService", factory),
    ):
        return TestClient(app_mod.create_app(), base_url=LOCAL), gate


def _wait_until(predicate, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_mod.create_app(), base_url=LOCAL)


class TestSecurity:
    def test_posts_without_the_launcher_header_are_forbidden(self, client: TestClient) -> None:
        assert client.post("/api/load-runs", json=VALID).status_code == 403
        assert client.post("/api/load-runs/x/cancel").status_code == 403

    def test_foreign_host_is_rejected_on_the_load_routes(self) -> None:
        rebinding = TestClient(app_mod.create_app(), base_url="http://attacker.example:5175")
        assert rebinding.get("/api/load-tools").status_code == 400
        assert rebinding.get("/api/load-runs").status_code == 400

    @pytest.mark.parametrize(
        "extra", [{"command": "calc.exe"}, {"server_command": "x"}, {"warmup": False}]
    )
    def test_unknown_body_fields_are_refused(self, client: TestClient, extra: dict) -> None:
        resp = client.post("/api/load-runs", json={**VALID, **extra}, headers=HEADER)
        assert resp.status_code == 422


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {"concurrency": 0, "duration_seconds": 10},
            {"concurrency": 33, "duration_seconds": 10},
            {"concurrency": 2, "duration_seconds": 0.5},
            {"concurrency": 2, "duration_seconds": 1801},
            {"concurrency": 2, "duration_seconds": 10, "iterations": 0},
            {"concurrency": 2, "duration_seconds": 10, "timeout_seconds": 0},
            {"concurrency": 2, "duration_seconds": 10, "timeout_seconds": 1801},
            {"concurrency": 2, "duration_seconds": 10, "tools": []},
            {"concurrency": 2, "duration_seconds": 10, "tools": ["run_start"]},
            {"concurrency": 2, "duration_seconds": 10, "tools": ["docs_list", "run_status"]},
            {"concurrency": 2, "duration_seconds": 10, "tools": ["server_info"]},
            {"concurrency": 2, "duration_seconds": 10, "tools": ["nao_existe"]},
            {"duration_seconds": 10},
            {"concurrency": 2},
        ],
    )
    def test_out_of_bounds_or_forbidden_values_are_422_and_nothing_starts(
        self, client: TestClient, body: dict
    ) -> None:
        with patch.object(LoadRunService, "start_run") as start:
            resp = client.post("/api/load-runs", json=body, headers=HEADER)
        assert resp.status_code == 422
        start.assert_not_called()

    @pytest.mark.parametrize("raw", ["Infinity", "NaN"])
    def test_infinite_or_nan_numbers_are_422(self, client: TestClient, raw: str) -> None:
        for field in ("duration_seconds", "timeout_seconds"):
            body = {"concurrency": 2, "duration_seconds": 10, field: "@@"}
            payload = json.dumps(body).replace('"@@"', raw)
            resp = client.post(
                "/api/load-runs",
                content=payload,
                headers={**HEADER, "Content-Type": "application/json"},
            )
            assert resp.status_code == 422

    def test_bounds_are_inclusive_and_the_config_reaches_the_service(
        self, client: TestClient
    ) -> None:
        body = {
            "concurrency": 32,
            "duration_seconds": 1800,
            "iterations": 5,
            "tools": ["docs_list", "schema_list"],
            "timeout_seconds": 1800,
        }
        state = SimpleNamespace(to_dict=lambda: {"run_id": "r1", "status": "pending"})
        with patch.object(LoadRunService, "start_run", return_value=state) as start:
            resp = client.post("/api/load-runs", json=body, headers=HEADER)

        assert resp.status_code == 200
        config = start.call_args.args[0]
        assert config.concurrency == 32
        assert config.duration_s == 1800
        assert config.iterations == 5
        assert config.tools == ("docs_list", "schema_list")
        assert config.timeout_s == 1800

    def test_timeout_defaults_to_the_engine_default_when_omitted(self, client: TestClient) -> None:
        state = SimpleNamespace(to_dict=lambda: {"run_id": "r1"})
        with patch.object(LoadRunService, "start_run", return_value=state) as start:
            client.post("/api/load-runs", json=VALID, headers=HEADER)
        assert start.call_args.args[0].timeout_s == app_mod.DEFAULT_TIMEOUT_S


class TestLifecycleRoutes:
    def test_start_poll_and_finish(self) -> None:
        client, _gate = _build_client(_EXITS)
        resp = client.post("/api/load-runs", json=VALID, headers=HEADER)
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        assert _wait_until(
            lambda: client.get(f"/api/load-runs/{run_id}").json()["status"] == "done"
        )
        view = client.get(f"/api/load-runs/{run_id}").json()
        assert view["load_id"] == "20261024_100000_abc1234"
        assert [r["run_id"] for r in client.get("/api/load-runs").json()["runs"]] == [run_id]

    def test_unknown_run_is_404_for_get_and_cancel(self, client: TestClient) -> None:
        assert client.get("/api/load-runs/nao-existe").status_code == 404
        assert client.post("/api/load-runs/nao-existe/cancel", headers=HEADER).status_code == 404

    def test_cancel_stops_the_run_and_frees_the_slot(self) -> None:
        client, gate = _build_client(_SLEEPS)
        run_id = client.post("/api/load-runs", json=VALID, headers=HEADER).json()["run_id"]
        assert _wait_until(
            lambda: client.get(f"/api/load-runs/{run_id}").json()["status"] == "running"
        )

        resp = client.post(f"/api/load-runs/{run_id}/cancel", headers=HEADER)

        assert resp.status_code == 200
        assert resp.json()["cancel_requested"] is True
        assert _wait_until(
            lambda: client.get(f"/api/load-runs/{run_id}").json()["status"] == "cancelled"
        )
        assert gate.owner is None


class TestSharedLock:
    def test_load_is_409_while_an_agent_run_is_active(self) -> None:
        gate = RunGate()
        gate.acquire("agente-1")
        client, _ = _build_client(_EXITS, gate)

        resp = client.post("/api/load-runs", json=VALID, headers=HEADER)

        assert resp.status_code == 409
        assert "agente-1" in resp.json()["detail"]

    def test_second_load_is_409_while_a_load_is_active(self) -> None:
        client, _gate = _build_client(_SLEEPS)
        run_id = client.post("/api/load-runs", json=VALID, headers=HEADER).json()["run_id"]
        try:
            second = client.post("/api/load-runs", json=VALID, headers=HEADER)
            assert second.status_code == 409
        finally:
            client.post(f"/api/load-runs/{run_id}/cancel", headers=HEADER)
            assert _wait_until(
                lambda: client.get(f"/api/load-runs/{run_id}").json()["status"] == "cancelled"
            )


class TestLoadTools:
    def test_lists_the_catalog_with_classes_and_the_barred_tools_with_the_reason(
        self, client: TestClient
    ) -> None:
        data = client.get("/api/load-tools").json()
        rows = {row["tool"]: row for row in data["tools"]}
        assert {"deck_list", "docs_search", "results_query"} <= set(rows)
        keys = {
            "tool",
            "group",
            "calls",
            "available",
            "reason",
            "writes",
            "heavy",
            "default",
            "barred",
        }
        assert all(keys <= set(r) for r in data["tools"])
        assert rows["deck_list"]["default"] is True and rows["deck_list"]["writes"] is False
        assert (
            rows["deck_edit_json"]["writes"] is True and rows["deck_edit_json"]["default"] is False
        )
        assert rows["bridge_check_newave"]["heavy"] is True
        assert rows["run_plan"]["heavy"] is True and rows["run_plan"]["barred"] is False
        for barred in (
            "run_start",
            "run_status",
            "run_logs",
            "run_cancel",
            "server_info",
            "instalar_novomodelo",
        ):
            assert rows[barred]["barred"] is True and rows[barred]["available"] is False
            assert rows[barred]["reason"]
        assert data["limits"]["max_concurrency"] == 32
        assert data["limits"]["max_duration_seconds"] == 1800
        assert data["limits"]["min_concurrency"] == 1

    def test_writing_and_heavy_tools_can_be_requested_by_name(self, client: TestClient) -> None:
        body = {
            "concurrency": 2,
            "duration_seconds": 10,
            "tools": ["deck_edit_json", "bridge_check_newave", "run_plan"],
        }
        with patch.object(
            LoadRunService,
            "start_run",
            return_value=SimpleNamespace(to_dict=lambda: {"run_id": "r1", "status": "pending"}),
        ) as start:
            resp = client.post("/api/load-runs", json=body, headers=HEADER)
        assert resp.status_code == 200
        assert start.call_args.args[0].tools == (
            "deck_edit_json",
            "bridge_check_newave",
            "run_plan",
        )


class TestServingResultsLoad:
    @pytest.fixture
    def results(self, tmp_path: Path):
        results = tmp_path / "results"
        (results / "load").mkdir(parents=True)
        (results / "load" / "index.json").write_text('{"runs": []}', encoding="utf-8")
        (results / "load" / "20261024_100000_abc1234.json").write_text(
            '{"load_id": "x"}', encoding="utf-8"
        )
        (tmp_path / "segredo.json").write_text('{"segredo": true}', encoding="utf-8")
        (tmp_path / "results2").mkdir()
        (tmp_path / "results2" / "segredo.json").write_text("{}", encoding="utf-8")
        with patch.dict(app_mod._DATA_ROOTS, {"results": results.resolve()}):
            yield results

    def test_load_index_and_runs_are_served(self, client: TestClient, results: Path) -> None:
        assert client.get("/data/results/load/index.json").json() == {"runs": []}
        assert client.get("/data/results/load/20261024_100000_abc1234.json").json() == {
            "load_id": "x"
        }

    @pytest.mark.parametrize(
        "path",
        [
            "/data/results/load/..%2F..%2Fsegredo.json",
            "/data/results/load/..%2F..%2Fresults2%2Fsegredo.json",
            "/data/results/load/%2e%2e%2f%2e%2e%2fsegredo.json",
            "/data/results/..%2Fsegredo.json",
        ],
    )
    def test_traversal_out_of_results_stays_blocked(
        self, client: TestClient, results: Path, path: str
    ) -> None:
        resp = client.get(path)
        assert resp.status_code in (403, 404)
        assert "segredo" not in resp.text
