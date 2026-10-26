"""As tools de resultados recusam a pasta do caso e apontam a pasta da rodada."""
import dataclasses
import json

import pytest

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.server import SERVER_INSTRUCTIONS
from novomodelo_mcp.tools.results import register_results


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


CHAMADAS = {
    "results_status": {},
    "results_convergence": {},
    "results_stochastic": {},
    "results_policy": {},
    "results_list_entities": {},
    "results_query": {"entity": "buses"},
}


@pytest.fixture
def caso(tmp_path):
    caso = tmp_path / "caso"
    (caso / "output" / "training").mkdir(parents=True)
    (caso / "output" / "training" / "metadata.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8")
    mcp = _CaptureMCP()
    register_results(mcp, dataclasses.replace(load_settings(), workspace=str(tmp_path)))
    return caso, mcp.tools


@pytest.mark.parametrize("tool", sorted(CHAMADAS))
def test_pasta_do_caso_e_recusada_com_a_rodada_sugerida(caso, tool):
    pasta, tools = caso
    out = tools[tool](output_dir=str(pasta), **CHAMADAS[tool])
    assert out["status"] == "error"
    assert out["output_sugerido"] == str(pasta / "output")


def test_list_entities_nao_responde_vazio_para_a_pasta_do_caso(caso):
    pasta, tools = caso
    assert "entities" not in tools["results_list_entities"](output_dir=str(pasta))


def test_instrucoes_mandam_direto_para_as_tools_de_resultados():
    assert "`results_*`" in SERVER_INSTRUCTIONS
    assert "output_sugerido" in SERVER_INSTRUCTIONS
    assert "`rodadas`" in SERVER_INSTRUCTIONS


def test_busca_de_rodadas_nao_segue_link_para_fora(tmp_path):
    from novomodelo_mcp.adapters.results import find_runs
    fora = tmp_path / "fora"
    (fora / "training").mkdir(parents=True)
    (fora / "training" / "metadata.json").write_text("{}", encoding="utf-8")
    caso = tmp_path / "caso"
    caso.mkdir()
    try:
        (caso / "atalho").symlink_to(fora, target_is_directory=True)
    except OSError:
        pytest.skip("sem permissão para criar link simbólico")
    assert find_runs(caso) == []
