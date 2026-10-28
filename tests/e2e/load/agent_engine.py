"""Motor da carga do modo agent: N sessões de agente rodando casos do ``cases.yaml`` em laço.

Fases: ``preflight`` (provedor, casos e servidor MCP do agente, sem gastar tokens),
``starting`` (pasta e runner de cada sessão, criados em sequência antes de qualquer
agente rodar), ``running`` (cada sessão roda um caso por vez, em laço, até a duração
ou as iterações) e ``finishing`` (ao fim da janela nenhuma sessão começa caso novo; os
casos em curso terminam, limitados pelo timeout do próprio caso).

Cada execução tem dois resultados separados: o de transporte (``ok``: o agente
completou; ``timeout``; ``error``: exceção, agente sem resposta ou erro da API), que
alimenta a taxa de erro e a latência, e o da validação da esteira (``pass``,
``partial``, ``fail``), que alimenta a taxa de aprovação. Um ``fail`` é uma execução
completa: misturá-lo aos erros faria a latência mentir.
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from tests.e2e.load.agent_cases import (
    AgentSelection,
    CaseSelection,
    case_group,
)
from tests.e2e.load.engine import (
    MAX_DURATION_S,
    MAX_ITERATIONS,
    MAX_TIMEOUT_S,
    MIN_CONCURRENCY,
    MIN_DURATION_S,
    LoadError,
)
from tests.e2e.load.mix import ToolHints
from tests.e2e.load.resources import ResourceSampler
from tests.e2e.load.stats import LiveStats, Outcome, Sample
from tests.e2e.queries.mcp_workspace import SERVER_NAME
from tests.e2e.queries.models import QueryResult, QueryTestCase, TestResult
from tests.e2e.queries.validator import QueryValidator, classify_tool

__all__ = [
    "AGENT_BUCKET_SECONDS",
    "AgentLoadConfig",
    "AgentLoadRunner",
    "AgentOutcome",
    "AgentSample",
    "CaseRunner",
    "MAX_AGENT_CONCURRENCY",
    "PROVIDERS",
    "PreflightResult",
    "agent_failure",
]

AgentPhase = Literal["preflight", "starting", "running", "finishing"]

PROVIDERS: tuple[str, ...] = ("kiro-cli", "claude")

# Cada sessão é um CLI de agente + o seu servidor MCP e consome tokens do provedor;
# acima disto o limite de taxa do provedor domina a medição.
MAX_AGENT_CONCURRENCY = 8
# Um caso leva dezenas de segundos: buckets de 1 s ficariam quase todos vazios.
AGENT_BUCKET_SECONDS = 5.0
PROGRESS_INTERVAL_S = 1.0
LIVE_SERIES_WINDOW = 60
_JOIN_POLL_S = 0.5
_ERROR_CHARS = 300


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True)
class AgentLoadConfig:
    """Parâmetros da carga do modo agent, validados na criação.

    ``iterations`` é por sessão (casos executados). ``timeout_s`` None usa o
    ``timeout_s`` de cada caso no ``cases.yaml``. ``provider`` None escolhe o primeiro
    instalado, como a esteira.
    """

    concurrency: int
    duration_s: float
    provider: str | None = None
    selection: CaseSelection = field(default_factory=CaseSelection)
    iterations: int | None = None
    timeout_s: float | None = None

    mode = "agent"

    def __post_init__(self) -> None:
        if not isinstance(self.concurrency, int) or isinstance(self.concurrency, bool):
            raise ValueError("sessões simultâneas deve ser um inteiro")
        if not MIN_CONCURRENCY <= self.concurrency <= MAX_AGENT_CONCURRENCY:
            raise ValueError(
                f"sessões simultâneas fora de {MIN_CONCURRENCY}..{MAX_AGENT_CONCURRENCY} "
                "no modo agent"
            )
        if not _is_number(self.duration_s) or not math.isfinite(self.duration_s):
            raise ValueError("duração deve ser um número finito")
        if not MIN_DURATION_S <= self.duration_s <= MAX_DURATION_S:
            raise ValueError(f"duração fora de {MIN_DURATION_S:g}..{MAX_DURATION_S:g} s")
        if self.iterations is not None and (
            not isinstance(self.iterations, int)
            or isinstance(self.iterations, bool)
            or not 1 <= self.iterations <= MAX_ITERATIONS
        ):
            raise ValueError(f"iterações fora de 1..{MAX_ITERATIONS}")
        if self.timeout_s is not None and (
            not _is_number(self.timeout_s)
            or not math.isfinite(self.timeout_s)
            or not 0 < self.timeout_s <= MAX_TIMEOUT_S
        ):
            raise ValueError(f"timeout fora de (0, {MAX_TIMEOUT_S:g}] s")
        if self.provider is not None and self.provider not in PROVIDERS:
            raise ValueError(
                f"provedor desconhecido: {self.provider} (aceitos: {', '.join(PROVIDERS)})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "provider": self.provider,
            "concurrency": self.concurrency,
            "duration_seconds": self.duration_s,
            "iterations": self.iterations,
            "timeout_seconds": self.timeout_s,
            "selection": self.selection.to_dict(),
        }


@dataclass(frozen=True)
class AgentSample:
    """Uma execução de caso concluída; ``started_s`` conta a partir do início da carga."""

    case_id: str
    group: str
    session: int
    started_s: float
    latency_ms: float
    outcome: Outcome
    status: str
    tool_calls: int = 0
    mcp_calls: int = 0
    error: str | None = None

    def as_sample(self) -> Sample:
        return Sample(self.case_id, self.started_s, self.latency_ms, self.outcome, self.error)


@dataclass
class PreflightResult:
    """O que o pré-voo decidiu: os casos, as dicas das tools do servidor do agente e o plano
    da cópia das fixtures por sessão (``sandbox.SandboxPlan``; None ou desligado = sem cópia)."""

    selection: AgentSelection
    server_tools: Mapping[str, ToolHints] | None = None
    sandbox_plan: Any = None


class CaseRunner(Protocol):
    def execute(self, test_case: QueryTestCase) -> QueryResult: ...

    def cancel(self) -> None: ...

    def close(self) -> None: ...


RunnerFactory = Callable[[int, PreflightResult], CaseRunner]
Preflight = Callable[[], PreflightResult]


@dataclass
class AgentOutcome:
    """Tudo o que a carga do modo agent produziu; ``store.build_agent_record`` monta o JSON."""

    config: AgentLoadConfig
    selection: AgentSelection
    samples: list[AgentSample]
    sessions: list[dict[str, Any]]
    duration_s: float
    setup_s: float
    started_at: str
    ended_at: str
    interrupted: bool = False
    abandoned_calls: int = 0
    resource_samples: list[dict[str, Any]] | None = None
    server_tools: Mapping[str, ToolHints] | None = None
    sandbox_plan: Any = None


def _json_events(stdout: str):
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def _claude_mcp_unavailable(event: dict[str, Any]) -> str | None:
    """Status do servidor no evento ``init`` do claude, se ele não conectou."""
    servers = event.get("mcp_servers")
    if not isinstance(servers, list):
        return None
    status = next(
        (s.get("status") for s in servers if isinstance(s, dict) and s.get("name") == SERVER_NAME),
        "ausente",
    )
    if status == "connected":
        return None
    return f"o servidor MCP não conectou no agente (status: {status}): o caso rodou sem as tools"


def _claude_failure(stdout: str) -> str | None:
    for event in _json_events(stdout):
        if event.get("type") == "system" and event.get("subtype") == "init":
            unavailable = _claude_mcp_unavailable(event)
            if unavailable:
                return unavailable
        if event.get("type") == "result" and event.get("is_error"):
            detail = event.get("result") or event.get("subtype") or "erro sem detalhe"
            return f"o agente terminou com erro: {detail}"
    return None


def agent_failure(result: QueryResult) -> str | None:
    """Motivo de uma execução completa que não serve para validar o agente, ou None.

    Um erro da API (autenticação, limite de taxa) termina o CLI sem tool-call e sem
    resposta, e um servidor MCP que não conectou deixa o agente sem as tools; na esteira
    os dois viram ``fail``, mas na carga são o sinal de sobrecarga que se quer separar de
    "escolheu a tool errada". Do stream do claude saem os dois; do kiro-cli, só a
    ausência de resposta.
    """
    claude_failure = _claude_failure(result.stdout or "")
    if claude_failure:
        return claude_failure[:_ERROR_CHARS]
    if result.tool_calls or (result.agent_response or "").strip():
        return None
    tail = " ".join((result.stderr or "").split())[-200:]
    return ("o agente terminou sem resposta" + (f" (stderr: {tail})" if tail else ""))[
        :_ERROR_CHARS
    ]


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:_ERROR_CHARS]


class AgentLoadRunner:
    """Executa a carga do modo agent; ``request_stop`` cancela tudo (seguro de outra thread)."""

    def __init__(
        self,
        config: AgentLoadConfig,
        preflight: Preflight,
        runner_factory: RunnerFactory,
        build_result: Callable[[QueryTestCase, QueryResult, Any], TestResult],
        validator: QueryValidator | None = None,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        resource_sampler: ResourceSampler | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._cfg = config
        self._preflight = preflight
        self._factory = runner_factory
        self._build_result = build_result
        self._validator = validator or QueryValidator()
        self._on_progress = on_progress
        self._sampler = resource_sampler
        self._clock = clock

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._done = threading.Event()
        self._interrupted = False

        self._phase: AgentPhase = "preflight"
        self._cases: list[QueryTestCase] = []
        self._runners: dict[int, CaseRunner] = {}
        self._sessions: list[dict[str, Any]] = []
        self._samples: list[AgentSample] = []
        self._live = LiveStats(AGENT_BUCKET_SECONDS)
        self._statuses: Counter[str] = Counter()
        self._executions: dict[int, int] = {}
        self._in_flight: dict[int, tuple[str, float]] = {}
        self._finished_sessions = 0
        self._abandoned = 0
        self._resource_samples: list[dict[str, Any]] | None = [] if resource_sampler else None
        self._last_resource: dict[str, Any] | None = None
        self._t0 = 0.0
        self._deadline = 0.0
        self._ended_at = 0.0

    # ---- controle ---------------------------------------------------------

    def request_stop(self) -> None:
        """Interrompe a carga: nenhuma sessão começa caso novo e os agentes em curso morrem."""
        with self._lock:
            self._interrupted = True
            self._stop.set()
            runners = list(self._runners.values())
        for runner in runners:
            runner.cancel()

    # ---- execução ---------------------------------------------------------

    def run(self) -> AgentOutcome:
        """Roda pré-voo, preparo das sessões, carga e encerramento.

        Raises:
            LoadError: Se o pré-voo falha ou nenhuma sessão pôde ser preparada.
        """
        started_at = datetime.now().isoformat(timespec="seconds")
        ticker = threading.Thread(target=self._ticker, name="agent-load-ticker", daemon=True)
        ticker.start()
        try:
            preflight = self._preflight()
            if not preflight.selection.cases and not self._stop.is_set():
                raise LoadError("nenhum caso disponível para a carga")
            return self._run_sessions(preflight, started_at)
        finally:
            self._done.set()
            ticker.join(timeout=PROGRESS_INTERVAL_S * 2)
            self._emit()

    def _run_sessions(self, preflight: PreflightResult, started_at: str) -> AgentOutcome:
        cfg = self._cfg
        self._cases = list(preflight.selection.cases)
        self._phase = "starting"
        setup_started = self._clock()
        for index in range(cfg.concurrency):
            if self._stop.is_set():
                break
            self._open_session(index, preflight)
        setup_s = self._clock() - setup_started
        ready = sorted(self._runners)
        if not ready and not self._stop.is_set():
            first = next((s["error"] for s in self._sessions if not s["ok"]), "motivo desconhecido")
            raise LoadError(f"nenhuma sessão pôde ser preparada: {first}")

        threads = []
        if not self._stop.is_set():
            self._t0 = self._clock()
            self._deadline = self._t0 + cfg.duration_s
            self._phase = "running"
            threads = [
                threading.Thread(
                    target=self._session_loop, args=(i,), name=f"agent-s{i}", daemon=True
                )
                for i in ready
            ]
            for thread in threads:
                thread.start()
        try:
            for thread in threads:
                # join com timeout: no Windows um join sem prazo segura o Ctrl+C da thread principal.
                while thread.is_alive():
                    thread.join(_JOIN_POLL_S)
        finally:
            for runner in self._runners.values():
                runner.close()

        self._phase = "finishing"
        duration_s = max(self._ended_at - self._t0, 0.0) if self._t0 else 0.0
        return AgentOutcome(
            config=cfg,
            selection=preflight.selection,
            samples=list(self._samples),
            sessions=self._session_summary(),
            duration_s=duration_s,
            setup_s=setup_s,
            started_at=started_at,
            ended_at=datetime.now().isoformat(timespec="seconds"),
            interrupted=self._interrupted,
            abandoned_calls=self._abandoned,
            resource_samples=self._resource_samples,
            server_tools=preflight.server_tools,
            sandbox_plan=preflight.sandbox_plan,
        )

    def _open_session(self, index: int, preflight: PreflightResult) -> None:
        started = self._clock()
        try:
            runner = self._factory(index, preflight)
        except Exception as exc:  # noqa: BLE001 - uma sessão que não sobe não derruba a carga
            self._sessions.append(
                {
                    "session": index,
                    "ok": False,
                    "ms": (self._clock() - started) * 1000.0,
                    "error": _describe(exc),
                }
            )
            return
        with self._lock:
            self._runners[index] = runner
        self._sessions.append(
            {
                "session": index,
                "ok": True,
                "ms": (self._clock() - started) * 1000.0,
                "copy_ms": getattr(runner, "copy_ms", None),
                "error": None,
            }
        )

    def _session_summary(self) -> list[dict[str, Any]]:
        return [{**s, "executions": self._executions.get(s["session"], 0)} for s in self._sessions]

    def _may_start(self, index: int) -> bool:
        if self._stop.is_set() or self._clock() >= self._deadline:
            return False
        limit = self._cfg.iterations
        return limit is None or self._executions.get(index, 0) < limit

    def _session_loop(self, index: int) -> None:
        runner = self._runners[index]
        cursor = index
        try:
            while self._may_start(index):
                case = self._cases[cursor % len(self._cases)]
                cursor += 1
                started = self._clock()
                with self._lock:
                    self._in_flight[index] = (case.id, started)
                sample = self._execute(index, runner, case, started)
                with self._lock:
                    self._in_flight.pop(index, None)
                    if sample is None:
                        self._abandoned += 1
                        break
                    self._record(index, sample)
        finally:
            with self._lock:
                self._finished_sessions += 1
                self._ended_at = max(self._ended_at, self._clock())

    def _execute(
        self, index: int, runner: CaseRunner, case: QueryTestCase, started: float
    ) -> AgentSample | None:
        """Roda e valida um caso; None se a carga foi interrompida no meio dele."""
        started_s = started - self._t0
        try:
            result = runner.execute(case)
        except Exception as exc:  # noqa: BLE001 - uma execução falha não derruba a sessão
            if self._stop.is_set():
                return None
            return self._sample(
                case, index, started_s, started, "error", "error", error=_describe(exc)
            )
        if result.status == "cancelled" or self._stop.is_set():
            return None
        latency_ms = result.latency_ms
        tool_calls = len(result.tool_calls)
        mcp_calls = sum(1 for call in result.tool_calls if classify_tool(call.name) == "mcp")
        counts = {"tool_calls": tool_calls, "mcp_calls": mcp_calls, "latency_ms": latency_ms}
        if result.status == "timeout":
            message = f"sessão do agente encerrada após {result.timeout_s or 0:.0f} s"
            return self._sample(
                case, index, started_s, started, "timeout", "timeout", message, **counts
            )
        failure = agent_failure(result)
        if failure:
            return self._sample(
                case, index, started_s, started, "error", "error", failure, **counts
            )
        try:
            test_result = self._build_result(case, result, self._validator.validate(case, result))
        except Exception as exc:  # noqa: BLE001 - erro do validador vira erro da execução
            return self._sample(
                case, index, started_s, started, "error", "error", _describe(exc), **counts
            )
        message = None if test_result.status == "pass" else test_result.error_message
        return self._sample(
            case, index, started_s, started, "ok", test_result.status, message, **counts
        )

    def _sample(
        self,
        case: QueryTestCase,
        index: int,
        started_s: float,
        started: float,
        outcome: Outcome,
        status: str,
        error: str | None = None,
        tool_calls: int = 0,
        mcp_calls: int = 0,
        latency_ms: float | None = None,
    ) -> AgentSample:
        measured = latency_ms if latency_ms is not None else (self._clock() - started) * 1000.0
        return AgentSample(
            case_id=case.id,
            group=case_group(case),
            session=index,
            started_s=started_s,
            latency_ms=measured,
            outcome=outcome,
            status=status,
            tool_calls=tool_calls,
            mcp_calls=mcp_calls,
            error=(error or None) and str(error)[:_ERROR_CHARS],
        )

    def _record(self, index: int, sample: AgentSample) -> None:
        """Registra a execução; chamar com ``self._lock`` já tomado."""
        self._samples.append(sample)
        self._live.add(sample.as_sample())
        self._statuses[sample.status] += 1
        self._executions[index] = self._executions.get(index, 0) + 1

    # ---- progresso ----------------------------------------------------------

    def _ticker(self) -> None:
        while not self._done.is_set():
            self._sample_resources()
            self._emit()
            self._done.wait(PROGRESS_INTERVAL_S)

    def _sample_resources(self) -> None:
        if self._sampler is None or self._phase not in ("running", "finishing") or not self._t0:
            return
        sample = self._sampler.sample()
        if sample is None:
            return
        point = {"t": self._clock() - self._t0, **sample}
        with self._lock:
            self._last_resource = point
            if self._resource_samples is not None:
                self._resource_samples.append(point)

    def progress(self) -> dict[str, Any]:
        """Instantâneo para a UI: fase, sessões, execuções, aprovação, percentis e série recente."""
        with self._lock:
            now = self._clock()
            running = self._t0 > 0
            elapsed = now - self._t0 if running else 0.0
            phase = self._phase
            if phase == "running" and running and now >= self._deadline and self._in_flight:
                phase = "finishing"
            summary = self._live.summary(elapsed)
            executions = summary["calls"]
            requested = self._cfg.concurrency
            ready = len(self._runners)
            failed = sum(1 for s in self._sessions if not s["ok"])
            return {
                "mode": "agent",
                "phase": phase,
                "elapsed_seconds": min(elapsed, self._cfg.duration_s),
                "duration_seconds": self._cfg.duration_s,
                "clients": {
                    "requested": requested,
                    "ready": ready,
                    "failed": failed,
                    "respawns": 0,
                },
                "sessions": {
                    "requested": requested,
                    "ready": ready,
                    "failed": failed,
                    "running": len(self._in_flight),
                    "finished": self._finished_sessions,
                },
                **summary,
                "throughput_cpm": summary["throughput_cps"] * 60.0,
                "statuses": dict(self._statuses),
                "pass_rate": self._statuses["pass"] / executions if executions else 0.0,
                "in_flight": [
                    {"session": i, "case_id": case_id, "elapsed_seconds": now - since}
                    for i, (case_id, since) in sorted(self._in_flight.items())
                ],
                "series": self._live.recent_series(elapsed, LIVE_SERIES_WINDOW) if running else [],
                "series_bucket_seconds": AGENT_BUCKET_SECONDS,
                "resources": self._last_resource,
            }

    def _emit(self) -> None:
        if self._on_progress is not None:
            self._on_progress(self.progress())
