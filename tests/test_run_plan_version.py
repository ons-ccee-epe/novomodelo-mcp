"""A referência do `run_plan` prefere runs da mesma versão do novomodelo instalado."""
import dataclasses

import novomodelo_mcp.tools.run as run_tools
from novomodelo_mcp.adapters import runtime
from novomodelo_mcp.config import load_settings

DIMS = {"num_stages": 72, "num_hydros": 159, "num_thermals": 107,
        "num_buses": 5, "num_lines": 6}
PARAMS = {
    "forward_passes": 4, "selection_method": "sampled", "iteration_limit": 5,
    "stopping_mode": None, "simulation_enabled": True, "simulation_scenarios": 50,
    "num_stages": 72, "openings_per_stage": [3] * 72,
    "openings": {"min": 3, "max": 3, "mean": 3.0}, "max_order": 6,
    "dimensions": DIMS, "config_sig": "sig",
}
MACHINE = {"machine_id": "m1", "hostname": "h1", "cpu_count": 8,
           "performance_cpus": 4, "ram_bytes": 16 * 1024 ** 3}


def _point(source, version, completed_at):
    return {"source": source, "threads": 4, "completed_at": completed_at,
            "config_sig": "sig", "dims": DIMS, "software_version": version,
            "train": {"wall_per_solve": 0.01}, "sim": {"wall_per_solve": 0.02}}


V17 = _point("run-017", "0.17.0", "2026-10-09T00:00:00Z")
V18 = _point("run-018", "0.18.0", "2026-10-01T00:00:00Z")


def test_so_entram_os_pontos_da_versao_instalada():
    ref = runtime.select_reference([V17, V18], DIMS, "sig", version="v0.18.0")
    assert [p["source"] for p in ref["points"]] == ["run-018"]
    assert not ref.get("version_mismatch")


def test_sem_ponto_da_versao_usa_os_outros_e_marca_a_diferenca():
    ref = runtime.select_reference([V17], DIMS, "sig", version="0.18.0")
    assert [p["source"] for p in ref["points"]] == ["run-017"]
    assert ref["version_mismatch"] is True and ref["versions_used"] == ["0.17.0"]


def test_ponto_sem_versao_so_entra_na_falta_da_mesma_versao():
    unknown = _point("run-antigo", None, "2026-10-11T00:00:00Z")
    ref = runtime.select_reference([unknown, V18], DIMS, "sig", version="0.18.0")
    assert [p["source"] for p in ref["points"]] == ["run-018"]


def test_sem_versao_instalada_o_resultado_nao_muda():
    assert runtime.select_reference([V17, V18], DIMS, "sig", version=None) == \
        runtime.select_reference([V17, V18], DIMS, "sig")


def test_point_from_run_le_cobre_version_de_runs_antigos():
    meta = {"duration_seconds": 10.0, "solve_stats": {"total_lp_solves": 100},
            "cobre_version": "0.17.0"}
    assert runtime.point_from_run(meta)["software_version"] == "0.17.0"
    meta["software_version"] = "0.18.0"
    assert runtime.point_from_run(meta)["software_version"] == "0.18.0"


def test_plano_avisa_quando_a_referencia_e_de_outra_versao(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    settings = dataclasses.replace(load_settings(), state_dir=str(tmp_path / "state"))
    monkeypatch.setattr(run_tools, "read_case_params", lambda case_dir: PARAMS)
    monkeypatch.setattr(run_tools, "version_cli",
                        lambda *, settings: {"status": "ok", "version": "v0.18.0"})
    monkeypatch.setattr(runtime, "find_reference_runs", lambda roots, host: [dict(V17)])
    plan = run_tools.make_plan(str(tmp_path), settings, machine=MACHINE)
    msgs = [w for w in plan["warnings"] if "outra versão do novomodelo" in w]
    assert len(msgs) == 1 and "0.17.0" in msgs[0] and "0.18.0" in msgs[0]
