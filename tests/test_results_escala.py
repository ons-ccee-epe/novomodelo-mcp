"""`results_query` em escala: quando o recorte não cabe na resposta, ela diz como
seguir pelo `deck_sql` (que já lê todas as partições), em vez de só truncar."""
import dataclasses

import pytest

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.server import SERVER_INSTRUCTIONS
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
def query(tmp_path):
    out = tmp_path / "estudo ação" / "output"
    for cen in range(3):
        part = out / "simulation" / "hydros" / f"scenario_id={cen}"
        part.mkdir(parents=True)
        pl.DataFrame({"scenario_id": [cen] * 40, "stage_id": list(range(40)), "hydro_id": [1] * 40,
                      "storage_final_hm3": [float(i) for i in range(40)]}).write_parquet(part / "d.parquet")
    mcp = _CaptureMCP()
    settings = dataclasses.replace(load_settings(), workspace=str(tmp_path))
    register_results(mcp, settings)
    return mcp.tools["results_query"], out, settings


def test_truncado_traz_o_proximo_passo_com_o_glob_das_particoes(query):
    results_query, out, settings = query
    r = results_query(str(out), "hydros", limit=1000)
    assert r["truncated"] is True and r["row_count"] == settings.max_inline_rows
    glob = (out.resolve() / "simulation" / "hydros").as_posix() + "/**/*.parquet"
    assert "deck_sql" in r["proximo_passo"] and f"read_parquet('{glob}')" in r["proximo_passo"]


def test_limit_acima_do_teto_avisa_o_limite_aplicado(query):
    results_query, out, settings = query
    r = results_query(str(out), "hydros", limit=1000)
    assert r["limite_aplicado"] == settings.max_inline_rows


def test_so_a_resposta_truncada_traz_proximo_passo(query):
    results_query, out, _ = query
    r = results_query(str(out), "hydros", scenario=0, limit=5)
    assert r["truncated"] is True and "proximo_passo" in r
    r = results_query(str(out), "hydros", group_by=["hydro_id"], agg="max", columns=["storage_final_hm3"])
    assert r["truncated"] is False and "proximo_passo" not in r and "limite_aplicado" not in r


def test_descricao_e_instrucoes_apontam_o_deck_sql_para_varredura(query):
    results_query, _, _ = query
    assert "deck_sql" in results_query.__doc__ and "**/*.parquet" in results_query.__doc__
    assert "deck_sql" in SERVER_INSTRUCTIONS
