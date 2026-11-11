"""Teto por tamanho: as tools que devolvem linhas cabem em NOVOMODELO_MCP_MAX_RESPONSE_KB
(como o cliente recebe: JSON indentado), em vez de um número fixo de linhas."""

import dataclasses
import json

import pytest

from novomodelo_mcp.adapters import budget
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.results import register_results
from novomodelo_mcp.tools.shaping import fit_to_budget, response_bytes

pl = pytest.importorskip("polars")


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def test_padrao_e_50_kb_e_a_variavel_muda(monkeypatch):
    assert load_settings().max_response_kb == 50
    monkeypatch.setenv("NOVOMODELO_MCP_MAX_RESPONSE_KB", "20")
    s = load_settings()
    assert s.max_response_kb == 20 and budget.row_limit(s) == 20 * 1024 // 16


def test_corta_pelo_tamanho_e_diz_quanto_veio():
    s = dataclasses.replace(load_settings(), max_response_kb=4)
    env = {
        "status": "ok",
        "truncated": False,
        "rows": [{"c": "x" * 100, "i": i} for i in range(200)],
    }
    out = fit_to_budget(env, s, "rows")
    assert response_bytes(out) <= 4 * 1024
    assert out["truncated"] is True and 0 < len(out["rows"]) < 200
    assert out["size_truncation"] == {
        "limit_kb": 4,
        "rows_returned": len(out["rows"]),
        "rows_total": 200,
    }


def test_resposta_que_cabe_fica_igual():
    s = load_settings()
    env = {"status": "ok", "truncated": False, "rows": [{"i": 1}]}
    assert fit_to_budget(dict(env), s, "rows") == env


@pytest.fixture
def query(tmp_path):
    out = tmp_path / "ws" / "output"
    part = out / "simulation" / "hydros" / "scenario_id=0"
    part.mkdir(parents=True)
    n = 3000
    larga = {f"col_{k:02d}": [float(k)] * n for k in range(41)}
    pl.DataFrame({"scenario_id": [0] * n, "stage_id": list(range(n)), **larga}).write_parquet(
        part / "d.parquet"
    )
    mcp = _CaptureMCP()
    settings = dataclasses.replace(load_settings(), workspace=str(tmp_path / "ws"))
    register_results(mcp, settings)
    return mcp.tools["results_query"], str(out), settings


def test_consulta_estreita_traz_muito_mais_que_50_linhas(query):
    fn, out, settings = query
    r = fn(out, "hydros", columns=["stage_id", "col_01"], limit=1000)
    assert r["row_count"] > 500 and response_bytes(r) <= settings.max_response_kb * 1024
    r = fn(out, "hydros", columns=["stage_id"], limit=1000)
    assert r["row_count"] == 1000 and "size_truncation" not in r


def test_consulta_larga_cabe_no_orcamento_e_aponta_o_deck_sql(query):
    fn, out, settings = query
    r = fn(out, "hydros", limit=1000)
    assert response_bytes(r) <= settings.max_response_kb * 1024
    assert r["truncated"] is True and r["size_truncation"]["rows_returned"] == len(r["rows"])
    assert "deck_sql" in r["next"]


def test_deck_sql_estreito_passa_de_mil_linhas_e_o_largo_cabe(tmp_path):
    from novomodelo_mcp.adapters.sql import run_readonly_sql

    p = tmp_path / "t.parquet"
    pl.DataFrame(
        {"i": list(range(1500)), **{f"c{k}": [1.5] * 1500 for k in range(40)}}
    ).write_parquet(p)
    s = dataclasses.replace(load_settings(), workspace=str(tmp_path))
    estreito = run_readonly_sql(f"SELECT i FROM read_parquet('{p}')", settings=s)
    assert estreito["row_count"] == 1500 and estreito["truncated"] is False
    largo = run_readonly_sql(f"SELECT * FROM read_parquet('{p}')", settings=s)
    assert response_bytes(largo) <= s.max_response_kb * 1024 and largo["truncated"] is True
    assert json.loads(json.dumps(largo))["size_truncation"]["limit_kb"] == 50
