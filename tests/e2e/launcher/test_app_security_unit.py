"""Testes das proteções do launcher de dev (host, header, limites, path traversal)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.e2e.launcher import app as app_mod
from tests.e2e.launcher.service import RunAlreadyActiveError

LOCAL = "http://127.0.0.1:5175"
HEADER = {"X-Launcher": "1"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_mod.create_app(), base_url=LOCAL)


@pytest.fixture
def fake_provider():
    provider = SimpleNamespace(id="kiro-cli", label="Kiro CLI")
    with patch.object(app_mod, "resolve_provider", return_value=provider):
        yield provider


def test_foreign_host_is_rejected_even_for_reads() -> None:
    rebinding = TestClient(app_mod.create_app(), base_url="http://attacker.example:5175")
    assert rebinding.get("/api/health").status_code == 400
    assert rebinding.get("/api/cases").status_code == 400


def test_post_without_launcher_header_is_forbidden(client: TestClient) -> None:
    assert client.post("/api/runs", json={}).status_code == 403
    assert client.post("/api/runs/x/cancel").status_code == 403


@pytest.mark.parametrize("timeout", [0, -1, 1801])
def test_timeout_outside_bounds_is_rejected(client: TestClient, timeout: float) -> None:
    resp = client.post("/api/runs", json={"timeout_seconds": timeout}, headers=HEADER)
    assert resp.status_code == 422


@pytest.mark.parametrize("raw", ["Infinity", "NaN"])
def test_infinite_or_nan_timeout_is_rejected(client: TestClient, raw: str) -> None:
    resp = client.post(
        "/api/runs",
        content=f'{{"timeout_seconds": {raw}}}',
        headers={**HEADER, "Content-Type": "application/json"},
    )
    assert resp.status_code == 422


def test_second_concurrent_run_gets_409(client: TestClient, fake_provider) -> None:
    with patch(
        "tests.e2e.launcher.service.RunService.start_run",
        side_effect=RunAlreadyActiveError("run abc ainda em andamento"),
    ):
        resp = client.post("/api/runs", json={}, headers=HEADER)
    assert resp.status_code == 409


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
