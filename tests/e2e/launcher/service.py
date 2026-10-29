"""Servico de execucao de baterias de teste (estado consultavel por polling).

Reusa a maquinaria de tests/e2e/queries sem reimplementar nada:
  - CasesLoader       -> carrega e filtra os casos (por tags / case_id)
  - ProviderQueryRunner -> dispara cada prompt no provedor de IA escolhido
  - QueryValidator    -> valida tool-call + resultado
  - _build_test_result-> converte (case, result, validation) em TestResult
  - ResultStore       -> cria a bateria, persiste JSON e history.jsonl

Cada disparo da UI vira um "run" com id proprio, executado numa thread de fundo.
O frontend cria o run (POST) e faz polling (GET) ate terminar; ao terminar, a
bateria ja esta gravada e o frontend a le normalmente via /data/*.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from tests.e2e.launcher.provider_runner import ProviderQueryRunner
from tests.e2e.launcher.providers import ProviderInfo
from tests.e2e.launcher.run_gate import RunAlreadyActiveError, RunGate
from tests.e2e.queries.loader import CasesLoader, CasesLoaderError
from tests.e2e.queries.models import QueryTestCase, TestResult
from tests.e2e.queries.preconditions import missing_sources, skipped_result
from tests.e2e.queries.run_queries import _build_test_result
from tests.e2e.queries.runner import EXECUCAO_SO_NO_EXECUTOR
from tests.e2e.queries.store import ResultStore, conjunto_from_filters
from tests.e2e.queries.validator import QueryValidator

__all__ = ["ExecucaoNoHostDesligadaError", "RunAlreadyActiveError", "RunService", "RunState"]

RunStatus = Literal["pending", "running", "done", "error", "cancelled"]

# base_dir = tests/e2e/
_BASE_DIR = Path(__file__).resolve().parent.parent
_CASES_PATH = _BASE_DIR / "queries" / "cases.yaml"
_FIXTURES_DIR = _BASE_DIR / "fixtures"
_RESULTS_DIR = _BASE_DIR / "results"
_METRICS_DIR = _BASE_DIR / "metrics"

_FINISHED: frozenset[str] = frozenset({"done", "error", "cancelled"})


class ExecucaoNoHostDesligadaError(RunAlreadyActiveError):
    """O disparo de agente no host está desligado; a rota responde 409 como num run ativo."""


@dataclass
class RunState:
    """Estado de uma execucao de bateria disparada pela UI.

    Attributes:
        run_id: Id unico do run (nao confundir com batch_id).
        provider: Id do provedor usado ("kiro-cli"/"claude").
        status: pending | running | done | error | cancelled.
        total: Total de casos a rodar (0 ate serem carregados).
        completed: Quantos casos ja terminaram.
        current: Id do caso em execucao, se houver.
        batch_id: Id da bateria gravada ao final (None ate terminar).
        error: Mensagem de erro se status == "error".
        cancel_requested: Parada pedida pela UI; vira "cancelled" quando o
            caso em andamento é interrompido.
        started_at / finished_at: ISO timestamps.
        log: Linhas de progresso curtas para a UI mostrar ao vivo.
        results: O TestResult de cada caso JA terminado, como dict (o mesmo
            registro da bateria gravada), para a UI mostrar o detalhe completo
            de cada teste assim que ele acaba, sem esperar a esteira inteira.
    """

    run_id: str
    provider: str
    status: RunStatus = "pending"
    total: int = 0
    completed: int = 0
    current: str | None = None
    batch_id: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    started_at: str = ""
    finished_at: str | None = None
    log: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "provider": self.provider,
            "status": self.status,
            "total": self.total,
            "completed": self.completed,
            "current": self.current,
            "batch_id": self.batch_id,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "log": self.log[-50:],  # cap: ultimas 50 linhas
            "results": self.results,
        }


class RunService:
    """Gerencia runs de bateria em threads de fundo, com estado consultavel."""

    def __init__(self, gate: RunGate | None = None) -> None:
        self._runs: dict[str, RunState] = {}
        self._runners: dict[str, ProviderQueryRunner] = {}
        self._lock = threading.Lock()
        self._gate = gate or RunGate()

    # ---- consulta -------------------------------------------------------

    def get(self, run_id: str) -> RunState | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._runs.values()]

    # ---- casos ----------------------------------------------------------

    def load_cases(
        self,
        tags: list[str] | None = None,
        case_id: str | None = None,
    ) -> list[QueryTestCase]:
        """Carrega os casos de teste (opcionalmente filtrados).

        Raises:
            CasesLoaderError: Se o YAML nao carrega/valida.
        """
        loader = CasesLoader(_CASES_PATH, _FIXTURES_DIR)
        return loader.load(tags=tags, case_id=case_id)

    def list_cases_meta(self) -> list[dict[str, Any]]:
        """Metadados dos casos para a biblioteca de prompts da UI."""
        cases = self.load_cases()
        return [
            {
                "id": c.id,
                "query": c.query,
                "expected_tool": c.expected.tool,
                "expected_tools": c.expected.tools,
                "tags": list(c.tags),
                "timeout_s": c.timeout_s,
                "requires": list(c.requires),
            }
            for c in cases
        ]

    # ---- execucao -------------------------------------------------------

    def start_run(
        self,
        provider: ProviderInfo,
        tags: list[str] | None = None,
        case_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> RunState:
        """Recusa o disparo: o agente não roda no host, só no executor em container.

        Raises:
            ExecucaoNoHostDesligadaError: Sempre: nenhum agente roda no host.

        Args:
            provider: Provedor ja resolvido (installed=True).
            tags: Filtro por tags (esteira parcial), ou None para a esteira completa.
            case_id: Um unico caso (teste separado), mutuamente util com tags.
            timeout_seconds: Timeout por query.
        """
        raise ExecucaoNoHostDesligadaError(EXECUCAO_SO_NO_EXECUTOR)

    def cancel(self, run_id: str) -> RunState | None:
        """Pede a parada de um run: interrompe o caso atual e não roda os demais.

        Os casos já concluídos aparecem no estado do run, mas nenhuma bateria é
        gravada — uma bateria parcial distorceria o histórico de métricas.

        Returns:
            O estado do run, ou None se o run_id não existe.
        """
        with self._lock:
            state = self._runs.get(run_id)
            if state is None or state.status in _FINISHED:
                return state
            state.cancel_requested = True
            state.log.append("Parada solicitada.")
            runner = self._runners.get(run_id)
        if runner is not None:
            runner.cancel()
        return state

    def _execute(
        self,
        state: RunState,
        provider: ProviderInfo,
        tags: list[str] | None,
        case_id: str | None,
        timeout_seconds: float | None,
    ) -> None:
        """Corpo do run (roda na thread de fundo).

        O ``finally`` é a rede de segurança: os fins normais já liberam a vaga ao
        publicar o estado terminal, e ``release`` é idempotente.
        """
        try:
            self._execute_run(state, provider, tags, case_id, timeout_seconds)
        finally:
            self._gate.release(state.run_id)

    def _execute_run(
        self,
        state: RunState,
        provider: ProviderInfo,
        tags: list[str] | None,
        case_id: str | None,
        timeout_seconds: float | None,
    ) -> None:
        try:
            cases = self.load_cases(tags=tags, case_id=case_id)
        except CasesLoaderError as exc:
            self._fail(state, f"Erro ao carregar casos: {exc}")
            return

        if not cases:
            self._fail(state, "Nenhum caso encontrado com os filtros informados.")
            return

        with self._lock:
            state.total = len(cases)
            state.status = "running"
            state.log.append(f"Rodando {len(cases)} caso(s) via {provider.label}.")

        try:
            runner = ProviderQueryRunner(
                provider=provider,
                timeout_seconds=timeout_seconds,
                workspace_dir=_FIXTURES_DIR,
            )
            validator = QueryValidator()
            store = ResultStore(_RESULTS_DIR, _METRICS_DIR)
        except Exception as exc:  # noqa: BLE001 - reportar qualquer falha de setup
            self._fail(state, f"Falha ao inicializar o runner: {exc}")
            return

        with self._lock:
            self._runners[state.run_id] = runner
        try:
            self._run_cases(
                state, runner, validator, store, cases, conjunto_from_filters(tags, case_id)
            )
        finally:
            with self._lock:
                self._runners.pop(state.run_id, None)
            runner.close()

    def _run_cases(
        self,
        state: RunState,
        runner: ProviderQueryRunner,
        validator: QueryValidator,
        store: ResultStore,
        cases: list[QueryTestCase],
        conjunto: str,
    ) -> None:
        test_results: list[TestResult] = []
        for case in cases:
            with self._lock:
                if state.cancel_requested:
                    break
                state.current = case.id
            missing = missing_sources(case)
            if missing:
                tr = skipped_result(case, missing)
            else:
                tr = self._execute_case(runner, validator, case)
                if tr is None:
                    break
            test_results.append(tr)
            self._record(state, case, tr)

        if state.cancel_requested:
            self._finish_cancelled(state)
            return

        try:
            batch = store.create_batch(test_results, conjunto=conjunto)
            store.save_batch(batch)
            store.append_metrics(batch)
        except Exception as exc:  # noqa: BLE001
            self._fail(state, f"Falha ao gravar a bateria: {exc}")
            return

        with self._lock:
            state.batch_id = batch.batch_id
            state.current = None
            state.status = "done"
            state.finished_at = datetime.now(UTC).isoformat()
            state.log.append(f"Bateria gravada: {batch.batch_id}")
        self._gate.release(state.run_id)

    def _record(self, state: RunState, case: QueryTestCase, tr: TestResult) -> None:
        """Publica no estado do run o resultado de um caso (pass, fail, skip...)."""
        with self._lock:
            state.completed += 1
            state.results.append(asdict(tr))
            state.log.append(
                f"[{state.completed}/{state.total}] {case.id}: {tr.status} ({tr.latency_ms:.0f}ms)"
            )

    def _execute_case(
        self, runner: ProviderQueryRunner, validator: QueryValidator, case: QueryTestCase
    ) -> TestResult | None:
        """Roda e valida um caso; None se a execução foi interrompida pelo cancel."""
        try:
            result = runner.execute(case)
            if result.status == "cancelled":
                return None
            validation = validator.validate(case, result)
            return _build_test_result(case, result, validation)
        except Exception as exc:  # noqa: BLE001 - um caso nao derruba o run
            return TestResult(
                test_id=case.id,
                query=case.query,
                expected_tool=case.expected.tool,
                expected_tools=case.expected.tools,
                actual_tool=None,
                all_tool_calls=[],
                status="fail",
                latency_ms=0.0,
                tool_latency_ms=None,
                mcp_used=False,
                correct_tool=False,
                correct_result=False,
                agent_response="",
                error_message=f"Erro de execucao: {exc}",
                tags=list(case.tags),
                validation_checks=[],
            )

    def _finish_cancelled(self, state: RunState) -> None:
        with self._lock:
            state.status = "cancelled"
            state.current = None
            state.finished_at = datetime.now(UTC).isoformat()
            state.log.append(
                f"Parado após {state.completed}/{state.total} caso(s); bateria não gravada."
            )
        self._gate.release(state.run_id)

    def _fail(self, state: RunState, message: str) -> None:
        with self._lock:
            state.status = "error"
            state.error = message
            state.current = None
            state.finished_at = datetime.now(UTC).isoformat()
            state.log.append(f"ERRO: {message}")
        self._gate.release(state.run_id)
