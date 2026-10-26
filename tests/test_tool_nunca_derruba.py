"""Toda tool devolve envelope, mesmo quando uma biblioteca nativa entra em pânico
(`PanicException` do PyO3 herda de `BaseException`, e nenhum `except Exception` a pega)."""

import anyio
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

import novomodelo_mcp.server as S
from novomodelo_mcp.config import load_settings

pl = pytest.importorskip("polars")


def _servidor(falha: BaseException) -> FastMCP:
    srv = FastMCP("t")
    mcp = S._WithVersionWarnings(srv, load_settings())

    @mcp.tool()
    def quebra() -> dict:
        raise falha

    @mcp.tool()
    def ok() -> dict:
        return {"status": "ok"}

    return srv


@pytest.mark.parametrize("falha", [pl.exceptions.PanicException("simulado"), ValueError("NUL")])
def test_falha_vira_envelope_e_o_servidor_continua(falha):
    async def conversa():
        async with create_connected_server_and_client_session(
            _servidor(falha)._mcp_server, raise_exceptions=False
        ) as c:
            with anyio.fail_after(10):
                r1 = await c.call_tool("quebra", {})
                r2 = await c.call_tool("ok", {})
        return r1, r2

    r1, r2 = anyio.run(conversa)
    assert '"status": "error"' in r1.content[0].text and not r1.isError
    assert '"status": "ok"' in r2.content[0].text


def test_interrupcao_do_processo_nao_e_engolida():
    with pytest.raises(KeyboardInterrupt):
        S._never_raise(lambda: (_ for _ in ()).throw(KeyboardInterrupt()))()
