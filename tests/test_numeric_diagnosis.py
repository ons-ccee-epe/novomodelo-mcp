"""Run que falhou: a razão de coeficientes do executável é repassada; acima do limiar, nota heurística.

Fixture com os números do `training/scaling_report.json` de um run 0.18 real que falhou
(NEWAVE reduzido, coeficientes da FPHA da ordem de 1e-21).
"""

import dataclasses
import hashlib
import json

import pytest

import novomodelo_mcp.tools.run as run_tools
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.results import register_results

REAL_FALHOU = {
    "cost_scale_factor": 1000000.0,
    "stages": [
        {
            "stage_id": 0,
            "pre_scaling": {
                "matrix_coeff_range": [1.5335148496497908e-21, 744.0],
                "matrix_coeff_ratio": 4.851599579683936e23,
            },
        },
        {
            "stage_id": 1,
            "pre_scaling": {"matrix_coeff_range": [1e-3, 10.0], "matrix_coeff_ratio": 1e4},
        },
    ],
    "summary": {
        "worst_pre_scaling_matrix_ratio": 4.851599579683936e23,
        "worst_post_scaling_matrix_ratio": 80432641056.08427,
        "improvement_factor": 6031878993381.556,
        "num_stages": 113,
    },
}
CONVERGIU = {
    "stages": [
        {
            "stage_id": 0,
            "pre_scaling": {
                "matrix_coeff_range": [4.7e-9, 6.39],
                "matrix_coeff_ratio": 1353501916.09,
            },
        }
    ],
    "summary": {
        "worst_pre_scaling_matrix_ratio": 1353501916.09,
        "worst_post_scaling_matrix_ratio": 276144.82,
    },
}
META_ERRO = {
    "status": "complete",
    "convergence": {"termination_reason": "error"},
    "iterations": {"completed": 3, "converged_at": None},
}
META_LIMITE = {
    "status": "complete",
    "convergence": {"termination_reason": "iteration_limit"},
    "iterations": {"completed": 5, "converged_at": None},
}


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _output(tmp_path, meta, report):
    out = tmp_path / "caso" / "output"
    (out / "training").mkdir(parents=True)
    (out / "training" / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    if report is not None:
        text = report if isinstance(report, str) else json.dumps(report)
        (out / "training" / "scaling_report.json").write_text(text, encoding="utf-8")
    (tmp_path / "caso" / "config.json").write_text("{}", encoding="utf-8")
    return out


def _tools(tmp_path, monkeypatch, out, state):
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    settings = dataclasses.replace(load_settings(), state_dir=str(tmp_path / "state"))
    monkeypatch.setattr(
        run_tools.jobs,
        "job_state",
        lambda settings, job_id: {"job_id": job_id, "state": state, "output": str(out)},
    )
    monkeypatch.setattr(run_tools.jobs, "job_stderr", lambda *a, **k: "falhou")
    monkeypatch.setattr(run_tools, "harvest_calibrations", lambda settings: 0)
    mcp = _CaptureMCP()
    run_tools.register_run(mcp, settings)
    register_results(mcp, settings)
    return (lambda: mcp.tools["run_status"]("j1"), lambda: mcp.tools["results_status"](str(out)))


def test_job_falhou_com_razao_1e22_tem_diagnostico_heuristico(tmp_path, monkeypatch):
    report = json.loads(json.dumps(REAL_FALHOU))
    report["summary"]["worst_pre_scaling_matrix_ratio"] = 1e22
    report["stages"][0]["pre_scaling"]["matrix_coeff_ratio"] = 1e22
    out = _output(tmp_path, META_ERRO, report)
    env = _tools(tmp_path, monkeypatch, out, "failed")[0]()
    d = env["diagnostico_heuristico"]
    assert d["nota"].startswith("Heurística") and d["razao"] == 1e22 and d["estagio"] == 0


@pytest.mark.parametrize("tool", [0, 1], ids=["run_status", "results_status"])
def test_numeros_do_executavel_saem_identicos(tmp_path, monkeypatch, tool):
    out = _output(tmp_path, META_ERRO, REAL_FALHOU)
    env = _tools(tmp_path, monkeypatch, out, "failed")[tool]()
    assert env["escalonamento"] == {
        "razao_pre": 4.851599579683936e23,
        "razao_pos": 80432641056.08427,
        "estagio": 0,
        "faixa": [1.5335148496497908e-21, 744.0],
    }
    assert env["diagnostico_heuristico"]["faixa"] == [1.5335148496497908e-21, 744.0]


def test_falhou_abaixo_do_limiar_mostra_a_razao_sem_nota(tmp_path, monkeypatch):
    out = _output(tmp_path, META_ERRO, CONVERGIU)
    env = _tools(tmp_path, monkeypatch, out, "failed")[0]()
    assert env["escalonamento"]["razao_pre"] == 1353501916.09
    assert "diagnostico_heuristico" not in env


@pytest.mark.parametrize("tool", [0, 1], ids=["run_status", "results_status"])
def test_run_que_nao_falhou_nao_tem_diagnostico(tmp_path, monkeypatch, tool):
    out = _output(tmp_path, META_LIMITE, REAL_FALHOU)
    env = _tools(tmp_path, monkeypatch, out, "succeeded")[tool]()
    assert "escalonamento" not in env and "diagnostico_heuristico" not in env


@pytest.mark.parametrize("report", [None, "{quebrado"], ids=["ausente", "corrompido"])
def test_relatorio_ausente_ou_corrompido_sem_diagnostico_e_sem_excecao(
    tmp_path, monkeypatch, report
):
    out = _output(tmp_path, META_ERRO, report)
    env = _tools(tmp_path, monkeypatch, out, "failed")[0]()
    assert env["status"] == "ok"
    assert "escalonamento" not in env and "diagnostico_heuristico" not in env


def test_o_caso_nao_e_alterado(tmp_path, monkeypatch):
    out = _output(tmp_path, META_ERRO, REAL_FALHOU)
    case = tmp_path / "caso"

    def _hash():
        return {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(case.rglob("*"))
            if p.is_file()
        }

    antes = _hash()
    run_status, results_status = _tools(tmp_path, monkeypatch, out, "failed")
    run_status()
    results_status()
    assert _hash() == antes
