"""Cliente MCP unificado para testes locais e remotos."""
from __future__ import annotations

import json
import os
import time
from typing import Any


class MCPClient:
    """Cliente para chamar tools MCP em modo local ou remoto.

    Modo local: importa e chama o servidor MCP diretamente.
    Modo remoto: (futuro) comunica via HTTP/stdio.

    Uso:
        client = MCPClient()  # usa COBRE_MCP_TARGET ou "local"
        envelope, elapsed_ms = client.call_tool("bridge_check_newave", src="/path")
    """

    def __init__(self, target: str | None = None) -> None:
        """Inicializa o cliente.

        Args:
            target: "local" para importação direta, URL para servidor remoto.
                   Se None, usa env var COBRE_MCP_TARGET (default: "local").
        """
        self.target = target or os.environ.get("COBRE_MCP_TARGET", "local")
        self._server = None
        self._tools: dict[str, Any] = {}

        if self.target == "local":
            self._init_local()
        else:
            self._init_remote(self.target)

    def _init_local(self) -> None:
        """Inicializa cliente local importando o servidor MCP."""
        try:
            from cobre_mcp.server import build_server
            self._server = build_server()
            self._discover_tools()
        except ImportError as e:
            raise RuntimeError(
                f"Falha ao importar cobre_mcp: {e}. "
                "Certifique-se de que o pacote está instalado."
            ) from e

    def _init_remote(self, url: str) -> None:
        """Inicializa cliente remoto para servidor deployado."""
        # TODO: Implementar quando houver deployment
        raise NotImplementedError(
            f"Modo remoto não implementado: {url}. "
            "Use target='local' ou aguarde implementação futura."
        )

    def _discover_tools(self) -> None:
        """Descobre tools disponíveis no servidor local."""
        if self._server is None:
            return

        # FastMCP armazena tools registradas internamente
        # Acessamos via _tool_manager ou iterando pelos handlers
        try:
            for tool in self._server._tool_manager.list_tools():
                self._tools[tool.name] = tool
        except AttributeError:
            # Fallback: tenta descobrir de outra forma
            pass

    def available_tools(self) -> list[str]:
        """Retorna lista de tools disponíveis."""
        return list(self._tools.keys())

    def call_tool(self, tool_name: str, **params: Any) -> tuple[dict[str, Any], float]:
        """Chama uma tool MCP e retorna envelope + tempo de execução.

        Args:
            tool_name: Nome da tool (ex: "bridge_check_newave")
            **params: Parâmetros da tool

        Returns:
            Tupla (envelope, elapsed_ms) onde envelope é o dict de resposta
            e elapsed_ms é o tempo de execução em milissegundos.

        Raises:
            RuntimeError: Se a tool não existir ou falhar.
        """
        start = time.perf_counter_ns()

        if self.target == "local":
            envelope = self._call_local(tool_name, **params)
        else:
            envelope = self._call_remote(tool_name, **params)

        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        return envelope, elapsed_ms

    def _call_local(self, tool_name: str, **params: Any) -> dict[str, Any]:
        """Chama tool via servidor local."""
        import asyncio

        async def _async_call() -> Any:
            return await self._server.call_tool(tool_name, params)

        try:
            # Tenta usar event loop existente ou cria novo
            try:
                loop = asyncio.get_running_loop()
                # Se já tem loop rodando, cria task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _async_call())
                    result = future.result(timeout=120)
            except RuntimeError:
                # Nenhum loop rodando, cria um novo
                result = asyncio.run(_async_call())

            return self._parse_mcp_result(result)

        except Exception as e:
            return {
                "status": "error",
                "message": f"Exceção ao chamar {tool_name}: {type(e).__name__}: {e}",
                "exception": str(e),
            }

    def _call_remote(self, tool_name: str, **params: Any) -> dict[str, Any]:
        """Chama tool via servidor remoto."""
        raise NotImplementedError("Modo remoto não implementado")

    def _parse_mcp_result(self, result: Any) -> dict[str, Any]:
        """Extrai envelope JSON do resultado MCP.

        O FastMCP retorna resultado em diferentes formatos dependendo
        da versão e configuração. Esta função normaliza para dict.
        """
        # Resultado pode ser tupla (content, is_error) ou direto
        if isinstance(result, tuple):
            content = result[0]
        else:
            content = result

        # Content pode ser lista de TextContent ou similar
        if isinstance(content, list) and len(content) > 0:
            first = content[0]
            # TextContent tem atributo .text
            if hasattr(first, "text"):
                try:
                    return json.loads(first.text)
                except json.JSONDecodeError:
                    return {"status": "error", "message": "Resposta não é JSON válido", "raw": first.text}
            # Ou pode ser dict direto
            if isinstance(first, dict):
                return first

        # Se já é dict, retorna direto
        if isinstance(content, dict):
            return content

        # Fallback
        return {
            "status": "error",
            "message": "Formato de resposta inesperado",
            "raw": str(content),
        }

    @property
    def is_local(self) -> bool:
        """True se está em modo local."""
        return self.target == "local"

    @property
    def is_remote(self) -> bool:
        """True se está em modo remoto."""
        return self.target != "local"
