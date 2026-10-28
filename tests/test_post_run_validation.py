"""Tools de compare: o MCP checa só o tipo da tolerância; o valor é do bridge.

Registra as tools num ``FastMCP`` real e recupera a funcao via ToolManager,
com ``run_bridge`` substituido por um espiao (nao depende de duckdb/polars).
"""

import pytest
from mcp.server.fastmcp import FastMCP

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools import post_run as post_run_mod
from novomodelo_mcp.tools.post_run import register_post_run


def _build(monkeypatch):
    """Registra as tools com run_bridge espiao; sem workspace (irrestrito)."""
    calls = {"n": 0, "argv": None}

    def _spy(argv, **kwargs):
        calls["n"] += 1
        calls["argv"] = argv
        return {
            "schema_version": "1",
            "command": " ".join(argv[:2]),
            "status": "ok",
            "summary": {},
            "diagnostics": [],
            "exit_code": 0,
        }

    monkeypatch.setattr(post_run_mod, "run_bridge", _spy)
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)

    mcp = FastMCP("t")
    register_post_run(mcp, load_settings())
    return mcp, calls


def _fn(mcp, name):
    return mcp._tool_manager.get_tool(name).fn


@pytest.mark.parametrize("tool", ["bridge_compare_newave", "bridge_compare_decomp"])
def test_tolerance_fora_de_0_1_chega_ao_bridge(monkeypatch, tool):
    mcp, calls = _build(monkeypatch)
    _fn(mcp, tool)("/tmp/src", "/tmp/novomodelo", tolerance=9.0)
    assert calls["n"] == 1
    i = calls["argv"].index("--tolerance")
    assert calls["argv"][i + 1] == "9.0"


@pytest.mark.parametrize("tool", ["bridge_compare_newave", "bridge_compare_decomp"])
def test_tolerance_booleana_e_erro_de_tipo(monkeypatch, tool):
    mcp, calls = _build(monkeypatch)
    env = _fn(mcp, tool)("/tmp/src", "/tmp/novomodelo", tolerance=True)
    assert env["status"] == "error" and env["exit_code"] == 2
    assert "tolerance deve ser número" in " ".join(env["diagnostics"])
    assert calls["n"] == 0


@pytest.mark.parametrize("tool", ["bridge_compare_newave", "bridge_compare_decomp"])
def test_entrada_valida_chama_bridge(monkeypatch, tool):
    mcp, calls = _build(monkeypatch)
    env = _fn(mcp, tool)("/tmp/src", "/tmp/novomodelo", tolerance=0.5, fmt="json")
    assert calls["n"] == 1, "run_bridge deve ser chamado quando a entrada e valida"
    assert env["status"] == "ok"


@pytest.mark.parametrize("tool", ["bridge_compare_newave", "bridge_compare_decomp"])
def test_segundo_argumento_e_a_pasta_de_saida(monkeypatch, tool):
    """O bridge recebe a pasta de SAÍDA do run (`novomodelo_output_dir`), não a do caso.

    Regressão: no rename o parâmetro virou `case_dir`, nome que induzia o agente a
    passar a pasta do caso.
    """
    import inspect

    mcp, _ = _build(monkeypatch)
    params = list(inspect.signature(_fn(mcp, tool)).parameters)
    assert params[1] == "output_dir"
    assert "case_dir" not in params
