"""Testes do conjunto gravado pelo launcher e das rotas de baseline por conjunto."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from novomodelo_mcp_e2e.launcher import app as app_mod
from novomodelo_mcp_e2e.queries.models import ExpectedResult, QueryTestCase
from novomodelo_mcp_e2e.queries.preconditions import skipped_result
from novomodelo_mcp_e2e.queries.store import ResultStore

LOCAL = "http://127.0.0.1:5175"
HEADER = {"X-Launcher": "1"}
CONJUNTO = "grupo:bridge+deck"


def _case(case_id: str, tags: list[str] | None = None) -> QueryTestCase:
    return QueryTestCase(
        id=case_id,
        query="q",
        expected=ExpectedResult(uses_mcp=True, tool="server_info"),
        tags=tuple(tags or ()),
    )


@pytest.fixture
def store(tmp_path, monkeypatch) -> ResultStore:
    results, metrics = tmp_path / "results", tmp_path / "metrics"
    results.mkdir()
    metrics.mkdir()
    monkeypatch.setattr(app_mod, "_RESULTS_DIR", results)
    monkeypatch.setattr(app_mod, "_METRICS_DIR", metrics)
    return ResultStore(results, metrics)


@pytest.fixture
def client(store: ResultStore) -> TestClient:
    return TestClient(app_mod.create_app(), base_url=LOCAL)


def _save(store: ResultStore, conjunto: str | None, suffix: str = "") -> str:
    case = _case("c1")
    batch = store.create_batch([skipped_result(case, ["x"])], conjunto=conjunto)
    batch.batch_id += suffix
    store.save_batch(batch)
    return batch.batch_id


def test_put_baseline_requires_header(client: TestClient) -> None:
    resp = client.put("/api/baselines/todos", json={"batch_id": "b"})
    assert resp.status_code == 403


def test_delete_baseline_requires_header(client: TestClient) -> None:
    assert client.delete("/api/baselines/todos").status_code == 403


def test_put_baseline_sets_conjunto(client: TestClient, store: ResultStore) -> None:
    batch_id = _save(store, CONJUNTO)

    resp = client.put(
        "/api/baselines/grupo%3Abridge%2Bdeck", json={"batch_id": batch_id}, headers=HEADER
    )

    assert resp.status_code == 200
    assert resp.json() == {"conjunto": CONJUNTO, "batch_id": batch_id}
    assert client.get("/api/baselines").json() == {"baselines": {CONJUNTO: batch_id}}


def test_put_baseline_unknown_batch_is_404(client: TestClient) -> None:
    resp = client.put("/api/baselines/todos", json={"batch_id": "nao-existe"}, headers=HEADER)
    assert resp.status_code == 404


@pytest.mark.parametrize("batch_id", ["../x", "C:/x", "a/b"])
def test_put_baseline_rejects_path_like_batch_id(client: TestClient, batch_id: str) -> None:
    resp = client.put("/api/baselines/todos", json={"batch_id": batch_id}, headers=HEADER)
    assert resp.status_code == 422
    assert client.get("/api/baselines").json() == {"baselines": {}}


def test_put_baseline_wrong_conjunto_is_409(client: TestClient, store: ResultStore) -> None:
    batch_id = _save(store, CONJUNTO)

    resp = client.put("/api/baselines/grupo%3Adocs", json={"batch_id": batch_id}, headers=HEADER)

    assert resp.status_code == 409
    assert client.get("/api/baselines").json() == {"baselines": {}}


def test_delete_baseline_removes_only_that_conjunto(client: TestClient, store: ResultStore) -> None:
    first = _save(store, CONJUNTO)
    second = _save(store, "grupo:docs", suffix="_b")
    for conjunto, batch_id in ((CONJUNTO, first), ("grupo:docs", second)):
        store.set_baseline(batch_id, conjunto)

    resp = client.delete("/api/baselines/grupo%3Abridge%2Bdeck", headers=HEADER)

    assert resp.status_code == 200
    assert resp.json() == {"conjunto": CONJUNTO, "removed": True}
    assert client.get("/api/baselines").json() == {"baselines": {"grupo:docs": second}}
    again = client.delete("/api/baselines/grupo%3Abridge%2Bdeck", headers=HEADER)
    assert again.json() == {"conjunto": CONJUNTO, "removed": False}
