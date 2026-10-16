"""Sem run de mesmas dimensões, a referência é a de tamanho mais parecido.

Caso real: para um NEWAVE reduzido convertido (161 hidros, 158 térmicas), o run
mais recente era o `1dtoy` (1 hidro), que estimaria 5 s com veredito `cabe`; o run
real passou de 4 minutos.
"""

from novomodelo_mcp.adapters import runtime
from novomodelo_mcp.adapters.run_plan import build_plan

CASE_DIMS = {"num_stages": 113, "num_hydros": 161, "num_thermals": 158,
             "num_buses": 5, "num_lines": 6}
TOY = {"source": "1dtoy", "threads": 4, "completed_at": "2026-10-11T02:09:09Z",
       "config_sig": "toy", "train": {"wall_per_solve": 0.00006},
       "sim": {"wall_per_solve": 0.0007},
       "dims": {"num_stages": 4, "num_hydros": 1, "num_thermals": 2, "num_buses": 1}}
CASO_GRANDE = {"source": "caso_grande", "threads": 5, "completed_at": "2026-10-07T20:44:07Z",
         "config_sig": "jan", "train": {"wall_per_solve": 0.0148},
         "sim": {"wall_per_solve": 0.0239},
         "dims": {"num_stages": 72, "num_hydros": 159, "num_thermals": 107,
                  "num_buses": 5, "num_lines": 6}}
PARAMS = {
    "forward_passes": 4, "selection_method": "sampled", "iteration_limit": 5,
    "stopping_mode": None, "simulation_enabled": True, "simulation_scenarios": 50,
    "num_stages": 113, "openings_per_stage": [3] * 113,
    "openings": {"min": 3, "max": 3, "mean": 3.0}, "max_order": 6,
    "dimensions": CASE_DIMS, "config_sig": "novo",
}
MACHINE = {"cpu_count": 8, "performance_cpus": 4, "ram_bytes": 16 * 1024 ** 3}


def test_escolhe_o_caso_de_tamanho_mais_parecido_e_nao_o_mais_recente():
    ref = runtime.select_reference([TOY, CASO_GRANDE], CASE_DIMS, "novo")
    assert ref["level_name"] == "outro_caso"
    assert [p["source"] for p in ref["points"]] == ["caso_grande"]
    assert ref["size_ratio"] < 2


def test_estimativa_usa_a_referencia_parecida():
    ref = runtime.select_reference([TOY, CASO_GRANDE], CASE_DIMS, "novo")
    plan = build_plan(PARAMS, MACHINE, ref, time_budget_s=900)
    assert plan["time"]["current"]["total_seconds"] > 60   # e não ~5 s como antes
    assert plan["verdict"] != "indeterminado"


def test_so_caso_de_brinquedo_disponivel_da_indeterminado():
    ref = runtime.select_reference([TOY], CASE_DIMS, "novo")
    assert ref["size_ratio"] > runtime.MAX_SIZE_RATIO
    plan = build_plan(PARAMS, MACHINE, ref, time_budget_s=900)
    assert plan["verdict"] == "indeterminado"
    assert any("não é estimável" in w for w in plan["warnings"])
