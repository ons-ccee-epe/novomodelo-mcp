"""Integracao das tools de compare com a validacao de entrada (pytest).

Garante que uma entrada invalida (tolerance/format) e barrada ANTES de invocar
o cobre-bridge: o envelope de erro e retornado e ``run_bridge`` nao e chamado.
Registra as tools num ``FastMCP`` real e recupera a funcao via ToolManager,
com ``run_bridge`` substituido por um espiao (nao depende de duckdb/polars).
"""
import pytest

from mcp.server.fastmcp import FastMCP

from cobre_mcp.config import load_settings
from cobre_mcp.tools import post_run as post_run_mod
from cobre_mcp.tools.post_run import register_post_run


def _build(monkeypatch):
    """Registra as tools com run_bridge espiao; sem workspace (irrestrito)."""
    calls = {"n": 0}

    def _spy(argv, **kwargs):
        calls["n"] += 1
        return {"schema_version": "1", "command": " ".join(argv[:2]),
                "status": "ok", "summary": {}, "diagnostics": [], "exit_code": 0}

    monkeypatch.setattr(post_run_mod, "run_bridge", _spy)
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)

    mcp = FastMCP("t")
    register_post_run(mcp, load_settings())
    return mcp, calls


def _fn(mcp, name):
    return mcp._tool_manager.get_tool(name).fn


@pytest.mark.parametrize("tool", ["bridge_compare_newave", "bridge_compare_decomp"])
def test_tolerance_invalida_nao_chama_bridge(monkeypatch, tool):
    mcp, calls = _build(monkeypatch)
    env = _fn(mcp, tool)("/tmp/src", "/tmp/cobre", tolerance=9.0)
    assert env["status"] == "error"
    assert calls["n"] == 0, "run_bridge nao deve ser chamado com entrada invalida"


@pytest.mark.parametrize("tool", ["bridge_compare_newave", "bridge_compare_decomp"])
def test_fmt_invalido_nao_chama_bridge(monkeypatch, tool):
    mcp, calls = _build(monkeypatch)
    env = _fn(mcp, tool)("/tmp/src", "/tmp/cobre", fmt="xml")
    assert env["status"] == "error"
    assert calls["n"] == 0


@pytest.mark.parametrize("tool", ["bridge_compare_newave", "bridge_compare_decomp"])
def test_entrada_valida_chama_bridge(monkeypatch, tool):
    mcp, calls = _build(monkeypatch)
    env = _fn(mcp, tool)("/tmp/src", "/tmp/cobre", tolerance=0.5, fmt="json")
    assert calls["n"] == 1, "run_bridge deve ser chamado quando a entrada e valida"
    assert env["status"] == "ok"
