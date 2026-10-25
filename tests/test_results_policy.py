"""`results_policy`: resumo da política (cortes por estágio), sem os coeficientes e com teto.

A biblioteca carrega a política inteira em memória; acima de um teto de tamanho em disco a
tool recusa sem chamá-la.
"""
import dataclasses
import sys
import types

import pytest

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.results import register_results


def _policy(n_stages=3, n_cuts=8, dim=4):
    cut = lambda i: {"cut_id": i, "slot_index": i, "iteration": i // 2 + 1,  # noqa: E731
                     "forward_pass_index": 0, "intercept": 10.0 * i,
                     "coefficients": [0.5] * dim, "is_active": i % 2 == 0}
    return {
        "metadata": {"format_version": 3, "software": "novomodelo", "software_version": "0.18.0",
                     "created_at": "2026-10-13T00:00:00Z", "num_stages": n_stages,
                     "graph_manifest": {"n_pools": n_stages, "nodes": [{"id": i} for i in range(n_stages)],
                                        "edges": []},
                     "season_manifest": {"cycle_code": 255, "n_seasons": 0, "hydro_orders": []},
                     "producer": {"completed_iterations": 4}},
        "stage_cuts": [{"stage_id": s, "state_dimension": dim, "capacity": 10,
                        "warm_start_count": 0, "populated_count": n_cuts,
                        "cuts": [cut(i) for i in range(n_cuts)]} for s in range(n_stages)],
        "stage_bases": [{"stage_id": s, "column_status": [1] * 50} for s in range(n_stages)],
    }


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


class OutputError(Exception):
    pass


@pytest.fixture
def tool(monkeypatch, tmp_path):
    estado = {"erro": None, "chamadas": []}

    def load_policy(output_dir, policy_subdir="policy"):
        estado["chamadas"].append((output_dir, policy_subdir))
        if estado["erro"]:
            raise estado["erro"]
        return _policy()

    pkg = types.ModuleType("novomodelo")
    pkg.results = types.SimpleNamespace(load_policy=load_policy)
    monkeypatch.setitem(sys.modules, "novomodelo", pkg)
    monkeypatch.setitem(sys.modules, "novomodelo.results", pkg.results)
    out = tmp_path / "ws" / "output"
    (out / "policy" / "cuts").mkdir(parents=True)
    (out / "policy" / "cuts" / "000.bin").write_bytes(b"x" * 100)
    settings = dataclasses.replace(load_settings(), workspace=str(tmp_path / "ws"),
                                   max_rows=5, max_policy_bytes=1000)
    mcp = _CaptureMCP()
    register_results(mcp, settings)
    return mcp.tools["results_policy"], str(out), estado


def test_resumo_sem_os_coeficientes_dos_cortes(tool):
    fn, out, _ = tool
    env = fn(out)
    assert env["status"] == "ok"
    assert env["metadata"]["software_version"] == "0.18.0"
    assert [e["n_cortes"] for e in env["estagios"]] == [8, 8, 8]
    assert env["estagios"][0]["n_ativos"] == 4
    assert "coefficients" not in str(env) and "stage_bases" not in env


def test_estagio_devolve_cortes_com_teto_e_sem_coeficientes(tool):
    fn, out, _ = tool
    env = fn(out, stage=1)
    cortes = env["cortes"]
    assert cortes["estagio"] == 1 and cortes["total"] == 8 and cortes["truncado"] is True
    assert len(cortes["linhas"]) == 5
    assert cortes["linhas"][0] == {"cut_id": 0, "iteration": 1, "forward_pass_index": 0,
                                   "intercept": 0.0, "is_active": True, "n_coeficientes": 4}


def test_politica_acima_do_teto_e_recusada_sem_chamar_a_biblioteca(tool):
    fn, out, estado = tool
    with open(out + "/policy/cuts/001.bin", "wb") as fh:
        fh.write(b"x" * 2000)
    env = fn(out)
    assert env["status"] == "error" and env["exit_code"] == 13
    assert "NOVOMODELO_MCP_MAX_POLICY_BYTES" in " ".join(env["diagnostics"])
    assert estado["chamadas"] == []


@pytest.mark.parametrize("subdir", ["../x", "a/b", "", ".."])
def test_policy_subdir_so_nome_simples(tool, subdir):
    fn, out, estado = tool
    env = fn(out, policy_subdir=subdir)
    assert env["status"] == "error" and estado["chamadas"] == []


def test_politica_de_outra_versao_vira_envelope(tool):
    fn, out, estado = tool
    estado["erro"] = OutputError("unsupported checkpoint manifest format_version 2; expected 3")
    env = fn(out)
    assert env["status"] == "error" and "format_version 2" in " ".join(env["diagnostics"])


def test_politica_ausente_e_erro_2(tool, tmp_path):
    fn, _, estado = tool
    vazio = tmp_path / "ws" / "sem-politica"
    vazio.mkdir()
    env = fn(str(vazio))
    assert env["status"] == "error" and env["exit_code"] == 2 and estado["chamadas"] == []


def test_estagio_inexistente_e_erro_22(tool):
    fn, out, _ = tool
    env = fn(out, stage=99)
    assert env["status"] == "error" and env["exit_code"] == 22
