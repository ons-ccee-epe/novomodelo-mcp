"""Motor da carga: N clientes concorrentes chamando as tools do mix.

Fases: ``preflight`` (um cliente valida o mix), ``starting`` (os N servidores
sobem em paralelo e cada cliente se aquece), ``running`` (o relógio da carga só
começa depois que todos estão prontos) e ``finishing``. Tempo de subida e de
aquecimento ficam fora da latência das chamadas.

Cada chamada sem resposta no timeout é contada como ``timeout`` e o cliente é
recriado: uma sessão stdio que perdeu uma resposta não é mais confiável.

Com ``sessions`` (``sandbox.ToolsSessions``), cada sessão tem pastas próprias e, se a
seleção grava, a sua cópia das fixtures: a cópia é feita antes de subir o servidor dela,
medida em ``copy_ms`` (fora do tempo de subida), e as chamadas são expandidas contra ela.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from novomodelo_mcp_e2e.load.client import CallOutcome, ClientFactory, LoadClient
from novomodelo_mcp_e2e.load.mix import (
    CallSpec,
    Excluded,
    Selection,
    select_specs,
    tool_group,
    validate_tools,
)
from novomodelo_mcp_e2e.load.resources import ResourceSampler
from novomodelo_mcp_e2e.load.stats import LiveStats, Sample

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "LoadConfig",
    "LoadError",
    "LoadOutcome",
    "LoadRunner",
    "MAX_CONCURRENCY",
    "MAX_DURATION_S",
    "MAX_ITERATIONS",
    "MAX_TIMEOUT_S",
]

Phase = Literal["preflight", "starting", "running", "finishing"]
StartupKind = Literal["preflight", "initial", "respawn"]

MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 32
MIN_DURATION_S = 1.0
MAX_DURATION_S = 1800.0
MAX_TIMEOUT_S = 1800.0
MAX_ITERATIONS = 1_000_000
DEFAULT_TIMEOUT_S = 60.0

# Depois do fim da janela, chamadas em curso têm este tempo para responder; as que
# não respondem são abandonadas (contadas em ``abandoned_calls``).
DRAIN_GRACE_S = 5.0
PROGRESS_INTERVAL_S = 1.0
LIVE_SERIES_WINDOW = 120

# Medido no Windows: o bridge (Python) herda o stdin do servidor, que tem uma leitura
# síncrona pendente, e trava ao iniciar até o cliente escrever nesse pipe; a carga não
# escreve durante a chamada. A correção é do servidor, não do motor.
BRIDGE_STDIN_HINT = (
    "provável causa no Windows: o bridge herda o stdin do servidor MCP e trava ao iniciar "
    "até o cliente escrever nele (correção no servidor: stdin=subprocess.DEVNULL em run_bridge)"
)


class LoadError(RuntimeError):
    """A carga não pôde rodar (servidor não sobe, mix vazio...)."""


class SessionSpace(Protocol):
    """Pastas por sessão (``-1`` é o pré-voo); ``sandbox.ToolsSessions`` é a real."""

    def prepare(self, index: int) -> float: ...

    def root(self, index: int) -> Path: ...

    def release(self, index: int) -> None: ...


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True)
class LoadConfig:
    """Parâmetros da carga, validados na criação.

    ``iterations`` é por cliente: cada cliente para ao fazer essa quantidade de
    chamadas ou ao fim de ``duration_s``, o que vier primeiro.
    """

    concurrency: int
    duration_s: float
    iterations: int | None = None
    tools: tuple[str, ...] | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S
    warmup: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.concurrency, int) or isinstance(self.concurrency, bool):
            raise ValueError("concorrência deve ser um inteiro")
        if not MIN_CONCURRENCY <= self.concurrency <= MAX_CONCURRENCY:
            raise ValueError(f"concorrência fora de {MIN_CONCURRENCY}..{MAX_CONCURRENCY}")
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
        if (
            not _is_number(self.timeout_s)
            or not math.isfinite(self.timeout_s)
            or not 0 < self.timeout_s <= MAX_TIMEOUT_S
        ):
            raise ValueError(f"timeout fora de (0, {MAX_TIMEOUT_S:g}] s")
        if self.tools is not None:
            object.__setattr__(self, "tools", tuple(validate_tools(self.tools)))

    mode = "tools"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "concurrency": self.concurrency,
            "duration_seconds": self.duration_s,
            "iterations": self.iterations,
            "tools": list(self.tools) if self.tools is not None else None,
            "timeout_seconds": self.timeout_s,
            "warmup": self.warmup,
        }


@dataclass
class LoadOutcome:
    """Tudo o que a execução produziu; ``store.build_record`` monta o JSON final."""

    config: LoadConfig
    selection: Selection
    samples: list[Sample]
    startups: list[dict[str, Any]]
    duration_s: float
    startup_wall_s: float
    started_at: str
    ended_at: str
    interrupted: bool = False
    abandoned_calls: int = 0
    resource_samples: list[dict[str, Any]] | None = None


@dataclass
class _Counters:
    ready: int = 0
    failed: int = 0
    respawns: int = 0
    abandoned: int = 0
    per_client_calls: dict[int, int] = field(default_factory=dict)
    cursors: dict[int, int] = field(default_factory=dict)


def _describe(exc: BaseException) -> str:
    # Falha de subida costuma vir embrulhada em ExceptionGroup pelo anyio.
    leaf: BaseException = exc
    while isinstance(leaf, BaseExceptionGroup) and leaf.exceptions:
        leaf = leaf.exceptions[0]
    return f"{type(leaf).__name__}: {leaf}"[:300]


class LoadRunner:
    """Executa uma carga. ``client_factory(i)`` abre o cliente do worker ``i`` (-1: pré-voo)."""

    def __init__(
        self,
        config: LoadConfig,
        fixtures_dir: str | Path,
        client_factory: ClientFactory,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        resource_sampler: ResourceSampler | None = None,
        clock: Callable[[], float] = time.perf_counter,
        sessions: SessionSpace | None = None,
    ) -> None:
        self._cfg = config
        self._fixtures = Path(fixtures_dir)
        self._factory = client_factory
        self._sessions = sessions
        self._call_numbers: dict[int, int] = {}
        self._on_progress = on_progress
        self._sampler = resource_sampler
        self._clock = clock

        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_requested = False
        self._interrupted = False

        self._samples: list[Sample] = []
        self._live = LiveStats()
        self._startups: list[dict[str, Any]] = []
        self._counters = _Counters()
        self._resource_samples: list[dict[str, Any]] | None = [] if resource_sampler else None
        self._last_resource: dict[str, Any] | None = None

        self._phase: Phase = "preflight"
        self._specs: list[CallSpec] = []
        self._warm_specs: list[CallSpec] = []
        self._t0 = 0.0
        self._deadline = 0.0
        self._loops_ended_at = 0.0

    # ---- controle ---------------------------------------------------------

    def request_stop(self) -> None:
        """Interrompe a carga; seguro de chamar de outra thread (ou de um handler de sinal)."""
        loop = self._loop
        if loop is None:
            self._stop_requested = True
            return
        loop.call_soon_threadsafe(self._interrupt)

    def _interrupt(self) -> None:
        self._interrupted = True
        self._halt()

    def _halt(self) -> None:
        self._stop.set()
        self._all_arrived.set()
        self._go.set()

    # ---- execução ---------------------------------------------------------

    async def run(self) -> LoadOutcome:
        """Roda pré-voo, subida, carga e encerramento.

        Raises:
            LoadError: Se o servidor não sobe, o mix fica vazio ou nenhum cliente inicia.
        """
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._all_arrived = asyncio.Event()
        self._go = asyncio.Event()
        self._stop_waiter = asyncio.ensure_future(self._stop.wait())
        self._done = asyncio.Event()
        if self._stop_requested:
            self._interrupt()

        started_at = datetime.now().isoformat(timespec="seconds")
        ticker = asyncio.ensure_future(self._ticker())
        try:
            selection = await self._preflight()
            return await self._run_load(selection, started_at)
        finally:
            self._done.set()
            self._stop_waiter.cancel()
            await asyncio.gather(ticker, self._stop_waiter, return_exceptions=True)

    async def _run_load(self, selection: Selection, started_at: str) -> LoadOutcome:
        cfg = self._cfg
        self._specs = selection.specs
        first_by_tool: dict[str, CallSpec] = {}
        for spec in self._specs:
            first_by_tool.setdefault(spec.tool, spec)
        self._warm_specs = list(first_by_tool.values())
        self._phase = "starting"

        starting_at = self._clock()
        workers = [asyncio.ensure_future(self._worker(i)) for i in range(cfg.concurrency)]
        await self._all_arrived.wait()
        startup_wall_s = self._clock() - starting_at

        if self._counters.ready == 0 and not self._interrupted:
            self._halt()
            await asyncio.gather(*workers, return_exceptions=True)
            first = next((s["error"] for s in self._startups if not s["ok"]), "motivo desconhecido")
            raise LoadError(f"nenhum cliente iniciou: {first}")

        watchdog = None
        if not self._stop.is_set():
            self._t0 = self._clock()
            self._deadline = self._t0 + cfg.duration_s
            self._phase = "running"
            watchdog = asyncio.ensure_future(self._hard_stop_at(self._deadline + DRAIN_GRACE_S))
            self._go.set()
        await asyncio.gather(*workers)
        if watchdog is not None:
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)

        self._phase = "finishing"
        duration_s = max(self._loops_ended_at - self._t0, 0.0) if self._t0 else 0.0
        return LoadOutcome(
            config=cfg,
            selection=selection,
            samples=self._samples,
            startups=self._startups,
            duration_s=duration_s,
            startup_wall_s=startup_wall_s,
            started_at=started_at,
            ended_at=datetime.now().isoformat(timespec="seconds"),
            interrupted=self._interrupted,
            abandoned_calls=self._counters.abandoned,
            resource_samples=self._resource_samples,
        )

    async def _hard_stop_at(self, when: float) -> None:
        await asyncio.sleep(max(0.0, when - self._clock()))
        self._halt()

    # ---- pré-voo ----------------------------------------------------------

    async def _preflight(self) -> Selection:
        """Valida o mix num cliente à parte: uma chamada com parâmetro inválido ou que
        trava viraria taxa de erro da carga, não um sinal do servidor."""
        cfg = self._cfg
        selection: Selection | None = None
        pending: list[CallSpec] = []
        valid: list[CallSpec] = []
        excluded: list[Excluded] = []
        # Grupo pesado que já travou no pré-voo -> a chamada que travou: as demais do mesmo
        # grupo sobem a mesma CLI e custariam um timeout cada.
        stalled: dict[str, str] = {}
        copy_s = await self._prepare_session(-1)

        while selection is None or pending:
            if self._stop.is_set():
                break
            async with AsyncExitStack() as stack:
                started = self._clock()
                try:
                    client = await stack.enter_async_context(self._factory(-1))
                except Exception as exc:
                    raise LoadError(f"o servidor MCP não iniciou: {_describe(exc)}") from exc
                self._record_startup(-1, "preflight", self._clock() - started, True, copy_s=copy_s)
                copy_s = None

                if selection is None:
                    selection = await self._select(client)
                    excluded.extend(selection.excluded)
                    pending = list(selection.specs)

                while pending and not self._stop.is_set():
                    spec = pending.pop(0)
                    group = tool_group(spec.tool)
                    if spec.heavy and group in stalled:
                        reason = f"pré-voo: não chamada, {stalled[group]} ficou sem resposta"
                        excluded.append(Excluded(spec.id, spec.tool, reason))
                        continue
                    result = await self._race(
                        client.call(spec.tool, self._arguments(-1, spec), cfg.timeout_s)
                    )
                    if result is None:
                        break
                    if result.outcome == "ok":
                        valid.append(spec)
                    else:
                        excluded.append(
                            Excluded(spec.id, spec.tool, self._preflight_reason(spec, result))
                        )
                        if result.outcome == "timeout" and spec.heavy:
                            stalled.setdefault(group, spec.id)
                    if result.broken:
                        break

        if self._sessions is not None:
            await asyncio.to_thread(self._sessions.release, -1)
        final = Selection(specs=valid, excluded=excluded)
        if not final.specs and not self._interrupted:
            reasons = "; ".join(f"{e.id}: {e.reason}" for e in final.excluded[:5])
            raise LoadError(f"nenhuma chamada disponível no mix ({reasons})")
        return final

    @staticmethod
    def _preflight_reason(spec: CallSpec, result: CallOutcome) -> str:
        reason = f"pré-voo: {result.error}"
        if result.outcome == "timeout" and spec.tool.startswith("bridge_"):
            reason += f" ({BRIDGE_STDIN_HINT})"
        return reason

    async def _prepare_session(self, index: int) -> float | None:
        """Pastas e cópia da sessão, numa thread (a cópia é síncrona); None sem ``sessions``."""
        if self._sessions is None:
            return None
        return await asyncio.to_thread(self._sessions.prepare, index)

    def _arguments(self, index: int, spec: CallSpec) -> dict[str, Any]:
        """Argumentos da chamada na raiz da sessão, com ``{CALL}`` numerado por sessão."""
        if self._sessions is None:
            return spec.arguments
        number = self._call_numbers.get(index, 0) + 1
        self._call_numbers[index] = number
        return spec.bind(self._sessions.root(index), number)

    async def _select(self, client: LoadClient) -> Selection:
        try:
            hints = await client.list_tools()
        except Exception as exc:
            raise LoadError(f"list_tools falhou: {_describe(exc)}") from exc
        return select_specs(self._fixtures, self._cfg.tools, hints)

    # ---- workers ----------------------------------------------------------

    async def _worker(self, index: int) -> None:
        try:
            reason = await self._session(index, "initial")
            while reason == "respawn" and self._may_continue(index):
                self._counters.respawns += 1
                reason = await self._session(index, "respawn")
        except Exception as exc:  # noqa: BLE001 - um worker com defeito não derruba a carga
            self._record_startup(index, "respawn", 0.0, False, error=_describe(exc))

    def _may_continue(self, index: int) -> bool:
        if self._stop.is_set() or self._clock() >= self._deadline:
            return False
        limit = self._cfg.iterations
        return limit is None or self._counters.per_client_calls.get(index, 0) < limit

    async def _session(self, index: int, kind: StartupKind) -> str:
        """Abre o cliente, aquece e roda o laço de chamadas; devolve ``done|respawn|failed``."""
        copy_s = None
        if kind == "initial":
            try:
                copy_s = await self._prepare_session(index)
            except Exception as exc:  # noqa: BLE001 - registrado como falha de subida
                self._startup_failed(index, kind, 0.0, f"cópia das fixtures: {_describe(exc)}")
                return "failed"
        async with AsyncExitStack() as stack:
            started = self._clock()
            try:
                client = await stack.enter_async_context(self._factory(index))
            except Exception as exc:  # noqa: BLE001 - registrado como falha de subida
                self._startup_failed(
                    index, kind, self._clock() - started, _describe(exc), copy_s=copy_s
                )
                return "failed"
            startup_s = self._clock() - started

            warmup_s = None
            if self._cfg.warmup and not self._stop.is_set():
                warmup_started = self._clock()
                problem = await self._warm_up(index, client)
                if problem:
                    self._startup_failed(
                        index, kind, startup_s, f"aquecimento: {problem}", copy_s=copy_s
                    )
                    return "failed"
                warmup_s = self._clock() - warmup_started

            self._record_startup(index, kind, startup_s, True, warmup_s=warmup_s, copy_s=copy_s)
            if kind == "initial":
                self._counters.ready += 1
                self._arrive()
                await self._go.wait()
            try:
                return await self._call_loop(index, client)
            finally:
                self._loops_ended_at = max(self._loops_ended_at, self._clock())

    def _startup_failed(
        self,
        index: int,
        kind: StartupKind,
        seconds: float,
        error: str,
        copy_s: float | None = None,
    ) -> None:
        self._record_startup(index, kind, seconds, False, error=error, copy_s=copy_s)
        self._counters.failed += 1
        if kind == "initial":
            self._arrive()

    def _arrive(self) -> None:
        if self._counters.ready + self._counters.failed >= self._cfg.concurrency:
            self._all_arrived.set()

    async def _warm_up(self, index: int, client: LoadClient) -> str | None:
        """Uma chamada de cada tool do mix, fora das métricas; devolve o problema, se houver."""
        for spec in self._warm_specs:
            arguments = self._arguments(index, spec)
            result = await self._race(client.call(spec.tool, arguments, self._cfg.timeout_s))
            if result is not None and result.broken:
                return f"{spec.tool}: {result.error}"
        return None

    async def _call_loop(self, index: int, client: LoadClient) -> str:
        cfg = self._cfg
        counters = self._counters
        if not self._t0:
            return "done"
        while self._may_continue(index):
            cursor = counters.cursors.get(index, index)
            counters.cursors[index] = cursor + 1
            spec = self._specs[cursor % len(self._specs)]

            arguments = self._arguments(index, spec)
            started_s = self._clock() - self._t0
            result = await self._race(client.call(spec.tool, arguments, cfg.timeout_s))
            if result is None:
                counters.abandoned += 1
                return "done"
            sample = Sample(spec.tool, started_s, result.latency_ms, result.outcome, result.error)
            self._samples.append(sample)
            self._live.add(sample)
            counters.per_client_calls[index] = counters.per_client_calls.get(index, 0) + 1
            if result.broken:
                return "respawn"
        return "done"

    async def _race(self, call: Any) -> CallOutcome | None:
        """Resultado da chamada, ou None se a parada veio antes (a chamada é cancelada)."""
        task = asyncio.ensure_future(call)
        done, _ = await asyncio.wait({task, self._stop_waiter}, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            error = task.exception()
            if error is not None:
                return CallOutcome("error", 0.0, _describe(error), True)
            return task.result()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return None

    # ---- registro e progresso --------------------------------------------

    def _record_startup(
        self,
        index: int,
        kind: StartupKind,
        seconds: float,
        ok: bool,
        error: str | None = None,
        warmup_s: float | None = None,
        copy_s: float | None = None,
    ) -> None:
        self._startups.append(
            {
                "client": index,
                "kind": kind,
                "ms": seconds * 1000.0,
                "warmup_ms": warmup_s * 1000.0 if warmup_s is not None else None,
                "copy_ms": copy_s * 1000.0 if copy_s is not None else None,
                "ok": ok,
                "error": error,
            }
        )

    async def _ticker(self) -> None:
        while not self._done.is_set():
            await self._sample_resources()
            self._emit()
            try:
                await asyncio.wait_for(self._done.wait(), timeout=PROGRESS_INTERVAL_S)
            except TimeoutError:
                continue

    async def _sample_resources(self) -> None:
        if self._sampler is None or self._phase != "running":
            return
        sample = await asyncio.to_thread(self._sampler.sample)
        if sample is None:
            return
        point = {"t": self._clock() - self._t0, **sample}
        self._last_resource = point
        if self._resource_samples is not None:
            self._resource_samples.append(point)

    def progress(self) -> dict[str, Any]:
        """Instantâneo para a UI: fase, contagens, percentis acumulados e série recente."""
        running = self._phase in ("running", "finishing") and self._t0 > 0
        elapsed = min(self._clock() - self._t0, self._cfg.duration_s) if running else 0.0
        counters = self._counters
        return {
            "phase": self._phase,
            "elapsed_seconds": elapsed,
            "duration_seconds": self._cfg.duration_s,
            "clients": {
                "requested": self._cfg.concurrency,
                "ready": counters.ready,
                "failed": counters.failed,
                "respawns": counters.respawns,
            },
            **self._live.summary(max(self._clock() - self._t0, 0.0) if running else 0.0),
            "series": (
                self._live.recent_series(self._clock() - self._t0, LIVE_SERIES_WINDOW)
                if running
                else []
            ),
            "resources": self._last_resource,
        }

    def _emit(self) -> None:
        if self._on_progress is not None:
            self._on_progress(self.progress())
