"""Servidor MCP falso (stdio) para o teste de integração do motor de carga.

Expõe três tools somente leitura com os nomes do mix. Com ``FAKE_HANG_AFTER=N``
o processo para de responder depois de N chamadas, o que simula uma sessão
travada. Uso: ``python fake_mcp_server.py [--marker=<id>]`` (o marcador só
identifica o processo na linha de comando).
"""

from __future__ import annotations

import os
import time

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

server = FastMCP("fake-novomodelo")
_hang_after = int(os.environ.get("FAKE_HANG_AFTER", "0"))
_calls = 0


def _count_call() -> None:
    global _calls
    _calls += 1
    if _hang_after and _calls > _hang_after:
        time.sleep(3600)


@server.tool(annotations=READ_ONLY)
def docs_list() -> dict:
    _count_call()
    return {"status": "ok", "pages": []}


@server.tool(annotations=READ_ONLY)
def docs_search(consulta: str, k: int = 5) -> dict:
    _count_call()
    return {"status": "ok", "consulta": consulta, "resultados": []}


@server.tool(annotations=READ_ONLY)
def schema_list() -> dict:
    _count_call()
    return {"status": "ok", "types": ["config"]}


if __name__ == "__main__":
    server.run()
