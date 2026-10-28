"""Testes unitários para o ResultStore.

Este módulo testa:
- save_batch() e load_batch() para persistência de baterias
- _update_index() para manutenção do índice (Req 8.8, 8.9)
- set_baseline() e get_baseline() para baseline (Req 10.5, 10.6)
- list_batches() para listagem ordenada
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.queries.models import (
    BatchMetrics,
    BatchResult,
    GroupMetrics,
    TagMetrics,
    TestResult,
)
from tests.e2e.queries.store import (
    TOOL_GROUPS,
    ResultStore,
    conjunto_from_filters,
    infer_conjunto,
)


@pytest.fixture
def temp_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Cria diretórios temporários para testes."""
    results_dir = tmp_path / "results"
    metrics_dir = tmp_path / "metrics"
    results_dir.mkdir()
    metrics_dir.mkdir()
    return results_dir, metrics_dir


@pytest.fixture
def store(temp_dirs: tuple[Path, Path]) -> ResultStore:
    """Cria um ResultStore com diretórios temporários."""
    results_dir, metrics_dir = temp_dirs
    return ResultStore(results_dir, metrics_dir)


@pytest.fixture
def sample_batch() -> BatchResult:
    """Cria uma BatchResult de exemplo para testes."""
    test_results = [
        TestResult(
            test_id="test-1",
            query="Test query 1",
            expected_tool="deck_list",
            expected_tools=None,
            actual_tool="deck_list",
            all_tool_calls=[{"name": "deck_list", "args": {}}],
            status="pass",
            latency_ms=100.0,
            tool_latency_ms=50.0,
            mcp_used=True,
            correct_tool=True,
            correct_result=True,
            agent_response="Response 1",
            error_message=None,
            tags=["deck", "basic"],
            validation_checks=[],
        ),
        TestResult(
            test_id="test-2",
            query="Test query 2",
            expected_tool="docs_search",
            expected_tools=None,
            actual_tool="read_file",
            all_tool_calls=[{"name": "read_file", "args": {}}],
            status="fail",
            latency_ms=150.0,
            tool_latency_ms=None,
            mcp_used=False,
            correct_tool=False,
            correct_result=False,
            agent_response="Response 2",
            error_message="MCP not used",
            tags=["docs"],
            validation_checks=[],
        ),
    ]

    return BatchResult(
        batch_id="20241215_143052_abc1234",
        timestamp="2024-12-15T14:30:52",
        mcp_version="1.0.0",
        git_commit_sha="abc1234567890",
        environment="test",
        total_tests=2,
        passed=1,
        partial=0,
        failed=1,
        skipped=0,
        timeout=0,
        test_results=test_results,
        metrics=BatchMetrics(
            pct_mcp_used=50.0,
            pct_correct_tool=50.0,
            pct_correct_result=50.0,
            avg_latency_ms=125.0,
            p95_latency_ms=150.0,
        ),
        metrics_by_tag={
            "deck": TagMetrics(total=1, passed=1, failed=0, mcp_used=1, correct_tool=1),
            "docs": TagMetrics(total=1, passed=0, failed=1, mcp_used=0, correct_tool=0),
        },
        metrics_by_group={
            "deck": GroupMetrics(
                total=1,
                pct_pass=100.0,
                pct_mcp_used=100.0,
                pct_correct_tool=100.0,
                avg_latency_ms=100.0,
            ),
            "docs": GroupMetrics(
                total=1, pct_pass=0.0, pct_mcp_used=0.0, pct_correct_tool=0.0, avg_latency_ms=150.0
            ),
        },
    )


class TestToolGroups:
    """Testes para TOOL_GROUPS constant."""

    def test_tool_groups_contains_expected_groups(self):
        """Verifica que todos os grupos esperados estão presentes."""
        groups = set(TOOL_GROUPS.values())
        expected_groups = {"bridge", "deck", "docs", "results", "schema", "run", "case", "meta"}
        assert expected_groups.issubset(groups)

    def test_tool_groups_all_mcp_tools_mapped(self):
        """Verifica que há mapeamento para tools conhecidas."""
        assert TOOL_GROUPS["deck_list"] == "deck"
        assert TOOL_GROUPS["bridge_check_newave"] == "bridge"
        assert TOOL_GROUPS["docs_search"] == "docs"
        assert TOOL_GROUPS["server_info"] == "meta"


class TestSaveBatch:
    """Testes para save_batch()."""

    def test_save_batch_creates_file(self, store: ResultStore, sample_batch: BatchResult):
        """save_batch cria arquivo JSON (Req 8.2)."""
        batch_path = store.save_batch(sample_batch)

        assert batch_path.exists()
        assert batch_path.name == f"{sample_batch.batch_id}.json"

    def test_save_batch_json_content(self, store: ResultStore, sample_batch: BatchResult):
        """save_batch salva conteúdo correto (Req 8.3, 8.4)."""
        batch_path = store.save_batch(sample_batch)

        with open(batch_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["batch_id"] == sample_batch.batch_id
        assert data["timestamp"] == sample_batch.timestamp
        assert data["total_tests"] == 2
        assert data["passed"] == 1
        assert data["failed"] == 1
        assert len(data["test_results"]) == 2

    def test_save_batch_updates_index(self, store: ResultStore, sample_batch: BatchResult):
        """save_batch atualiza index.json (Req 8.8)."""
        store.save_batch(sample_batch)

        assert store.index_path.exists()
        with open(store.index_path, encoding="utf-8") as f:
            index = json.load(f)

        assert len(index["batches"]) == 1
        assert index["batches"][0]["batch_id"] == sample_batch.batch_id


class TestLoadBatch:
    """Testes para load_batch()."""

    def test_load_batch_returns_correct_data(self, store: ResultStore, sample_batch: BatchResult):
        """load_batch retorna dados corretos."""
        store.save_batch(sample_batch)
        loaded = store.load_batch(sample_batch.batch_id)

        assert loaded.batch_id == sample_batch.batch_id
        assert loaded.total_tests == sample_batch.total_tests
        assert loaded.passed == sample_batch.passed
        assert len(loaded.test_results) == len(sample_batch.test_results)

    def test_load_batch_not_found(self, store: ResultStore):
        """load_batch levanta FileNotFoundError para batch inexistente."""
        with pytest.raises(FileNotFoundError, match="Batch not found"):
            store.load_batch("nonexistent_batch_id")


class TestUpdateIndex:
    """Testes para _update_index()."""

    def test_index_contains_required_fields(self, store: ResultStore, sample_batch: BatchResult):
        """Index contém campos obrigatórios (Req 8.9)."""
        store.save_batch(sample_batch)

        with open(store.index_path, encoding="utf-8") as f:
            index = json.load(f)

        batch_entry = index["batches"][0]
        assert "batch_id" in batch_entry
        assert "timestamp" in batch_entry
        assert "version" in batch_entry
        assert "summary" in batch_entry
        assert batch_entry["summary"]["total"] == 2
        assert batch_entry["summary"]["passed"] == 1
        assert batch_entry["summary"]["failed"] == 1

    def test_index_deduplicates_batches(self, store: ResultStore, sample_batch: BatchResult):
        """Index não duplica baterias ao salvar novamente."""
        store.save_batch(sample_batch)
        store.save_batch(sample_batch)

        with open(store.index_path, encoding="utf-8") as f:
            index = json.load(f)

        assert len(index["batches"]) == 1


class TestListBatches:
    """Testes para list_batches()."""

    def test_list_batches_empty(self, store: ResultStore):
        """list_batches retorna lista vazia sem baterias."""
        batches = store.list_batches()
        assert batches == []

    def test_list_batches_sorted_by_timestamp(self, store: ResultStore, sample_batch: BatchResult):
        """list_batches retorna ordenado por timestamp (Req 10.1)."""
        # Save first batch
        store.save_batch(sample_batch)

        # Create and save second batch with later timestamp
        batch2 = BatchResult(
            batch_id="20241216_100000_def5678",
            timestamp="2024-12-16T10:00:00",
            mcp_version="1.0.0",
            git_commit_sha="def5678901234",
            environment="test",
            total_tests=1,
            passed=1,
            partial=0,
            failed=0,
            skipped=0,
            timeout=0,
            test_results=[],
            metrics=BatchMetrics(
                pct_mcp_used=100.0,
                pct_correct_tool=100.0,
                pct_correct_result=100.0,
                avg_latency_ms=50.0,
                p95_latency_ms=50.0,
            ),
            metrics_by_tag={},
            metrics_by_group={},
        )
        store.save_batch(batch2)

        batches = store.list_batches()

        assert len(batches) == 2
        # Most recent first
        assert batches[0]["batch_id"] == "20241216_100000_def5678"
        assert batches[1]["batch_id"] == "20241215_143052_abc1234"


class TestSetBaseline:
    """Testes para set_baseline() (Req 10.5, 10.6)."""

    def test_set_baseline_creates_file(self, store: ResultStore, sample_batch: BatchResult):
        """set_baseline cria baseline.json."""
        store.save_batch(sample_batch)
        store.set_baseline(sample_batch.batch_id)

        assert store.baseline_path.exists()

    def test_set_baseline_content(self, store: ResultStore, sample_batch: BatchResult):
        """set_baseline salva batch_id correto (Req 10.6)."""
        store.save_batch(sample_batch)
        store.set_baseline(sample_batch.batch_id)

        with open(store.baseline_path, encoding="utf-8") as f:
            baseline_data = json.load(f)

        assert baseline_data == {"baselines": {"todos": sample_batch.batch_id}}

    def test_set_baseline_replaces_previous(self, store: ResultStore, sample_batch: BatchResult):
        """set_baseline substitui baseline anterior (Req 10.5)."""
        store.save_batch(sample_batch)
        store.set_baseline(sample_batch.batch_id)

        # Create and save second batch
        batch2 = BatchResult(
            batch_id="20241216_100000_def5678",
            timestamp="2024-12-16T10:00:00",
            mcp_version="1.0.0",
            git_commit_sha="def5678901234",
            environment="test",
            total_tests=1,
            passed=1,
            partial=0,
            failed=0,
            skipped=0,
            timeout=0,
            test_results=[],
            metrics=BatchMetrics(
                pct_mcp_used=100.0,
                pct_correct_tool=100.0,
                pct_correct_result=100.0,
                avg_latency_ms=50.0,
                p95_latency_ms=50.0,
            ),
            metrics_by_tag={},
            metrics_by_group={},
        )
        store.save_batch(batch2)
        store.set_baseline(batch2.batch_id)

        with open(store.baseline_path, encoding="utf-8") as f:
            baseline_data = json.load(f)

        assert baseline_data == {"baselines": {"todos": batch2.batch_id}}

    def test_set_baseline_batch_not_found(self, store: ResultStore):
        """set_baseline levanta FileNotFoundError para batch inexistente."""
        with pytest.raises(FileNotFoundError, match="Batch not found"):
            store.set_baseline("nonexistent_batch_id")


class TestGetBaseline:
    """Testes para get_baseline() (Req 10.5, 10.6)."""

    def test_get_baseline_no_baseline_set(self, store: ResultStore):
        """get_baseline retorna None quando não há baseline."""
        baseline = store.get_baseline()
        assert baseline is None

    def test_get_baseline_returns_batch(self, store: ResultStore, sample_batch: BatchResult):
        """get_baseline retorna BatchResult correta."""
        store.save_batch(sample_batch)
        store.set_baseline(sample_batch.batch_id)

        baseline = store.get_baseline()

        assert baseline is not None
        assert baseline.batch_id == sample_batch.batch_id
        assert baseline.total_tests == sample_batch.total_tests

    def test_get_baseline_missing_batch_file(self, store: ResultStore, sample_batch: BatchResult):
        """get_baseline levanta erro se arquivo da batch foi removido."""
        store.save_batch(sample_batch)
        store.set_baseline(sample_batch.batch_id)

        # Remove the batch file
        batch_path = store.results_dir / f"{sample_batch.batch_id}.json"
        batch_path.unlink()

        with pytest.raises(FileNotFoundError, match="Batch not found"):
            store.get_baseline()


def _result(test_id: str, tool: str | None) -> TestResult:
    return TestResult(
        test_id=test_id,
        query="q",
        expected_tool=tool,
        expected_tools=None,
        actual_tool=tool,
        all_tool_calls=[],
        status="pass",
        latency_ms=1.0,
        tool_latency_ms=None,
        mcp_used=True,
        correct_tool=True,
        correct_result=True,
        agent_response="",
        error_message=None,
        tags=[],
        validation_checks=[],
    )


def _stored_batch(
    store: ResultStore, batch_id: str, results: list[TestResult], **kwargs
) -> BatchResult:
    batch = store.create_batch(results, **kwargs)
    batch.batch_id = batch_id
    store.save_batch(batch)
    return batch


def test_conjunto_from_filters():
    assert conjunto_from_filters(None, None) == "todos"
    assert conjunto_from_filters([], None) == "todos"
    assert conjunto_from_filters(["docs"], None) == "grupo:docs"
    assert conjunto_from_filters(["deck", "bridge", "deck"], None) == "grupo:bridge+deck"
    assert conjunto_from_filters(["docs"], "x") == "pergunta:x"


def test_infer_conjunto():
    assert infer_conjunto([_result("q1", "docs_list")]) == "pergunta:q1"
    assert infer_conjunto([_result("a", "docs_list"), _result("b", "docs_read")]) == "grupo:docs"
    assert infer_conjunto([_result("a", "docs_list"), _result("b", "deck_list")]) == "todos"


def test_create_batch_records_conjunto_in_batch_and_index(store: ResultStore):
    batch = store.create_batch([_result("a", "docs_list")], conjunto="grupo:docs")
    store.save_batch(batch)

    assert store.load_batch(batch.batch_id).conjunto == "grupo:docs"
    assert store.list_batches()[0]["conjunto"] == "grupo:docs"


def test_set_baseline_per_conjunto_keeps_other_conjuntos(store: ResultStore):
    todos = _stored_batch(store, "b_todos", [_result("a", "docs_list"), _result("b", "deck_list")])
    docs = _stored_batch(store, "b_docs", [_result("a", "docs_list")], conjunto="grupo:docs")

    assert store.set_baseline(todos.batch_id) == "todos"
    assert store.set_baseline(docs.batch_id) == "grupo:docs"

    assert store.get_baselines() == {"todos": "b_todos", "grupo:docs": "b_docs"}
    assert store.get_baseline("grupo:docs").batch_id == "b_docs"
    assert store.get_baseline("todos").batch_id == "b_todos"
    assert store.get_baseline("grupo:deck") is None


def test_legacy_baseline_file_maps_to_batch_conjunto(store: ResultStore):
    batch = _stored_batch(store, "b_docs", [_result("a", "docs_list")], conjunto="grupo:docs")
    store.baseline_path.write_text(json.dumps({"batch_id": batch.batch_id}), encoding="utf-8")

    assert store.get_baselines() == {"grupo:docs": "b_docs"}
    assert store.get_baseline().batch_id == "b_docs"


def test_baseline_to_missing_batch_is_ignored(store: ResultStore):
    store.baseline_path.write_text(json.dumps({"batch_id": "sumiu"}), encoding="utf-8")
    assert store.get_baselines() == {}

    store.baseline_path.write_text(json.dumps({"baselines": {"todos": "sumiu"}}), encoding="utf-8")
    assert store.get_baselines() == {}


def test_get_baselines_without_file_is_empty(store: ResultStore):
    assert store.get_baselines() == {}


def test_set_baseline_rejects_conjunto_mismatch(store: ResultStore):
    batch = _stored_batch(store, "b_docs", [_result("a", "docs_list")], conjunto="grupo:docs")
    with pytest.raises(ValueError):
        store.set_baseline(batch.batch_id, "todos")


def test_clear_baseline(store: ResultStore):
    batch = _stored_batch(store, "b_docs", [_result("a", "docs_list")], conjunto="grupo:docs")
    store.set_baseline(batch.batch_id)

    assert store.clear_baseline("grupo:docs") is True
    assert store.get_baselines() == {}
    assert store.clear_baseline("grupo:docs") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
