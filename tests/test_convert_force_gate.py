"""`force` no convert apaga o deck de destino (o bridge limpa `dst`): exige o mesmo
gate do `case_init` (NOVOMODELO_MCP_ALLOW_FORCE=1), nos dois trilhos."""

import dataclasses

import pytest

import novomodelo_mcp.tools.pre_run as P
from novomodelo_mcp.config import load_settings


class _Cap:
    def __init__(self):
        self.tools = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def tools(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        P, "run_bridge", lambda argv, settings: chamadas.append(argv) or {"exit_code": 0}
    )

    def registrar(allow_force):
        cap = _Cap()
        P.register_pre_run(
            cap,
            dataclasses.replace(load_settings(), workspace=str(tmp_path), allow_force=allow_force),
        )
        return cap.tools

    return registrar, chamadas, tmp_path


@pytest.mark.parametrize("trilho", ["newave", "decomp"])
def test_convert_force_exige_allow_force(tools, trilho):
    registrar, chamadas, ws = tools
    env = registrar(False)[f"bridge_convert_{trilho}"](str(ws / "src"), str(ws / "dst"), force=True)
    assert env["status"] == "error" and env["exit_code"] == 13
    assert chamadas == []


@pytest.mark.parametrize("trilho", ["newave", "decomp"])
def test_convert_force_com_gate_ou_em_dry_run_segue(tools, trilho):
    registrar, chamadas, ws = tools
    registrar(True)[f"bridge_convert_{trilho}"](str(ws / "src"), str(ws / "dst"), force=True)
    registrar(False)[f"bridge_convert_{trilho}"](
        str(ws / "src"), str(ws / "dst"), force=True, dry_run=True
    )
    assert len(chamadas) == 2 and all("--force" in a for a in chamadas)
