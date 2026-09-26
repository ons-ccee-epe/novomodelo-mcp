"""Exercício manual do servidor MCP — chama tools de verdade e imprime o resultado.

Uso:
    uv run python tests/try_tools.py                 # só diagnóstico + lista de tools
    uv run python tests/try_tools.py <pasta_newave>  # também roda bridge_check_newave

Não é um teste de CI (não usa pytest). É um "smoke" interativo para ver o
servidor conversando com o cobre-bridge real.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# torna o pacote em src/ importável sem instalar
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cobre_mcp.server import build_server  # noqa: E402


def _text(result) -> str:
    """Extrai o texto/estrutura de um retorno de call_tool (varia entre versões do mcp)."""
    # mcp 1.x costuma devolver (list[Content], structured) OU list[Content]
    payload = result[0] if isinstance(result, tuple) else result
    if isinstance(payload, list) and payload:
        item = payload[0]
        return getattr(item, "text", str(item))
    return str(payload)


async def main() -> None:
    srv = build_server()
    print(f"== servidor: {srv.name} ==\n")

    tools = await srv.list_tools()
    print("Tools registradas:")
    for t in tools:
        print(f"  - {t.name}")
    print()

    print("== cobre_mcp_info ==")
    info = await srv.call_tool("cobre_mcp_info", {})
    print(_text(info))
    print()

    if len(sys.argv) > 1:
        src = sys.argv[1]
        print(f"== bridge_check_newave(src={src!r}) ==")
        res = await srv.call_tool("bridge_check_newave", {"src": src})
        print(_text(res))


if __name__ == "__main__":
    asyncio.run(main())
