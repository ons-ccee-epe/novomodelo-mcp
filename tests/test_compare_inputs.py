"""Compare: `fmt` é vocabulário fechado no schema da tool; fora dele, recusa sem chamar o bridge."""

import importlib
from typing import get_args

import anyio
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools import post_run as post_run_mod
from novomodelo_mcp.tools.post_run import FormatoCompare, register_post_run

TOOLS = {"bridge_compare_newave": "newave_dir", "bridge_compare_decomp": "decomp_dir"}
FORMATOS = ["console", "html", "csv", "parquet", "json", "all"]


def _server(monkeypatch):
    calls = []

    def _spy(argv, **kwargs):
        calls.append(argv)
        return {"status": "ok", "summary": {}, "diagnostics": [], "exit_code": 0}

    monkeypatch.setattr(post_run_mod, "run_bridge", _spy)
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    mcp = FastMCP("t")
    register_post_run(mcp, load_settings())
    return mcp, calls


def test_schema_publicado_lista_os_formatos(monkeypatch):
    mcp, _ = _server(monkeypatch)
    tools = {t.name: t for t in anyio.run(mcp.list_tools)}
    for name in TOOLS:
        assert tools[name].inputSchema["properties"]["fmt"]["enum"] == FORMATOS


@pytest.mark.parametrize("tool", TOOLS)
def test_formato_fora_da_lista_e_erro_de_tool_sem_chamar_o_bridge(monkeypatch, tool):
    mcp, calls = _server(monkeypatch)
    args = {TOOLS[tool]: "/tmp/src", "output_dir": "/tmp/out"}

    async def _session():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            bad = await client.call_tool(tool, {**args, "fmt": "xml"})
            good = await client.call_tool(tool, {**args, "fmt": "csv"})
            return bad, good

    bad, good = anyio.run(_session)
    assert bad.isError is True
    assert good.isError is False
    assert len(calls) == 1 and calls[0][-2:] == ["--format", "csv"]


def test_vocabulario_igual_ao_do_bridge():
    try:
        args = importlib.import_module("novomodelo_bridge.cli.args")
    except ImportError:
        pytest.skip("novomodelo_bridge não está instalado neste ambiente")
    # `_VALID_CLI_FORMATS` é nome interno do bridge: lido só aqui, em teste.
    assert set(get_args(FormatoCompare)) == set(args._VALID_CLI_FORMATS)
