"""Persistência de resultados de baterias e métricas.

Este módulo implementa o ResultStore que persiste resultados de baterias de testes
em arquivos JSON e mantém o índice e histórico de métricas.

Implements:
- Req 8.1: Batch_Result com ID único no formato {timestamp}_{git_short_sha}
- Req 8.2: Persistência em tests/e2e/results/{batch_id}.json
- Req 8.3: Metadados obrigatórios no Batch_Result
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from tests.e2e.queries.models import (
    BatchMetrics,
    BatchResult,
    GroupMetrics,
    TagMetrics,
    TestResult,
)

__all__ = [
    "ResultStore",
    "TOOL_GROUPS",
    "conjunto_from_filters",
    "infer_conjunto",
]


# Mapeamento de tools MCP para seus grupos (Req 9.3)
TOOL_GROUPS: dict[str, str] = {
    # Bridge tools
    "bridge_check_newave": "bridge",
    "bridge_check_decomp": "bridge",
    "bridge_convert_newave": "bridge",
    "bridge_convert_decomp": "bridge",
    "bridge_compare_newave": "bridge",
    "bridge_compare_decomp": "bridge",
    "bridge_dashboard": "bridge",
    # Deck tools
    "deck_list": "deck",
    "deck_read_json": "deck",
    "deck_read_parquet": "deck",
    "deck_describe_parquet": "deck",
    "deck_edit_json": "deck",
    "deck_edit_parquet": "deck",
    "deck_sql": "deck",
    # Docs tools
    "docs_list": "docs",
    "docs_search": "docs",
    "docs_read": "docs",
    # Results tools
    "results_status": "results",
    "results_convergence": "results",
    "results_query": "results",
    "results_list_entities": "results",
    "results_policy": "results",
    "results_stochastic": "results",
    # Schema tools
    "schema_list": "schema",
    "schema_get": "schema",
    "schema_export": "schema",
    # Run tools
    "run_plan": "run",
    "run_apply": "run",
    "run_start": "run",
    "run_status": "run",
    "run_logs": "run",
    "run_cancel": "run",
    # Case tools
    "case_validate": "case",
    "case_summary": "case",
    "case_init": "case",
    # Meta tools
    "server_info": "meta",
    "solver_version": "meta",
    "instalar_novomodelo": "meta",
}

CONJUNTO_TODOS = "todos"


def conjunto_from_filters(tags: list[str] | None, case_id: str | None) -> str:
    """Conjunto de uma bateria a partir dos filtros com que ela rodou."""
    if case_id:
        return f"pergunta:{case_id}"
    if tags:
        return "grupo:" + "+".join(sorted(set(tags)))
    return CONJUNTO_TODOS


def _group_of(result: TestResult) -> str:
    tool = result.expected_tool
    if tool is None and result.expected_tools:
        tool = result.expected_tools[0]
    return TOOL_GROUPS.get(tool, "other") if tool else "other"


def infer_conjunto(test_results: list[TestResult]) -> str:
    """Conjunto de uma bateria gravada sem o campo, deduzido dos resultados."""
    if len(test_results) == 1:
        return f"pergunta:{test_results[0].test_id}"
    groups = {_group_of(r) for r in test_results}
    if len(groups) == 1:
        return f"grupo:{groups.pop()}"
    return CONJUNTO_TODOS


class ResultStore:
    """Persiste resultados de baterias e métricas.

    O ResultStore é responsável por:
    - Gerar batch_id no formato {timestamp}_{git_sha} (Req 8.1)
    - Salvar Batch_Result em JSON (Req 8.2)
    - Manter índice de todas as baterias (Req 8.8)
    - Manter histórico de métricas em JSONL (Req 9.4)

    Attributes:
        results_dir: Diretório para arquivos de resultados JSON.
        metrics_dir: Diretório para histórico de métricas JSONL.
        index_path: Caminho do arquivo de índice.
        baseline_path: Caminho do arquivo de baseline.
        history_path: Caminho do arquivo de histórico de métricas.
        TOOL_GROUPS: Mapeamento de tools para grupos.

    Example:
        >>> store = ResultStore(results_dir, metrics_dir)
        >>> batch_path = store.save_batch(batch_result)
        >>> loaded = store.load_batch("20241215_143052_abc1234")
    """

    # Mapeamento de tools para grupos (exposto como class var para design conformance)
    TOOL_GROUPS: ClassVar[dict[str, str]] = TOOL_GROUPS

    def __init__(
        self,
        results_dir: Path,
        metrics_dir: Path,
    ) -> None:
        """Inicializa o ResultStore.

        Args:
            results_dir: Diretório para arquivos de resultados JSON.
            metrics_dir: Diretório para histórico de métricas JSONL.
        """
        self.results_dir = Path(results_dir)
        self.metrics_dir = Path(metrics_dir)
        self.index_path = self.results_dir / "index.json"
        self.baseline_path = self.results_dir / "baseline.json"
        self.history_path = self.metrics_dir / "history.jsonl"

        # Cached values for git sha and version
        self._git_sha: str | None = None
        self._version: str | None = None

    def save_batch(self, batch: BatchResult) -> Path:
        """Salva resultado de bateria e atualiza índice.

        Implements:
        - Req 8.2: Persistir em tests/e2e/results/{batch_id}.json
        - Req 8.8: Atualizar índice em tests/e2e/results/index.json

        Args:
            batch: Resultado completo da bateria.

        Returns:
            Caminho do arquivo JSON salvo.
        """
        # Ensure directories exist
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Save batch result as JSON
        batch_path = self.results_dir / f"{batch.batch_id}.json"
        batch_dict = self._batch_to_dict(batch)

        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(batch_dict, f, ensure_ascii=False, indent=2)

        # Update index
        self._update_index(batch)

        return batch_path

    def load_batch(self, batch_id: str) -> BatchResult:
        """Carrega resultado de bateria pelo ID.

        Args:
            batch_id: ID da bateria a carregar.

        Returns:
            BatchResult carregado do arquivo JSON.

        Raises:
            FileNotFoundError: Se o arquivo da bateria não existe.
            ValueError: Se o JSON é inválido ou está incompleto.
        """
        batch_path = self.results_dir / f"{batch_id}.json"

        if not batch_path.exists():
            raise FileNotFoundError(f"Batch not found: {batch_id}")

        with open(batch_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self._dict_to_batch(data)

    def list_batches(self) -> list[dict[str, Any]]:
        """Lista todas as baterias do índice.

        Implements Req 10.1: Lista de todas as baterias executadas, ordenadas
        por data (mais recente primeiro).

        Returns:
            Lista de dicts com metadados de cada bateria.
        """
        if not self.index_path.exists():
            return []

        with open(self.index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        # Return batches sorted by timestamp (most recent first)
        batches = index.get("batches", [])
        return sorted(batches, key=lambda b: b.get("timestamp", ""), reverse=True)

    def conjunto_of(self, batch: BatchResult) -> str:
        """Conjunto gravado na bateria, ou deduzido dos resultados."""
        return batch.conjunto or infer_conjunto(batch.test_results)

    def _read_baseline_map(self) -> dict[str, str]:
        """Mapa conjunto -> batch_id do baseline.json, sem checar as baterias."""
        if not self.baseline_path.exists():
            return {}

        with open(self.baseline_path, encoding="utf-8") as f:
            data = json.load(f)

        baselines = data.get("baselines")
        if isinstance(baselines, dict):
            return {str(k): str(v) for k, v in baselines.items() if v}

        batch_id = data.get("batch_id")
        if not batch_id:
            return {}
        try:
            return {self.conjunto_of(self.load_batch(batch_id)): batch_id}
        except FileNotFoundError:
            return {}

    def _write_baseline_map(self, baselines: dict[str, str]) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        with open(self.baseline_path, "w", encoding="utf-8") as f:
            json.dump({"baselines": baselines}, f, ensure_ascii=False, indent=2)

    def get_baselines(self) -> dict[str, str]:
        """Mapa conjunto -> batch_id; omite baselines cuja bateria não existe."""
        return {
            conjunto: batch_id
            for conjunto, batch_id in self._read_baseline_map().items()
            if (self.results_dir / f"{batch_id}.json").exists()
        }

    def set_baseline(self, batch_id: str, conjunto: str | None = None) -> str:
        """Define uma bateria como baseline do seu conjunto.

        Baselines de outros conjuntos são preservadas.

        Args:
            batch_id: ID da bateria a marcar como baseline.
            conjunto: Conjunto da baseline; default é o da própria bateria.

        Returns:
            O conjunto cuja baseline foi definida.

        Raises:
            FileNotFoundError: Se a bateria especificada não existe.
            ValueError: Se conjunto diverge do conjunto da bateria.
        """
        batch = self.load_batch(batch_id)
        batch_conjunto = self.conjunto_of(batch)
        if conjunto is not None and conjunto != batch_conjunto:
            raise ValueError(
                f"Bateria {batch_id} é do conjunto {batch_conjunto}, "
                f"não de {conjunto}"
            )

        baselines = self._read_baseline_map()
        baselines[batch_conjunto] = batch_id
        self._write_baseline_map(baselines)
        return batch_conjunto

    def clear_baseline(self, conjunto: str) -> bool:
        """Remove a baseline do conjunto; False se não havia."""
        baselines = self._read_baseline_map()
        if conjunto not in baselines:
            return False
        del baselines[conjunto]
        self._write_baseline_map(baselines)
        return True

    def get_baseline(self, conjunto: str | None = None) -> BatchResult | None:
        """Retorna a bateria baseline, se definida.

        Sem conjunto, usa `todos` (ou a única baseline do formato antigo).

        Raises:
            FileNotFoundError: Se o baseline referencia uma bateria que não
                existe mais.
        """
        if not self.baseline_path.exists():
            return None

        with open(self.baseline_path, encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data.get("baselines"), dict):
            batch_id = data["baselines"].get(conjunto or CONJUNTO_TODOS)
        else:
            batch_id = data.get("batch_id")
            if batch_id and conjunto is not None:
                if self.conjunto_of(self.load_batch(batch_id)) != conjunto:
                    return None
        if not batch_id:
            return None

        return self.load_batch(batch_id)

    def _generate_batch_id(self) -> str:
        """Gera batch_id no formato {timestamp}_{git_sha}.

        Implements Req 8.1: ID único no formato {timestamp}_{git_short_sha}.

        Returns:
            String no formato "20241215_143052_abc1234".
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        git_sha = self._get_git_sha()[:7]
        return f"{timestamp}_{git_sha}"

    def _get_git_sha(self) -> str:
        """Obtém SHA do commit atual via git.

        Returns:
            SHA completo do commit atual, ou "unknown" se não disponível.
        """
        if self._git_sha is None:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=Path(__file__).parent,
                )
                if result.returncode == 0:
                    self._git_sha = result.stdout.strip()
                else:
                    self._git_sha = "unknown"
            except Exception:
                self._git_sha = "unknown"
        return self._git_sha

    def _get_version(self) -> str:
        """Obtém versão do pacote cobre-mcp.

        Returns:
            Versão do pacote, ou "unknown" se não disponível.
        """
        if self._version is None:
            try:
                from importlib.metadata import version
                self._version = version("cobre-mcp")
            except Exception:
                self._version = "unknown"
        return self._version

    def _update_index(self, batch: BatchResult) -> None:
        """Atualiza índice com nova bateria.

        Implements Req 8.8 and 8.9: Atualizar índice com metadados da bateria.

        Args:
            batch: Bateria a adicionar ao índice.
        """
        # Load existing index or create new
        if self.index_path.exists():
            with open(self.index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        else:
            index = {"batches": []}

        # Add batch summary to index (Req 8.9)
        batch_summary = {
            "batch_id": batch.batch_id,
            "timestamp": batch.timestamp,
            "version": batch.cobre_mcp_version,
            "conjunto": self.conjunto_of(batch),
            "summary": {
                "total": batch.total_tests,
                "passed": batch.passed,
                "failed": batch.failed,
                "skipped": batch.skipped,
                "timeout": batch.timeout,
            },
        }

        # Remove existing entry with same batch_id if any
        index["batches"] = [
            b for b in index["batches"]
            if b.get("batch_id") != batch.batch_id
        ]

        # Add new batch
        index["batches"].append(batch_summary)

        # Save updated index
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _batch_to_dict(self, batch: BatchResult) -> dict[str, Any]:
        """Converte BatchResult para dict serializável em JSON.

        Args:
            batch: Batch a converter.

        Returns:
            Dict serializável em JSON.
        """
        return {
            "batch_id": batch.batch_id,
            "timestamp": batch.timestamp,
            "cobre_mcp_version": batch.cobre_mcp_version,
            "git_commit_sha": batch.git_commit_sha,
            "environment": batch.environment,
            "conjunto": batch.conjunto,
            "total_tests": batch.total_tests,
            "passed": batch.passed,
            "partial": batch.partial,
            "failed": batch.failed,
            "skipped": batch.skipped,
            "timeout": batch.timeout,
            "test_results": [
                self._test_result_to_dict(tr) for tr in batch.test_results
            ],
            "metrics": dataclasses.asdict(batch.metrics),
            "metrics_by_tag": {
                tag: dataclasses.asdict(m)
                for tag, m in batch.metrics_by_tag.items()
            },
            "metrics_by_group": {
                group: dataclasses.asdict(m)
                for group, m in batch.metrics_by_group.items()
            },
        }

    def _test_result_to_dict(self, result: TestResult) -> dict[str, Any]:
        """Converte TestResult para dict serializável em JSON.

        Args:
            result: Test result a converter.

        Returns:
            Dict serializável em JSON.
        """
        return {
            "test_id": result.test_id,
            "query": result.query,
            "expected_tool": result.expected_tool,
            "expected_tools": result.expected_tools,
            "actual_tool": result.actual_tool,
            "all_tool_calls": result.all_tool_calls,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "tool_latency_ms": result.tool_latency_ms,
            "mcp_used": result.mcp_used,
            "correct_tool": result.correct_tool,
            "correct_result": result.correct_result,
            "agent_response": result.agent_response,
            "error_message": result.error_message,
            "tags": result.tags,
            "validation_checks": result.validation_checks,
        }

    def _dict_to_batch(self, data: dict[str, Any]) -> BatchResult:
        """Converte dict de JSON para BatchResult.

        Args:
            data: Dict carregado do JSON.

        Returns:
            BatchResult reconstruído.

        Raises:
            ValueError: Se campos obrigatórios estão ausentes.
        """
        # Reconstruct test results
        test_results = [
            self._dict_to_test_result(tr)
            for tr in data.get("test_results", [])
        ]

        # Reconstruct metrics
        metrics_data = data.get("metrics", {})
        metrics = BatchMetrics(
            pct_mcp_used=metrics_data.get("pct_mcp_used", 0.0),
            pct_correct_tool=metrics_data.get("pct_correct_tool", 0.0),
            pct_correct_result=metrics_data.get("pct_correct_result", 0.0),
            avg_latency_ms=metrics_data.get("avg_latency_ms", 0.0),
            p95_latency_ms=metrics_data.get("p95_latency_ms", 0.0),
        )

        # Reconstruct metrics by tag
        metrics_by_tag = {}
        for tag, tag_data in data.get("metrics_by_tag", {}).items():
            metrics_by_tag[tag] = TagMetrics(
                total=tag_data.get("total", 0),
                passed=tag_data.get("passed", 0),
                failed=tag_data.get("failed", 0),
                mcp_used=tag_data.get("mcp_used", 0),
                correct_tool=tag_data.get("correct_tool", 0),
            )

        # Reconstruct metrics by group
        metrics_by_group = {}
        for group, group_data in data.get("metrics_by_group", {}).items():
            metrics_by_group[group] = GroupMetrics(
                total=group_data.get("total", 0),
                pct_pass=group_data.get("pct_pass", 0.0),
                pct_mcp_used=group_data.get("pct_mcp_used", 0.0),
                pct_correct_tool=group_data.get("pct_correct_tool", 0.0),
                avg_latency_ms=group_data.get("avg_latency_ms", 0.0),
            )

        return BatchResult(
            batch_id=data["batch_id"],
            timestamp=data["timestamp"],
            cobre_mcp_version=data.get("cobre_mcp_version", "unknown"),
            git_commit_sha=data.get("git_commit_sha", "unknown"),
            environment=data.get("environment", "local"),
            total_tests=data.get("total_tests", 0),
            passed=data.get("passed", 0),
            partial=data.get("partial", 0),
            failed=data.get("failed", 0),
            skipped=data.get("skipped", 0),
            timeout=data.get("timeout", 0),
            test_results=test_results,
            metrics=metrics,
            metrics_by_tag=metrics_by_tag,
            metrics_by_group=metrics_by_group,
            conjunto=data.get("conjunto"),
        )

    def _dict_to_test_result(self, data: dict[str, Any]) -> TestResult:
        """Converte dict de JSON para TestResult.

        Args:
            data: Dict carregado do JSON.

        Returns:
            TestResult reconstruído.
        """
        return TestResult(
            test_id=data.get("test_id", ""),
            query=data.get("query", ""),
            expected_tool=data.get("expected_tool"),
            expected_tools=data.get("expected_tools"),
            actual_tool=data.get("actual_tool"),
            all_tool_calls=data.get("all_tool_calls", []),
            status=data.get("status", "skip"),
            latency_ms=data.get("latency_ms", 0.0),
            tool_latency_ms=data.get("tool_latency_ms"),
            mcp_used=data.get("mcp_used", False),
            correct_tool=data.get("correct_tool", False),
            correct_result=data.get("correct_result", False),
            agent_response=data.get("agent_response", ""),
            error_message=data.get("error_message"),
            tags=data.get("tags", []),
            validation_checks=data.get("validation_checks", []),
        )

    def append_metrics(self, batch: BatchResult) -> None:
        """Adiciona métricas ao histórico JSONL.

        Implements:
        - Req 9.4: Persistir em tests/e2e/metrics/history.jsonl
        - Req 9.5: Record contém batch_id, timestamp, métricas, metrics_by_tag/group
        - Req 9.7: Detectar alertas quando métrica piora >10% vs anterior

        Args:
            batch: Resultado completo da bateria com métricas calculadas.
        """
        import dataclasses

        # Ensure metrics directory exists
        self.metrics_dir.mkdir(parents=True, exist_ok=True)

        # Load previous batch for alert detection
        previous = self._get_previous_batch_metrics()
        alerts = self._detect_alerts(batch, previous)

        # Build metrics record (Req 9.5)
        record = {
            "batch_id": batch.batch_id,
            "timestamp": batch.timestamp,
            "pct_mcp_used": batch.metrics.pct_mcp_used,
            "pct_correct_tool": batch.metrics.pct_correct_tool,
            "pct_correct_result": batch.metrics.pct_correct_result,
            "avg_latency_ms": batch.metrics.avg_latency_ms,
            "metrics_by_tag": {
                tag: dataclasses.asdict(m)
                for tag, m in batch.metrics_by_tag.items()
            },
            "metrics_by_group": {
                group: dataclasses.asdict(m)
                for group, m in batch.metrics_by_group.items()
            },
            "alerts": alerts,
        }

        # Append to JSONL file (Req 9.4)
        with open(self.history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _detect_alerts(
        self,
        current: BatchResult,
        previous: dict[str, Any] | None,
    ) -> dict[str, bool]:
        """Detecta alertas comparando com bateria anterior.

        Implements Req 9.7: WHEN uma métrica piora mais de 10% em relação
        à bateria imediatamente anterior, marcar alert: true para essa métrica.

        Alert logic:
        - For percentages (pct_*): alert if current < previous * 0.9
        - For latency: alert if current > previous * 1.1

        Args:
            current: Bateria atual com métricas calculadas.
            previous: Métricas da bateria anterior (dict from JSONL) ou None.

        Returns:
            Dict com True para métricas que pioraram >10%.
        """
        alerts = {
            "pct_mcp_used": False,
            "pct_correct_tool": False,
            "pct_correct_result": False,
            "avg_latency_ms": False,
        }

        if previous is None:
            return alerts

        # For percentages: alert if current < previous * 0.9 (10% worse)
        for metric in ["pct_mcp_used", "pct_correct_tool", "pct_correct_result"]:
            prev_value = previous.get(metric, 0.0)
            curr_value = getattr(current.metrics, metric)
            if prev_value > 0 and curr_value < prev_value * 0.9:
                alerts[metric] = True

        # For latency: alert if current > previous * 1.1 (10% worse = higher)
        prev_latency = previous.get("avg_latency_ms", 0.0)
        curr_latency = current.metrics.avg_latency_ms
        if prev_latency > 0 and curr_latency > prev_latency * 1.1:
            alerts["avg_latency_ms"] = True

        return alerts

    def _get_previous_batch_metrics(self) -> dict[str, Any] | None:
        """Obtém métricas da bateria anterior do histórico.

        Returns:
            Dict com métricas da última bateria, ou None se não houver histórico.
        """
        history = self.load_metrics_history(limit=1)
        if history:
            return history[0]
        return None

    def load_metrics_history(self, limit: int | None = 20) -> list[dict[str, Any]]:
        """Carrega histórico de métricas do arquivo JSONL.

        Args:
            limit: Número máximo de registros a retornar (mais recentes primeiro).
                   Use None para retornar todos os registros.

        Returns:
            Lista de dicts com métricas, ordenada por timestamp (mais recente primeiro).
        """
        if not self.history_path.exists():
            return []

        records: list[dict[str, Any]] = []
        with open(self.history_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue

        # Sort by timestamp descending (most recent first)
        records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

        # Return limited number of records (or all if limit is None)
        if limit is None:
            return records
        return records[:limit]

    def calculate_trends(self, current: BatchMetrics) -> dict[str, str]:
        """Calcula tendências comparando com últimas 5 baterias.

        Implements Req 9.6: Calcular trend_mcp_used, trend_correct_tool,
        trend_correct_result, trend_latency como 'improving', 'stable', 'degrading'.

        Trend logic:
        - For percentages: improving if current > avg, degrading if current < avg - 5%
        - For latency: improving if current < avg, degrading if current > avg + 5%
        - stable: within 5% of average

        Args:
            current: Métricas da bateria atual.

        Returns:
            Dict com trends: trend_mcp_used, trend_correct_tool, 
            trend_correct_result, trend_latency.
        """
        # Default to stable if no history
        trends = {
            "trend_mcp_used": "stable",
            "trend_correct_tool": "stable",
            "trend_correct_result": "stable",
            "trend_latency": "stable",
        }

        # Load last 5 batches from history
        history = self.load_metrics_history(limit=5)
        if not history:
            return trends

        # Calculate averages for each metric
        def avg(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        avg_mcp_used = avg([h.get("pct_mcp_used", 0.0) for h in history])
        avg_correct_tool = avg([h.get("pct_correct_tool", 0.0) for h in history])
        avg_correct_result = avg([h.get("pct_correct_result", 0.0) for h in history])
        avg_latency = avg([h.get("avg_latency_ms", 0.0) for h in history])

        # Calculate trends for percentage metrics
        # improving: current > avg
        # stable: within 5% of avg
        # degrading: current < avg - 5%
        def calc_pct_trend(current_val: float, avg_val: float) -> str:
            if avg_val == 0:
                return "stable"
            threshold = avg_val * 0.05  # 5% threshold
            if current_val > avg_val:
                return "improving"
            elif current_val < avg_val - threshold:
                return "degrading"
            else:
                return "stable"

        # Calculate trends for latency (inverted - lower is better)
        # improving: current < avg
        # stable: within 5% of avg  
        # degrading: current > avg + 5%
        def calc_latency_trend(current_val: float, avg_val: float) -> str:
            if avg_val == 0:
                return "stable"
            threshold = avg_val * 0.05  # 5% threshold
            if current_val < avg_val:
                return "improving"
            elif current_val > avg_val + threshold:
                return "degrading"
            else:
                return "stable"

        trends["trend_mcp_used"] = calc_pct_trend(
            current.pct_mcp_used, avg_mcp_used
        )
        trends["trend_correct_tool"] = calc_pct_trend(
            current.pct_correct_tool, avg_correct_tool
        )
        trends["trend_correct_result"] = calc_pct_trend(
            current.pct_correct_result, avg_correct_result
        )
        trends["trend_latency"] = calc_latency_trend(
            current.avg_latency_ms, avg_latency
        )

        return trends

    def create_batch(
        self,
        test_results: list[TestResult],
        environment: str = "local",
        conjunto: str | None = None,
    ) -> BatchResult:
        """Cria um BatchResult completo a partir de resultados de testes.

        Gera batch_id, timestamp, e calcula todas as métricas agregadas.

        Implements:
        - Req 8.1: ID único no formato {timestamp}_{git_short_sha}
        - Req 8.3: Metadados obrigatórios no Batch_Result
        - Req 9.1, 9.2, 9.3: Cálculo de métricas agregadas

        Args:
            test_results: Lista de resultados de testes individuais.
            environment: Identificador do ambiente (default: "local").
            conjunto: Escopo da bateria; None deixa conjunto_of deduzir.

        Returns:
            BatchResult completo com métricas calculadas.
        """
        batch_id = self._generate_batch_id()
        timestamp = datetime.now().isoformat()

        # Count status totals (including partial)
        passed = sum(1 for r in test_results if r.status == "pass")
        partial = sum(1 for r in test_results if r.status == "partial")
        failed = sum(1 for r in test_results if r.status == "fail")
        skipped = sum(1 for r in test_results if r.status == "skip")
        timeout = sum(1 for r in test_results if r.status == "timeout")

        # Percentuais só sobre o que rodou: um skip (fonte ausente) não é falha
        # do agente e não pode puxar pct_mcp_used/pct_correct_tool para baixo.
        executed = [r for r in test_results if r.status != "skip"]
        metrics = self._calculate_metrics(executed)
        metrics_by_tag = self._calculate_metrics_by_tag(executed)
        metrics_by_group = self._calculate_metrics_by_group(executed)

        return BatchResult(
            batch_id=batch_id,
            timestamp=timestamp,
            cobre_mcp_version=self._get_version(),
            git_commit_sha=self._get_git_sha(),
            environment=environment,
            total_tests=len(test_results),
            passed=passed,
            partial=partial,
            failed=failed,
            skipped=skipped,
            timeout=timeout,
            test_results=test_results,
            metrics=metrics,
            metrics_by_tag=metrics_by_tag,
            metrics_by_group=metrics_by_group,
            conjunto=conjunto,
        )

    def _calculate_metrics(self, results: list[TestResult]) -> BatchMetrics:
        """Calcula métricas agregadas de uma bateria.

        Implements Req 9.1: pct_mcp_used, pct_correct_tool, pct_correct_result,
        avg_latency_ms, p95_latency_ms.

        Args:
            results: Lista de resultados de testes.

        Returns:
            BatchMetrics com métricas agregadas.
        """
        if not results:
            return BatchMetrics(
                pct_mcp_used=0.0,
                pct_correct_tool=0.0,
                pct_correct_result=0.0,
                avg_latency_ms=0.0,
                p95_latency_ms=0.0,
            )

        total = len(results)

        # Calculate percentages
        mcp_used_count = sum(1 for r in results if r.mcp_used)
        correct_tool_count = sum(1 for r in results if r.correct_tool)
        correct_result_count = sum(1 for r in results if r.correct_result)

        pct_mcp_used = (mcp_used_count / total) * 100
        pct_correct_tool = (correct_tool_count / total) * 100
        pct_correct_result = (correct_result_count / total) * 100

        # Calculate latency metrics
        latencies = [r.latency_ms for r in results]
        avg_latency_ms = sum(latencies) / total

        # Calculate p95 latency
        sorted_latencies = sorted(latencies)
        p95_index = int(0.95 * total)
        # Ensure index is within bounds (at least 0, at most len-1)
        p95_index = min(p95_index, total - 1)
        p95_latency_ms = sorted_latencies[p95_index]

        return BatchMetrics(
            pct_mcp_used=pct_mcp_used,
            pct_correct_tool=pct_correct_tool,
            pct_correct_result=pct_correct_result,
            avg_latency_ms=avg_latency_ms,
            p95_latency_ms=p95_latency_ms,
        )

    def _calculate_metrics_by_tag(
        self, results: list[TestResult]
    ) -> dict[str, TagMetrics]:
        """Calcula métricas agregadas por tag.

        Implements Req 9.2: Para cada tag, totais de passed, failed,
        mcp_used, correct_tool.

        Args:
            results: Lista de resultados de testes.

        Returns:
            Dict mapeando tag -> TagMetrics.
        """
        # Collect all unique tags
        tag_results: dict[str, list[TestResult]] = {}
        for result in results:
            for tag in result.tags:
                if tag not in tag_results:
                    tag_results[tag] = []
                tag_results[tag].append(result)

        # Calculate metrics for each tag
        metrics_by_tag: dict[str, TagMetrics] = {}
        for tag, tag_tests in tag_results.items():
            total = len(tag_tests)
            passed = sum(1 for r in tag_tests if r.status == "pass")
            failed = sum(1 for r in tag_tests if r.status == "fail")
            mcp_used = sum(1 for r in tag_tests if r.mcp_used)
            correct_tool = sum(1 for r in tag_tests if r.correct_tool)

            metrics_by_tag[tag] = TagMetrics(
                total=total,
                passed=passed,
                failed=failed,
                mcp_used=mcp_used,
                correct_tool=correct_tool,
            )

        return metrics_by_tag

    def _calculate_metrics_by_group(
        self, results: list[TestResult]
    ) -> dict[str, GroupMetrics]:
        """Calcula métricas por grupo de tools.

        Implements Req 9.3: Métricas por grupo (bridge_*, deck_*, docs_*,
        results_*, schema_*, run_*, case_*, meta_*, other).

        Uses TOOL_GROUPS to map expected_tool to group. Tests without
        a recognized expected_tool are grouped under "other".

        Args:
            results: Lista de resultados de testes.

        Returns:
            Dict mapeando grupo -> GroupMetrics.
        """
        # Group tests by tool group
        group_results: dict[str, list[TestResult]] = {}

        for result in results:
            # Determine the group from expected_tool or expected_tools
            tool = result.expected_tool
            if tool is None and result.expected_tools:
                # Use first tool from the list
                tool = result.expected_tools[0]

            # Map tool to group, default to "other"
            group = TOOL_GROUPS.get(tool, "other") if tool else "other"

            if group not in group_results:
                group_results[group] = []
            group_results[group].append(result)

        # Calculate metrics for each group
        metrics_by_group: dict[str, GroupMetrics] = {}
        for group, group_tests in group_results.items():
            total = len(group_tests)
            if total == 0:
                continue

            passed = sum(1 for r in group_tests if r.status == "pass")
            mcp_used = sum(1 for r in group_tests if r.mcp_used)
            correct_tool = sum(1 for r in group_tests if r.correct_tool)
            latencies = [r.latency_ms for r in group_tests]

            pct_pass = (passed / total) * 100
            pct_mcp_used = (mcp_used / total) * 100
            pct_correct_tool = (correct_tool / total) * 100
            avg_latency_ms = sum(latencies) / total

            metrics_by_group[group] = GroupMetrics(
                total=total,
                pct_pass=pct_pass,
                pct_mcp_used=pct_mcp_used,
                pct_correct_tool=pct_correct_tool,
                avg_latency_ms=avg_latency_ms,
            )

        return metrics_by_group
