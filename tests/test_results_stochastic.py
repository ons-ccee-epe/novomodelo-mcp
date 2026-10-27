"""`results_stochastic`: PAR(p) e árvore de aberturas, repassados da biblioteca com filtro e teto."""

import dataclasses
import sys
import types

import pytest

from novomodelo_mcp.adapters import budget

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.results import register_results

np = pytest.importorskip("numpy")


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


class _Stochastic:
    def __init__(self, n_hydros=3, n_stages=4, lags=2):
        self._par = np.array(
            [
                [h, s, lag, 0.1 * lag]
                for h in range(n_hydros)
                for s in range(n_stages)
                for lag in range(1, lags + 1)
            ],
            dtype=float,
        )
        self._stages = n_stages

    def par_coefficients(self):
        return self._par

    def opening_tree(self, stage):
        if not 0 <= stage < self._stages:
            raise IndexError(f"stage {stage} not present in the opening tree")
        return np.arange(20 * 3, dtype=float).reshape(20, 3)


@pytest.fixture
def tool(monkeypatch, tmp_path):
    estado = {"erro": None, "chamadas": []}

    def load_stochastic(output_dir):
        estado["chamadas"].append(output_dir)
        if estado["erro"]:
            raise estado["erro"]
        return _Stochastic()

    monkeypatch.setattr(budget, "row_limit", lambda settings: 5)
    pkg = types.ModuleType("novomodelo")
    pkg.results = types.SimpleNamespace(load_stochastic=load_stochastic)
    monkeypatch.setitem(sys.modules, "novomodelo", pkg)
    monkeypatch.setitem(sys.modules, "novomodelo.results", pkg.results)
    ws = tmp_path / "ws"
    (ws / "output").mkdir(parents=True)
    mcp = _CaptureMCP()
    register_results(mcp, dataclasses.replace(load_settings(), workspace=str(ws)))
    return mcp.tools["results_stochastic"], str(ws / "output"), estado


def test_par_filtrado_por_usina_e_estagio(tool):
    fn, out, _ = tool
    env = fn(out, hydro_id=1, stage=2)
    assert env["status"] == "ok"
    assert env["par"]["linhas"] == [
        {"hydro_id": 1, "stage_id": 2, "lag": 1, "coefficient": 0.1},
        {"hydro_id": 1, "stage_id": 2, "lag": 2, "coefficient": 0.2},
    ]
    assert env["par"]["total"] == 2 and env["par"]["truncado"] is False


def test_par_sem_filtro_respeita_o_teto(tool):
    fn, out, _ = tool
    env = fn(out)
    assert len(env["par"]["linhas"]) == 5
    assert env["par"]["total"] == 3 * 4 * 2 and env["par"]["truncado"] is True
    assert "aberturas" not in env


def test_arvore_de_aberturas_do_estagio_com_teto(tool):
    fn, out, _ = tool
    env = fn(out, aberturas_do_estagio=0)
    arv = env["aberturas"]
    assert arv["estagio"] == 0 and arv["n_aberturas"] == 20 and arv["dim"] == 3
    assert len(arv["linhas"]) == 5 and arv["truncado"] is True
    assert arv["linhas"][0] == [0.0, 1.0, 2.0]


def test_estagio_inexistente_na_arvore_e_erro_22(tool):
    fn, out, _ = tool
    env = fn(out, aberturas_do_estagio=99)
    assert env["status"] == "error" and env["exit_code"] == 22


def test_sem_exportacao_estocastica_explica_o_que_ligar(tool):
    fn, out, estado = tool
    estado["erro"] = FileNotFoundError("stochastic/inflow_ar_coefficients.parquet not found")
    env = fn(out)
    assert env["status"] == "error" and env["exit_code"] == 2
    assert "exports.stochastic" in " ".join(env["diagnostics"])


def test_output_dir_fora_do_workspace_e_recusado(tool, tmp_path):
    fn, _, estado = tool
    env = fn(str(tmp_path / "fora"))
    assert env["status"] == "error" and estado["chamadas"] == []


def test_biblioteca_ausente_e_127(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "novomodelo", None)
    mcp = _CaptureMCP()
    register_results(mcp, dataclasses.replace(load_settings(), workspace=None))
    env = mcp.tools["results_stochastic"](str(tmp_path))
    assert env["status"] == "error" and env["exit_code"] == 127
