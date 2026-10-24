"""Clientes falsos para testar o motor de carga sem subir o servidor MCP."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from tests.e2e.load.client import CallOutcome
from tests.e2e.load.engine import LoadConfig, LoadOutcome
from tests.e2e.load.mix import CallSpec, Selection, ToolHints
from tests.e2e.load.stats import Sample

READ_ONLY = ToolHints(read_only=True, open_world=False)

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
    ) -> None:
        self.behaviors = behaviors or {}
        self.startup_delay_s = startup_delay_s or {}
        self.fail_startup = fail_startup or set()
        self.hints = {tool: READ_ONLY for tool in tools}
        self.opened: list[int] = []
        self.closed: list[int] = []
        self.calls: list[tuple[int, str]] = []
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
