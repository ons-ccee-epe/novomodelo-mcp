"""Referência sem medição de treino (registro de calibração editado à mão) não estima."""

from novomodelo_mcp.adapters import runtime
from novomodelo_mcp.adapters.run_plan import build_plan

DIMS = {"num_stages": 12, "num_hydros": 3, "num_thermals": 2, "num_buses": 1, "num_lines": 0}
SEM_TREINO = {
    "source": "calibracao-editada",
    "threads": 4,
    "completed_at": "2026-10-20T10:00:00Z",
    "config_sig": "sig",
    "train": None,
    "sim": {"wall_per_solve": 0.001},
    "dims": DIMS,
}
PARAMS = {
    "forward_passes": 4,
    "selection_method": "sampled",
    "iteration_limit": 5,
    "stopping_mode": None,
    "simulation_enabled": True,
    "simulation_scenarios": 10,
    "num_stages": 12,
    "openings_per_stage": [3] * 12,
    "openings": {"min": 3, "max": 3, "mean": 3.0},
    "max_order": 2,
    "dimensions": DIMS,
    "config_sig": "sig",
}
MACHINE = {"cpu_count": 8, "performance_cpus": 4, "ram_bytes": 16 * 1024**3}


def test_referencia_sem_medicao_de_treino_da_indeterminado():
    ref = runtime.select_reference([SEM_TREINO], DIMS, "sig")
    assert ref is not None
    plan = build_plan(PARAMS, MACHINE, ref, time_budget_s=900)
    assert plan["verdict"] == "indeterminado"
    assert plan["reference"] is None
    assert any("medição do treino" in w for w in plan["warnings"]), plan["warnings"]
