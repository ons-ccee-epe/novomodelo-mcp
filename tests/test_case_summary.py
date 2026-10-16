"""`case_summary`: o caso como o novomodelo o lê (`io.load_case`), com contagens e teto de ids."""
import dataclasses
import hashlib
import sys
import types

import pytest

import novomodelo_mcp.tools.pre_run as pre_run
from novomodelo_mcp.config import load_settings


def _item(i, prefixo):
    return types.SimpleNamespace(id=i, name=f"{prefixo} {i}", max_storage_hm3=1.0)


def _system():
    return types.SimpleNamespace(
        n_buses=2, n_lines=1, n_hydros=8, n_thermals=3, n_stages=12,
        buses=[_item(i, "barra") for i in range(2)], lines=[_item(0, "linha")],
        hydros=[_item(i, "usina") for i in range(8)], thermals=[_item(i, "térmica") for i in range(3)],
        contracts=[], pumping_stations=[_item(0, "bomba")], non_controllable_sources=[])


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


@pytest.fixture
def tool(monkeypatch, tmp_path):
    estado = {"erro": None, "chamadas": []}

    def load_case(path):
        estado["chamadas"].append(path)
        if estado["erro"]:
            raise estado["erro"]
        return _system()

    pkg = types.ModuleType("novomodelo")
    pkg.io = types.SimpleNamespace(load_case=load_case)
    monkeypatch.setitem(sys.modules, "novomodelo", pkg)
    monkeypatch.setitem(sys.modules, "novomodelo.io", pkg.io)
    case = tmp_path / "ws" / "caso"
    case.mkdir(parents=True)
    (case / "config.json").write_text("{}", encoding="utf-8")
    mcp = _CaptureMCP()
    pre_run.register_pre_run(mcp, dataclasses.replace(load_settings(), workspace=str(tmp_path / "ws"),
                                                      max_inline_rows=5))
    return mcp.tools["case_summary"], case, estado


def test_contagens_e_teto_da_lista_de_ids(tool):
    fn, case, _ = tool
    env = fn(str(case))
    assert env["status"] == "ok"
    assert env["contagens"] == {"barras": 2, "linhas": 1, "hidros": 8, "termicas": 3, "estagios": 12,
                                "contratos": 0, "bombeamento": 1, "fontes_nao_controlaveis": 0}
    hidros = env["itens"]["hidros"]
    assert len(hidros["lista"]) == 5 and hidros["truncado"] is True
    assert hidros["lista"][0] == {"id": 0, "name": "usina 0"}
    assert env["itens"]["termicas"]["truncado"] is False


def test_caso_invalido_vira_envelope(tool):
    fn, case, estado = tool
    estado["erro"] = ValueError("referential integrity: hydro 7 downstream 99 inexistente")
    env = fn(str(case))
    assert env["status"] == "error" and env["exit_code"] == 1
    assert "downstream 99" in " ".join(env["diagnostics"])


def test_caso_fora_do_workspace_e_recusado(tool, tmp_path):
    fn, _, estado = tool
    env = fn(str(tmp_path / "fora"))
    assert env["status"] == "error" and estado["chamadas"] == []


def test_nada_e_criado_nem_alterado_no_caso(tool):
    fn, case, _ = tool

    def _arvore():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
                for p in sorted(case.rglob("*"))}

    antes = _arvore()
    fn(str(case))
    assert _arvore() == antes


def test_biblioteca_ausente_e_127(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "novomodelo", None)
    mcp = _CaptureMCP()
    pre_run.register_pre_run(mcp, dataclasses.replace(load_settings(), workspace=None))
    env = mcp.tools["case_summary"](str(tmp_path))
    assert env["status"] == "error" and env["exit_code"] == 127
