"""Regressão: caso minúsculo com orçamento estourado não pode quebrar o plano.

Achado pela bateria e2e (scripts/e2e_live.py): `1dtoy` com 1 000 000 de iterações e
orçamento de 1 s. O tempo de UMA iteração (≈0,003 s) era arredondado para 0,0 e a
redução de iterações dividia por zero (`ZeroDivisionError`), derrubando o run_start.
"""

from novomodelo_mcp.adapters.run_plan import build_plan

PARAMS = {
    "forward_passes": 1, "selection_method": "sampled", "iteration_limit": 1_000_000,
    "stopping_mode": None, "simulation_enabled": False, "simulation_scenarios": 0,
    "num_stages": 4, "openings_per_stage": [10, 10, 10, 10],
    "openings": {"min": 10, "max": 10, "mean": 10.0}, "max_order": 0,
    "dimensions": {"num_stages": 4, "num_hydros": 1}, "config_sig": "x",
}
POINT = {"source": "ref", "threads": 4, "completed_at": "2026-10-11T00:00:00Z",
         "config_sig": "x", "train": {"wall_per_solve": 0.00006}, "sim": None}
REF = {"level": 3, "level_name": "mesma_modelagem", "points": [POINT], "candidates": [POINT]}
MACHINE = {"cpu_count": 8, "performance_cpus": 4, "ram_bytes": 16 * 1024 ** 3}


def test_orcamento_estourado_em_caso_minusculo_nao_divide_por_zero():
    plan = build_plan(PARAMS, MACHINE, REF, time_budget_s=1)
    assert plan["status"] == "ok"
    assert plan["verdict"] in ("cabe_com_ajustes", "nao_cabe")
    assert plan["params_suggested"]["iteration_limit"] < PARAMS["iteration_limit"]


def test_campos_internos_nao_vazam_na_resposta():
    plan = build_plan(PARAMS, MACHINE, REF, time_budget_s=1)
    for key in ("current", "suggested"):
        assert not [k for k in plan["time"][key] if k.startswith("_")]
