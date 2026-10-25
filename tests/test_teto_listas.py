"""Listas aninhadas (cortes da política, PAR(p), itens do resumo do caso) também cabem
em NOVOMODELO_MCP_MAX_RESPONSE_KB: a maior lista encolhe até a resposta caber."""
import dataclasses

from novomodelo_mcp.adapters import budget
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.shaping import response_bytes


def _s(kb=50):
    return dataclasses.replace(load_settings(), max_response_kb=kb)


def test_politica_com_milhares_de_cortes_cabe_e_marca_truncado():
    env = {"status": "ok", "estagios": [{"stage_id": i, "n_cortes": 9000} for i in range(60)],
           "cortes": {"estagio": 3, "total": 9000, "truncado": False,
                      "linhas": [{"id": i, "iteracao": i, "intercepto": 1.0e6 + i, "ativo": True}
                                 for i in range(3200)]}}
    out = budget.shrink_to_budget(env, _s())
    assert response_bytes(out) <= 50 * 1024
    assert out["cortes"]["truncado"] is True and 0 < len(out["cortes"]["linhas"]) < 3200
    assert len(out["estagios"]) == 60 and out["cortado_por_tamanho"]["teto_kb"] == 50


def test_varias_listas_encolhem_a_maior_primeiro():
    env = {"status": "ok", "itens": {
        "hidros": {"lista": [{"id": i, "name": f"usina {i}" * 3} for i in range(3000)], "truncado": False},
        "barras": {"lista": [{"id": i, "name": "b"} for i in range(5)], "truncado": False}}}
    out = budget.shrink_to_budget(env, _s(10))
    assert response_bytes(out) <= 10 * 1024
    assert out["itens"]["barras"]["lista"] == env["itens"]["barras"]["lista"]
    assert out["itens"]["hidros"]["truncado"] is True


def test_resposta_pequena_fica_igual():
    env = {"status": "ok", "par": {"linhas": [{"lag": 1}], "truncado": False}}
    assert budget.shrink_to_budget(dict(env), _s()) == env


def test_as_tres_tools_passam_pelo_corte(monkeypatch):
    import inspect
    from novomodelo_mcp.tools import pre_run, results
    fontes = inspect.getsource(results.register_results) + inspect.getsource(pre_run.register_pre_run)
    for tool in ("results_policy", "results_stochastic", "case_summary"):
        corpo = fontes[fontes.index(f"def {tool}("):]
        corpo = corpo[:corpo.index("@mcp.tool") if "@mcp.tool" in corpo else None]
        assert "shrink_to_budget" in corpo, tool
