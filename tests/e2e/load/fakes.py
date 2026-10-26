"""Clientes e runners falsos para testar a carga sem subir o servidor MCP nem um agente."""
from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from tests.e2e.load.agent_cases import AgentSelection
from tests.e2e.load.agent_engine import AgentLoadConfig, AgentOutcome, AgentSample
from tests.e2e.load.client import CallOutcome
from tests.e2e.load.engine import LoadConfig, LoadOutcome
from tests.e2e.load.mix import CallSpec, Excluded, Selection, ToolHints
from tests.e2e.load.stats import Sample
from tests.e2e.queries.models import ExpectedResult, QueryResult, QueryTestCase, TestResult, ToolCall

READ_ONLY = ToolHints(read_only=True, open_world=False)
WRITES = ToolHints(read_only=False, open_world=False)

DEFAULT_TOOLS = ("docs_list", "docs_search", "schema_list")


@dataclass
class Behavior:
    """Como uma tool responde: ``outcome``, ``delay_s`` e se a sessão fica inutilizável."""

    outcome: str = "ok"
    delay_s: float = 0.005
    broken: bool = False
    error: str | None = None
    hang: bool = False
    hang_only_workers: bool = False


class FakeClient:
    def __init__(self, owner: FakeFactory, index: int) -> None:
        self._owner = owner
        self.index = index

    async def list_tools(self) -> dict[str, ToolHints]:
        return dict(self._owner.hints)

    async def call(self, tool: str, arguments: dict[str, Any], timeout_s: float) -> CallOutcome:
        owner = self._owner
        owner.calls.append((self.index, tool))
        owner.arguments.append((self.index, tool, arguments))
        behavior = owner.behaviors.get(tool, Behavior())
        if behavior.hang or (behavior.hang_only_workers and self.index >= 0):
            await asyncio.sleep(3600)
        await asyncio.sleep(behavior.delay_s)
        if behavior.broken and not owner.broken_once.get((self.index, tool)):
            owner.broken_once[(self.index, tool)] = True
            return CallOutcome("timeout", behavior.delay_s * 1000, "sem resposta", True)
        return CallOutcome(behavior.outcome, behavior.delay_s * 1000, behavior.error)  # type: ignore[arg-type]


class FakeFactory:
    """Fábrica de clientes: registra aberturas/fechamentos e injeta atraso ou falha de subida."""

    def __init__(
        self,
        behaviors: dict[str, Behavior] | None = None,
        startup_delay_s: dict[int, float] | None = None,
        fail_startup: set[int] | None = None,
        tools: tuple[str, ...] = DEFAULT_TOOLS,
        writing_tools: tuple[str, ...] = (),
    ) -> None:
        self.behaviors = behaviors or {}
        self.startup_delay_s = startup_delay_s or {}
        self.fail_startup = fail_startup or set()
        self.hints = {tool: READ_ONLY for tool in tools}
        self.hints.update({tool: WRITES for tool in writing_tools})
        self.opened: list[int] = []
        self.closed: list[int] = []
        self.calls: list[tuple[int, str]] = []
        self.arguments: list[tuple[int, str, dict[str, Any]]] = []
        self.broken_once: dict[tuple[int, str], bool] = {}

    def __call__(self, index: int):
        return self._open(index)

    @asynccontextmanager
    async def _open(self, index: int) -> AsyncIterator[FakeClient]:
        await asyncio.sleep(self.startup_delay_s.get(index, 0.0))
        if index in self.fail_startup:
            raise RuntimeError(f"cliente {index} não subiu")
        self.opened.append(index)
        try:
            yield FakeClient(self, index)
        finally:
            self.closed.append(index)


def make_outcome(
    samples: list[Sample] | None = None,
    duration_s: float = 2.0,
    config: LoadConfig | None = None,
    excluded: list[Any] | None = None,
) -> LoadOutcome:
    """Resultado sintético para testar persistência e relatório sem rodar a carga."""
    samples = samples if samples is not None else [
        Sample("docs_list", 0.1, 100.0, "ok"),
        Sample("docs_list", 0.5, 140.0, "ok"),
        Sample("docs_search", 0.7, 30.0, "ok"),
        Sample("docs_search", 1.2, 31.0, "error", "falha simulada"),
    ]
    return LoadOutcome(
        config=config or LoadConfig(concurrency=2, duration_s=2.0),
        selection=Selection(
            specs=[CallSpec("docs_list#todas", "docs_list", {}),
                   CallSpec("docs_search#sddp", "docs_search", {"consulta": "SDDP"})],
            excluded=excluded or [],
        ),
        samples=samples,
        startups=[
            {"client": -1, "kind": "preflight", "ms": 900.0, "warmup_ms": None, "ok": True, "error": None},
            {"client": 0, "kind": "initial", "ms": 700.0, "warmup_ms": 120.0, "ok": True, "error": None},
            {"client": 1, "kind": "initial", "ms": 760.0, "warmup_ms": 110.0, "ok": True, "error": None},
        ],
        duration_s=duration_s,
        startup_wall_s=0.9,
        started_at="2026-10-24T10:00:00",
        ended_at="2026-10-24T10:00:03",
    )


# ---- modo agent -------------------------------------------------------------


def make_case(
    case_id: str = "docs-list-all",
    tool: str | None = "docs_list",
    tools: list[str] | None = None,
    uses_mcp: bool = True,
    tags: tuple[str, ...] = ("docs",),
    requires: tuple[str, ...] = (),
) -> QueryTestCase:
    """Caso de teste mínimo, sem fonte exigida por padrão."""
    return QueryTestCase(
        id=case_id,
        query=f"pergunta de {case_id}",
        expected=ExpectedResult(uses_mcp=uses_mcp, tool=tool, tools=tools),
        tags=tags,
        requires=requires,
        timeout_s=30.0,
    )


def make_query_result(
    case: QueryTestCase,
    status: str = "completed",
    tools: tuple[str, ...] = ("docs_list",),
    response: str = "resposta",
    latency_ms: float = 1200.0,
    stdout: str = "",
    stderr: str = "",
) -> QueryResult:
    return QueryResult(
        test_case=case,
        tool_calls=[ToolCall(name=t, args={}) for t in tools],
        agent_response=response,
        latency_ms=latency_ms,
        status=status,
        stdout=stdout,
        stderr=stderr,
        timeout_s=30.0,
    )


def fake_build_result(status_by_case: dict[str, str] | None = None):
    """``_build_test_result`` falso: o status vem do mapa (padrão ``pass``)."""
    statuses = status_by_case or {}

    def build(case: QueryTestCase, result: QueryResult, _validation: Any) -> TestResult:
        status = statuses.get(case.id, "pass")
        return TestResult(
            test_id=case.id,
            query=case.query,
            expected_tool=case.expected.tool,
            expected_tools=case.expected.tools,
            actual_tool=result.tool_calls[0].name if result.tool_calls else None,
            all_tool_calls=[],
            status=status,
            latency_ms=result.latency_ms,
            tool_latency_ms=None,
            mcp_used=bool(result.tool_calls),
            correct_tool=status != "fail",
            correct_result=status == "pass",
            agent_response=result.agent_response,
            error_message=None if status == "pass" else f"validação: {status}",
            tags=list(case.tags),
            validation_checks=[],
        )

    return build


class AlwaysValid:
    """Validador falso: o status sai do ``fake_build_result``."""

    def validate(self, _case: QueryTestCase, _result: QueryResult) -> None:
        return None


class FakeCaseRunner:
    """Runner de sessão falso: devolve ``respond(case)`` depois de ``delay_s``.

    Com ``block=True`` a execução só termina quando ``cancel`` é chamado (devolve
    ``cancelled``), como o ``QueryRunner`` real ao matar o agente.
    """

    def __init__(
        self,
        index: int,
        respond=None,
        delay_s: float = 0.01,
        block: bool = False,
        log: list[tuple[str, int, str]] | None = None,
    ) -> None:
        self.index = index
        self._respond = respond or (lambda case: make_query_result(case))
        self._delay_s = delay_s
        self._block = block
        self._cancel = threading.Event()
        self.log = log if log is not None else []
        self.cancelled = False
        self.closed = False

    def execute(self, case: QueryTestCase) -> QueryResult:
        self.log.append(("execute", self.index, case.id))
        if self._block:
            self._cancel.wait(30)
            return make_query_result(case, status="cancelled")
        if self._cancel.wait(self._delay_s):
            return make_query_result(case, status="cancelled")
        return self._respond(case)

    def cancel(self) -> None:
        self.cancelled = True
        self._cancel.set()

    def close(self) -> None:
        self.closed = True


def make_agent_outcome(samples: list[AgentSample] | None = None, **config: Any) -> AgentOutcome:
    """Resultado sintético do modo agent para testar persistência e relatório."""
    cases = [make_case("docs-list-all"), make_case("schema-list-all", tool="schema_list")]
    samples = samples if samples is not None else [
        AgentSample("docs-list-all", "docs", 0, 0.0, 10_000.0, "ok", "pass", 2, 1),
        AgentSample("docs-list-all", "docs", 1, 0.5, 14_000.0, "ok", "fail", 3, 1, "tool errada"),
        AgentSample("schema-list-all", "schema", 0, 10.0, 8_000.0, "ok", "pass", 1, 1),
        AgentSample("schema-list-all", "schema", 1, 15.0, 30_000.0, "timeout", "timeout", 0, 0,
                    "sessão do agente encerrada após 30 s"),
    ]
    values = {"concurrency": 2, "duration_s": 60.0, "provider": "claude"}
    values.update(config)
    return AgentOutcome(
        config=AgentLoadConfig(**values),
        selection=AgentSelection(
            cases=cases,
            excluded=[Excluded("deck-edit-json", "deck_edit_json", "grava arquivos")],
        ),
        samples=samples,
        sessions=[
            {"session": 0, "ok": True, "ms": 5.0, "error": None, "executions": 2},
            {"session": 1, "ok": True, "ms": 6.0, "error": None, "executions": 2},
        ],
        duration_s=60.0,
        setup_s=0.2,
        started_at="2026-10-24T10:00:00",
        ended_at="2026-10-24T10:01:00",
    )
