"""Cliente MCP da carga: um processo do servidor por cliente, via stdio.

Cada ``LoadClient`` abre e fecha dentro da mesma task: ``stdio_client`` e
``ClientSession`` usam task groups do anyio, que não podem ser encerrados por
outra task.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol, TextIO

from tests.e2e.load.mix import ToolHints, hints_from_tools
from tests.e2e.load.stats import Outcome

__all__ = [
    "CallOutcome",
    "ClientFactory",
    "LoadClient",
    "McpStdioClient",
    "classify_result",
    "default_server_command",
    "stdio_client_factory",
]

STARTUP_TIMEOUT_S = 180.0
# Folga sobre o timeout do SDK: só dispara se o próprio SDK ficar preso.
_BACKSTOP_S = 5.0
# McpError do SDK para "sem resposta a tempo" (httpx.codes.REQUEST_TIMEOUT).
_SDK_TIMEOUT_CODE = 408
_ERROR_CHARS = 200


@dataclass(frozen=True)
class CallOutcome:
    """Resultado de uma chamada. ``broken``: a sessão não é mais confiável e deve ser recriada."""

    outcome: Outcome
    latency_ms: float
    error: str | None = None
    broken: bool = False


class LoadClient(Protocol):
    async def call(self, tool: str, arguments: dict[str, Any], timeout_s: float) -> CallOutcome: ...

    async def list_tools(self) -> dict[str, ToolHints]: ...


ClientFactory = Callable[[int], AbstractAsyncContextManager[LoadClient]]


def default_server_command() -> tuple[str, list[str]]:
    """Servidor do checkout em teste: o ``~/.kiro/settings/mcp.json`` aponta outra instalação."""
    return sys.executable, ["-m", "novomodelo_mcp"]


def _first_text(result: Any) -> str:
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            return text
    return ""


def classify_result(result: Any) -> tuple[Outcome, str | None]:
    """``error`` se o MCP marcou ``isError`` ou o envelope da tool tem ``status == "error"``."""
    text = _first_text(result)
    if getattr(result, "isError", False):
        return "error", text[:_ERROR_CHARS] or "isError sem texto"
    try:
        envelope = json.loads(text)
    except ValueError:
        return "ok", None
    if isinstance(envelope, dict) and envelope.get("status") == "error":
        diagnostics = envelope.get("diagnostics") or envelope.get("message") or "status=error"
        first = diagnostics[0] if isinstance(diagnostics, list) and diagnostics else diagnostics
        return "error", str(first)[:_ERROR_CHARS]
    return "ok", None


class McpStdioClient:
    """Sessão MCP já inicializada. ``call`` nunca levanta: devolve ``CallOutcome``."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def list_tools(self) -> dict[str, ToolHints]:
        result = await self._session.list_tools()
        return hints_from_tools(result.tools)

    async def call(self, tool: str, arguments: dict[str, Any], timeout_s: float) -> CallOutcome:
        started = time.perf_counter()

        def elapsed_ms() -> float:
            return (time.perf_counter() - started) * 1000.0

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(
                    tool, arguments, read_timeout_seconds=timedelta(seconds=timeout_s)
                ),
                timeout=timeout_s + _BACKSTOP_S,
            )
        except TimeoutError:
            return CallOutcome("timeout", elapsed_ms(), f"sem resposta em {timeout_s:g} s", True)
        except Exception as exc:  # noqa: BLE001 - uma chamada falha não derruba o worker
            error = getattr(exc, "error", None)
            if getattr(error, "code", None) == _SDK_TIMEOUT_CODE:
                return CallOutcome("timeout", elapsed_ms(), f"sem resposta em {timeout_s:g} s", True)
            return CallOutcome(
                "error", elapsed_ms(), f"{type(exc).__name__}: {exc}"[:_ERROR_CHARS], True
            )
        outcome, message = classify_result(result)
        return CallOutcome(outcome, elapsed_ms(), message)


@asynccontextmanager
async def _open_stdio_client(
    command: str, args: list[str], env: dict[str, str], errlog: TextIO
) -> AsyncIterator[McpStdioClient]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(params, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=STARTUP_TIMEOUT_S)
            yield McpStdioClient(session)


def stdio_client_factory(
    command: str, args: list[str], env: dict[str, str], errlog: TextIO
) -> ClientFactory:
    """Fábrica de clientes reais: cada chamada de ``factory(i)`` sobe um processo novo."""

    def factory(_index: int) -> AbstractAsyncContextManager[LoadClient]:
        return _open_stdio_client(command, args, env, errlog)

    return factory
