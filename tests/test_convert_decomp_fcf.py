"""`bridge_convert_decomp(importar_fcf=False)` passa `--no-fcf`; o NEWAVE não tem a opção."""

import inspect

import pytest

import novomodelo_mcp.tools.pre_run as pre_run
from novomodelo_mcp.config import load_settings


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def tools(monkeypatch):
    argvs = []
    monkeypatch.setattr(
        pre_run,
        "run_bridge",
        lambda argv, **kw: (
            argvs.append(argv) or {"status": "ok", "exit_code": 0, "diagnostics": []}
        ),
    )
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    mcp = _CaptureMCP()
    pre_run.register_pre_run(mcp, load_settings())
    return mcp.tools, argvs


def test_sem_fcf_passa_no_fcf(tools, tmp_path):
    t, argvs = tools
    t["bridge_convert_decomp"](str(tmp_path / "src"), str(tmp_path / "dst"), importar_fcf=False)
    assert "--no-fcf" in argvs[-1]


def test_padrao_importa_a_fcf(tools, tmp_path):
    t, argvs = tools
    t["bridge_convert_decomp"](str(tmp_path / "src"), str(tmp_path / "dst"))
    assert "--no-fcf" not in argvs[-1]


def test_newave_nao_tem_a_opcao(tools):
    t, _ = tools
    assert "importar_fcf" not in inspect.signature(t["bridge_convert_newave"]).parameters
