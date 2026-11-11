"""Cliente MCP síncrono para os testes: sobe o servidor no stdio, como um cliente faria.

A sessão vive numa tarefa só, numa thread com o próprio loop: o `stdio_client` do SDK
abre cancel scopes do anyio, que precisam ser fechados pela mesma tarefa que os abriu.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def payload(result) -> dict:
    """Envelope da tool, venha como structuredContent ou como texto JSON."""
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        return sc.get("result", sc) if set(sc) == {"result"} else sc
    for item in result.content or []:
        text = getattr(item, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"status": "error", "diagnostics": [text[:300]]}
    return {}


class ClienteMCP:
    def __init__(self, params: StdioServerParameters, *, timeout_inicio: float = 120) -> None:
        self.params = params
        self.chamadas: set[str] = set()
        self.avisos: list[tuple[str, str]] = []
        self.instalacao: dict | None = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._pronto: concurrent.futures.Future = concurrent.futures.Future()
        self._parar = asyncio.Event()
        self._servindo = asyncio.run_coroutine_threadsafe(self._servir(), self._loop)
        self._pronto.result(timeout_inicio)

    async def _servir(self) -> None:
        try:
            async with (
                stdio_client(self.params) as (read, write),
                ClientSession(read, write) as sessao,
            ):
                self.inicio = await sessao.initialize()
                self._sessao = sessao
                self._pronto.set_result(None)
                await self._parar.wait()
        except BaseException as exc:
            if not self._pronto.done():
                self._pronto.set_exception(exc)
            raise

    def _rodar(self, coro, timeout: float):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    @property
    def versao_anunciada(self) -> str:
        return self.inicio.serverInfo.version

    def ferramentas(self) -> dict:
        return {t.name: t for t in self._rodar(self._sessao.list_tools(), 60).tools}

    def chamar(self, tool: str, argumentos: dict | None = None, *, timeout: float = 900) -> dict:
        self.chamadas.add(tool)
        env = payload(self._rodar(self._sessao.call_tool(tool, argumentos or {}), timeout))
        if env.get("version_warnings"):
            self.avisos.append((tool, str(env["version_warnings"][0])[:160]))
        return env

    def fechar(self) -> None:
        self._loop.call_soon_threadsafe(self._parar.set)
        try:
            self._servindo.result(60)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(10)
