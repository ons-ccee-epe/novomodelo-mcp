"""`run_status` e `results_status` repassam como a rodada terminou, sem interpretar.

`_SUCCESS` e `status: complete` aparecem também numa rodada que parou no limite de
iterações sem convergir; o motivo está em `convergence.termination_reason`.
"""
import dataclasses
import json

import pytest

import novomodelo_mcp.tools.run as run_tools
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.results import register_results

LIMITE_018 = {"status": "complete", "software_version": "0.18.0",
              "iterations": {"completed": 5, "converged_at": None},
              "convergence": {"achieved": False, "final_gap_percent": 12.5,
                              "termination_reason": "iteration_limit"}}
ANTIGO_017 = {"status": "complete", "cobre_version": "0.17.0", "iterations": 5}


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


def _output(tmp_path, training, simulation=None):
    out = tmp_path / "output"
    (out / "training").mkdir(parents=True)
    if training is not None:
        text = training if isinstance(training, str) else json.dumps(training)
        (out / "training" / "metadata.json").write_text(text)
    if simulation is not None:
        (out / "simulation").mkdir()
        (out / "simulation" / "metadata.json").write_text(json.dumps(simulation))
    return out


def _tools(tmp_path, monkeypatch, out):
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    settings = dataclasses.replace(load_settings(), state_dir=str(tmp_path / "state"))
    monkeypatch.setattr(run_tools.jobs, "job_state",
                        lambda settings, job_id: {"job_id": job_id, "state": "succeeded",
                                                  "output": str(out)})
    monkeypatch.setattr(run_tools, "harvest_calibrations", lambda settings: 0)
    mcp = _CaptureMCP()
    run_tools.register_run(mcp, settings)
    register_results(mcp, settings)
    return (lambda: mcp.tools["run_status"]("j1"),
            lambda: mcp.tools["results_status"](str(out)))


@pytest.mark.parametrize("tool", [0, 1], ids=["run_status", "results_status"])
def test_rodada_parada_no_limite_repassa_o_motivo(tmp_path, monkeypatch, tool):
    out = _output(tmp_path, LIMITE_018, simulation={"status": "partial"})
    env = _tools(tmp_path, monkeypatch, out)[tool]()
    assert env["treino"] == {"status": "complete", "termination_reason": "iteration_limit",
                             "converged_at": None, "iterations": 5}
    assert env["simulacao"] == {"status": "partial"}


@pytest.mark.parametrize("tool", [0, 1], ids=["run_status", "results_status"])
def test_metadata_antigo_sem_os_campos_vira_null(tmp_path, monkeypatch, tool):
    out = _output(tmp_path, ANTIGO_017)
    env = _tools(tmp_path, monkeypatch, out)[tool]()
    assert env["status"] == "ok"
    assert env["treino"] == {"status": "complete", "termination_reason": None,
                             "converged_at": None, "iterations": 5}
    assert "simulacao" not in env


def test_sem_metadata_o_run_status_nao_ganha_campos(tmp_path, monkeypatch):
    out = _output(tmp_path, None)
    env = _tools(tmp_path, monkeypatch, out)[0]()
    assert env["status"] == "ok"
    assert "treino" not in env and "simulacao" not in env


def test_metadata_sendo_gravado_nao_derruba_o_run_status(tmp_path, monkeypatch):
    out = _output(tmp_path, '{"status": "comp')
    env = _tools(tmp_path, monkeypatch, out)[0]()
    assert env["status"] == "ok" and "treino" not in env
