"""`results_query`: `entity` é um nome dentro de `simulation/`; nada fora do workspace é lido."""

import dataclasses
import os

import pytest

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.results import register_results

pl = pytest.importorskip("polars")


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def setup(tmp_path):
    ws, fora = tmp_path / "ws", tmp_path / "fora"
    out = ws / "output"
    (out / "simulation" / "hydros" / "scenario_id=0").mkdir(parents=True)
    pl.DataFrame({"stage_id": [0], "x": [1.0]}).write_parquet(
        out / "simulation" / "hydros" / "scenario_id=0" / "data.parquet"
    )
    fora.mkdir()
    pl.DataFrame({"segredo": [42]}).write_parquet(fora / "x.parquet")
    mcp = _CaptureMCP()
    register_results(mcp, dataclasses.replace(load_settings(), workspace=str(ws)))
    return mcp.tools["results_query"], str(out), fora


@pytest.mark.parametrize("entity", ["../../../fora", "hydros/../../x", "/abs", "..\\x", ""])
def test_entity_que_nao_e_nome_simples_e_recusada(setup, entity):
    query, out, _ = setup
    env = query(out, entity)
    assert env["status"] == "error" and env["exit_code"] == 13
    assert "rows" not in env and "42" not in str(env)


def test_link_simbolico_com_nome_valido_e_recusado(setup):
    query, out, fora = setup
    try:
        os.symlink(fora, os.path.join(out, "simulation", "link"))
    except OSError:
        pytest.skip("este sistema não permite criar link simbólico")
    env = query(out, "link")
    assert env["status"] == "error" and env["exit_code"] == 13
    assert "rows" not in env and "42" not in str(env)


def test_entity_valida_continua_funcionando(setup):
    query, out, _ = setup
    env = query(out, "hydros")
    assert env["status"] == "ok" and env["rows"] == [{"stage_id": 0, "x": 1.0}]
