"""Tools de resultados devolvem envelope de erro, nunca exceção, com arquivo ilegível."""

import dataclasses
import json

import pytest

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.results import register_results


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def tools(monkeypatch, tmp_path):
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    mcp = _CaptureMCP()
    register_results(mcp, dataclasses.replace(load_settings(), workspace=None))
    return mcp.tools


def _output(tmp_path, training="{}", simulation=None):
    out = tmp_path / "output"
    (out / "training").mkdir(parents=True)
    (out / "training" / "metadata.json").write_text(training, encoding="utf-8")
    if simulation is not None:
        (out / "simulation").mkdir()
        (out / "simulation" / "metadata.json").write_text(simulation, encoding="utf-8")
    return str(out)


def _is_error_envelope(env):
    return env["status"] == "error" and isinstance(env["exit_code"], int) and env["diagnostics"]


@pytest.mark.parametrize("training", ["{", "[1, 2]"], ids=["json-quebrado", "nao-e-objeto"])
def test_metadata_de_treino_ilegivel_vira_envelope(tools, tmp_path, training):
    env = tools["results_status"](_output(tmp_path, training=training))
    assert _is_error_envelope(env)
    assert "metadata.json" in " ".join(env["diagnostics"])


def test_metadata_de_simulacao_ilegivel_vira_aviso(tools, tmp_path):
    env = tools["results_status"](
        _output(tmp_path, training=json.dumps({"status": "complete"}), simulation="{")
    )
    assert env["status"] == "ok"
    assert env["simulation_ran"] is False and env["simulation_cost"] is None
    assert len(env["warnings"]) == 1 and "simulation/metadata.json" in env["warnings"][0]


def test_parquet_de_convergencia_ilegivel_vira_envelope(tools, tmp_path):
    out = _output(tmp_path)
    (tmp_path / "output" / "training" / "convergence.parquet").write_bytes(b"isto nao e parquet")
    assert _is_error_envelope(tools["results_convergence"](out))


def test_parquet_de_simulacao_ilegivel_vira_envelope(tools, tmp_path):
    out = _output(tmp_path)
    part = tmp_path / "output" / "simulation" / "hydros" / "scenario_id=0"
    part.mkdir(parents=True)
    (part / "data.parquet").write_bytes(b"isto nao e parquet")
    assert _is_error_envelope(tools["results_query"](out, "hydros"))


def test_coluna_inexistente_vira_envelope(tools, tmp_path):
    pl = pytest.importorskip("polars")
    out = _output(tmp_path)
    part = tmp_path / "output" / "simulation" / "hydros" / "scenario_id=0"
    part.mkdir(parents=True)
    pl.DataFrame({"stage_id": [0, 1], "x": [1.0, 2.0]}).write_parquet(part / "data.parquet")
    assert _is_error_envelope(tools["results_query"](out, "hydros", columns=["nao_existe"]))
