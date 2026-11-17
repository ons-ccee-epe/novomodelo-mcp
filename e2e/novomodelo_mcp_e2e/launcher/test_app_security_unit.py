"""Testes das proteções do launcher de dev (host, header, limites, path traversal)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from novomodelo_mcp_e2e.launcher import app as app_mod
from novomodelo_mcp_e2e.launcher.service import RodadaService, RunAlreadyActiveError

LOCAL = "http://127.0.0.1:5175"
HEADER = {"X-Launcher": "1"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_mod.create_app(), base_url=LOCAL)


def test_foreign_host_is_rejected_even_for_reads() -> None:
    rebinding = TestClient(app_mod.create_app(), base_url="http://attacker.example:5175")
    assert rebinding.get("/api/health").status_code == 400
    assert rebinding.get("/api/cases").status_code == 400


def test_post_without_launcher_header_is_forbidden(client: TestClient) -> None:
    assert client.post("/api/rodadas", json={"mcp": ["sem"]}).status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        {"mcp": ["sem"], "repeticoes": 0},
        {"mcp": ["sem"], "repeticoes": 51},
        {"mcp": ["sem"], "max_minutos": -1},
        {"mcp": ["sem"], "esperar_limite": 0},
        {"mcp": ["sem"], "filtro": "a;b"},
        {"mcp": ["sem"], "rodada": "--completa"},
        {"mcp": ["sem"], "rodada": "../fora"},
        {"mcp": ["sem"], "conjuntos": ["deterministica"]},
        {"mcp": ["sem"], "agentes": ["gpt"]},
        {"mcp": []},
    ],
)
def test_values_outside_the_whitelist_are_422(client: TestClient, body: dict) -> None:
    with patch("subprocess.Popen") as popen:
        resp = client.post("/api/rodadas", json=body, headers=HEADER)
    assert resp.status_code == 422
    popen.assert_not_called()


def test_second_concurrent_run_gets_409(client: TestClient) -> None:
    with patch.object(
        RodadaService, "disparar", side_effect=RunAlreadyActiveError("run abc ainda em andamento")
    ):
        resp = client.post("/api/rodadas", json={"mcp": ["sem"]}, headers=HEADER)
    assert resp.status_code == 409


def test_host_e_origem_continuam_restritos(client: TestClient) -> None:
    foreign = TestClient(app_mod.create_app(), base_url="http://attacker.example:5175")
    assert foreign.get("/api/rodadas").status_code == 400
    assert app_mod._ALLOWED_HOSTS == ["127.0.0.1", "localhost"]
    assert app_mod._ALLOWED_ORIGINS == ["http://127.0.0.1:5174", "http://localhost:5174"]
    preflight = client.options(
        "/api/rodadas",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in preflight.headers


def test_data_prefix_sibling_directory_is_not_served(client: TestClient, tmp_path) -> None:
    results = tmp_path / "results"
    sibling = tmp_path / "results2"
    results.mkdir()
    sibling.mkdir()
    (sibling / "segredo.json").write_text("{}", encoding="utf-8")

    with patch.dict(app_mod._DATA_ROOTS, {"results": results.resolve()}):
        resp = client.get("/data/results/..%2Fresults2%2Fsegredo.json")
    assert resp.status_code in (403, 404)
    assert resp.status_code != 200
