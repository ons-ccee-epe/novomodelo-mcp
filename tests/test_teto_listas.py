"""Listas aninhadas (cortes da política, PAR(p), itens do resumo do caso) também cabem
em NOVOMODELO_MCP_MAX_RESPONSE_KB: a maior lista encolhe até a resposta caber."""

import dataclasses

from novomodelo_mcp.adapters import budget
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.shaping import response_bytes


def _s(kb=50):
    return dataclasses.replace(load_settings(), max_response_kb=kb)


def test_politica_com_milhares_de_cortes_cabe_e_marca_truncado():
    env = {
        "status": "ok",
        "stages": [{"stage_id": i, "n_cuts": 9000} for i in range(60)],
        "cuts": {
            "stage": 3,
            "total": 9000,
            "truncated": False,
            "rows": [
                {"id": i, "iteracao": i, "intercepto": 1.0e6 + i, "ativo": True}
                for i in range(3200)
            ],
        },
    }
    out = budget.shrink_to_budget(env, _s())
    assert response_bytes(out) <= 50 * 1024
    assert out["cuts"]["truncated"] is True and 0 < len(out["cuts"]["rows"]) < 3200
    assert len(out["stages"]) == 60 and out["size_truncation"]["limit_kb"] == 50


def test_varias_listas_encolhem_a_maior_primeiro():
    env = {
        "status": "ok",
        "items": {
            "hydros": {
                "entries": [{"id": i, "name": f"usina {i}" * 3} for i in range(3000)],
                "truncated": False,
            },
            "buses": {"entries": [{"id": i, "name": "b"} for i in range(5)], "truncated": False},
        },
    }
    out = budget.shrink_to_budget(env, _s(10))
    assert response_bytes(out) <= 10 * 1024
    assert out["items"]["buses"]["entries"] == env["items"]["buses"]["entries"]
    assert out["items"]["hydros"]["truncated"] is True


def test_resposta_pequena_fica_igual():
    env = {"status": "ok", "par": {"rows": [{"lag": 1}], "truncated": False}}
    assert budget.shrink_to_budget(dict(env), _s()) == env


def test_as_tres_tools_passam_pelo_corte(monkeypatch):
    import inspect

    from novomodelo_mcp.tools import pre_run, results

    fontes = inspect.getsource(results.register_results) + inspect.getsource(
        pre_run.register_pre_run
    )
    for tool in ("results_policy", "results_stochastic", "case_summary"):
        corpo = fontes[fontes.index(f"def {tool}(") :]
        corpo = corpo[: corpo.index("@mcp.tool") if "@mcp.tool" in corpo else None]
        assert "shrink_to_budget" in corpo, tool
