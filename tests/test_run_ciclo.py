"""init / plano / apply / run assíncrono, offline.

Usa o `novomodelo` falso (tests/fake_novomodelo.py, via lançador portável em _fakes.py) e
uma máquina MOCKADA (machine_id, hostname, cores, RAM) com metadata/config
sintéticos -> veredito determinístico em qualquer SO. Cada teste usa um state
dir temporário (NOVOMODELO_MCP_STATE_DIR) — nunca o do usuário.
"""

import contextlib
import json
import os
import socket
import tempfile
import time
from pathlib import Path

import pytest


from _fakes import fake_bin
from novomodelo_mcp.adapters import jobs, machine, run_plan, runtime, state
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.run import make_plan, register_run

FAKE = fake_bin("fake_novomodelo.py")
HOST = "host-sintetico"
MID = "0123456789abcdef"
GIB = 1024**3
MOCK_MACHINE = {
    "machine_id": MID,
    "hostname": HOST,
    "cpu_count": 8,
    "ram_bytes": 16 * GIB,
    "ram_gib": 16.0,
    "platform": "Test",
}

# Fixture sintética com ordens de grandeza de um run real de porte médio
# (8 CPUs/16 GiB, 4 threads): 72 estágios × 159 hidros, fwd=4, iters=6,
# 8 aberturas -> 15408 solves, ~243 s de treino. Valida o modelo de custo.
REF_META = {
    "hostname": HOST,
    "duration_seconds": 242.633,
    "completed_at": "2026-10-01T00:00:00Z",
    "configuration": {"max_iterations": 6, "forward_passes": 4},
    "problem_dimensions": {"num_stages": 72, "num_hydros": 159, "num_buses": 1},
    "solve_stats": {
        "total_lp_solves": 15408,
        "forward_solve_seconds": 158.5009550469995,
        "backward_solve_seconds": 553.9910048730003,
        "parallelism": 4,
    },
    "distribution": {"backend": "local", "world_size": 1, "threads_per_rank": 4},
}
SIM_META = {
    "duration_seconds": 148.623,
    "solve_stats": {"total_lp_solves": 7200, "solve_seconds": 582.49, "parallelism": 4},
}
# Mesmo caso a 7 threads numa CPU híbrida 4P+4E: MAIS LENTO que a 4 threads.
REF_META_7 = {
    **REF_META,
    "duration_seconds": 255.905,
    "completed_at": "2026-10-02T00:00:00Z",
    "solve_stats": {
        **REF_META["solve_stats"],
        "forward_solve_seconds": 180.0,
        "backward_solve_seconds": 573.8,
        "parallelism": 7,
    },
    "distribution": {"backend": "local", "world_size": 1, "threads_per_rank": 7},
}
SIM_META_7 = {
    "duration_seconds": 164.962,
    "solve_stats": {"total_lp_solves": 7200, "solve_seconds": 1114.9, "parallelism": 7},
}


class _StubMCP:
    """Captura as funções decoradas com @mcp.tool() (sem depender do pacote mcp)."""

    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):  # aceita annotations=… como o FastMCP
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@contextlib.contextmanager
def _env(**kv):
    saved = dict(os.environ)
    os.environ.update({k: str(v) for k, v in kv.items()})
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


@contextlib.contextmanager
def _sandbox(**kv):
    """Workspace + state dir temporários (nunca toca o estado real do usuário)."""
    with (
        tempfile.TemporaryDirectory() as d,
        _env(NOVOMODELO_MCP_WORKSPACE=d, NOVOMODELO_MCP_STATE_DIR=str(Path(d) / "state"), **kv),
    ):
        os.environ.pop("NOVOMODELO_MCP_ALLOW_FORCE", None)
        try:
            yield Path(d)
        finally:
            # no Windows, arquivo aberto por um runner vivo impede a limpeza da pasta
            for proc in list(jobs._PROCS.values()):
                proc.wait(timeout=30)
            jobs._PROCS.clear()


def _tools():
    mcp = _StubMCP()
    register_run(mcp, load_settings())
    return mcp.tools


def _make_case(
    root: Path,
    *,
    fwd=4,
    iters=6,
    n_stages=72,
    openings=8,
    hydros=159,
    sim=100,
    meta_host=HOST,
    modeling="penalty",
) -> Path:
    case = root / "caso"
    (case / "system").mkdir(parents=True)
    (case / "config.json").write_text(
        json.dumps(
            {
                "training": {
                    "selection": {"method": "sampled", "forward_passes": fwd},
                    "stopping_rules": [{"type": "iteration_limit", "limit": iters}],
                },
                "simulation": {
                    "enabled": True,
                    "selection": {"method": "sampled", "num_scenarios": sim},
                },
                "modeling": {"inflow_non_negativity": {"method": modeling}},
            }
        ),
        encoding="utf-8",
    )
    (case / "stages.json").write_text(
        json.dumps({"stages": [{"id": i, "num_openings": openings} for i in range(n_stages)]}),
        encoding="utf-8",
    )
    (case / "system" / "hydros.json").write_text(
        json.dumps({"hydros": [{"id": i} for i in range(hydros)]}), encoding="utf-8"
    )
    (case / "system" / "buses.json").write_text(
        json.dumps({"buses": [{"id": 0}]}), encoding="utf-8"
    )
    if meta_host:
        tr = case / "output" / "training"
        tr.mkdir(parents=True)
        (tr / "metadata.json").write_text(
            json.dumps({**REF_META, "hostname": meta_host}), encoding="utf-8"
        )
        (case / "output" / "simulation").mkdir()
        (case / "output" / "simulation" / "metadata.json").write_text(
            json.dumps(SIM_META), encoding="utf-8"
        )
    return case


def _wait(tools, job_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = tools["run_status"](job_id)
        if st["state"] != "running":
            return st
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} não terminou em {timeout}s")


# ── máquina ───────────────────────────────────────────────────────────────────


def test_machine_meminfo_and_mock():
    assert machine.parse_meminfo("MemTotal:       16384000 kB\nMemFree: 1 kB") == 16384000 * 1024
    assert machine.parse_meminfo("nada") is None
    m = machine.detect_machine(hostname="h", cpu_count=8, ram_bytes=16 * GIB)
    assert (m["hostname"], m["cpu_count"], m["ram_gib"]) == ("h", 8, 16.0), m
    real = machine.detect_machine()
    assert real["hostname"] and real["cpu_count"] >= 1, real
    assert real["ram_bytes"], "RAM não detectada neste SO"
    assert len(real["machine_id"]) == 16 and real["machine_id"] == machine.detect_machine_id()


def test_machine_cgroup_parsers_and_hostname():
    assert machine.parse_cpu_max("200000 100000") == 2.0
    assert machine.parse_cpu_max("max 100000") is None
    assert machine.parse_mem_limit("max") is None
    assert machine.parse_mem_limit("8589934592\n") == 8 * GIB
    assert machine.parse_mem_limit(str(2**63 - 4096)) is None  # cgroup v1 "ilimitado"
    assert machine.normalize_hostname(" Host-A.local ") == "host-a"


def test_state_dir_is_persistent_not_tmp():
    d = state.default_state_dir()
    assert d.name == "novomodelo-mcp", d
    assert not str(d).startswith(tempfile.gettempdir()), d


# ── custo ─────────────────────────────────────────────────────────────────────


def test_machine_hybrid_parsers():
    assert machine.parse_cpu_list("0-7,16-23") == 16 and machine.parse_cpu_list("3") == 1
    assert machine.performance_from_classes([(1, 2)] * 4 + [(0, 1)] * 4) == 8
    assert machine.performance_from_classes([(0, 2)] * 8) is None  # não híbrida

    def core(eff, mask):  # registro RelationProcessorCore (64 bits), 48 bytes
        rec = bytearray(48)
        rec[0:4] = (0).to_bytes(4, "little")
        rec[4:8] = (48).to_bytes(4, "little")
        rec[9] = eff
        rec[30:32] = (1).to_bytes(2, "little")
        rec[32:40] = mask.to_bytes(8, "little")
        return bytes(rec)

    buf = core(1, 0b11) + core(1, 0b1100) + core(0, 0b10000) + core(0, 0b100000)
    cores = machine.parse_win_cores(buf)
    assert cores == [(1, 2), (1, 2), (0, 1), (0, 1)], cores
    assert machine.performance_from_classes(cores) == 4
    m = machine.detect_machine(hostname="h", cpu_count=8, ram_bytes=GIB, performance_cpus=4)
    assert m["hybrid"] is True and m["performance_cpus"] == 4


# ── tempo de execução ─────────────────────────────────────────────────────────


def test_runtime_model_matches_reference_point():
    p4 = runtime.point_from_run(REF_META, SIM_META, source="ref4")
    assert abs(p4["train"]["s_per_solve"] - 0.046) < 0.001, p4
    solves = runtime.training_solves(6, 4, [8] * 72)
    assert abs(solves - 15408) / 15408 < 0.01, solves  # modelo ≈ contagem real (~1%)
    est = runtime.estimate([p4], 4, solves, 7200)
    assert abs(est["training_seconds"] - 243) / 243 < 0.02, est
    assert abs(est["simulation_seconds"] - 149) / 149 < 0.01, est
    # acima do medido: SEM ganho; abaixo: reescala linear
    assert runtime.estimate([p4], 8, solves, 7200)["total_seconds"] == est["total_seconds"]
    half = runtime.estimate([p4], 2, solves, 7200)
    assert abs(half["training_seconds"] - 2 * est["training_seconds"]) < 0.2, half
    # com o ponto a 7 threads: 7 previsto pelo próprio ponto (real 256 s), 5 interpolado
    p7 = runtime.point_from_run(REF_META_7, SIM_META_7, source="ref7")
    e7 = runtime.estimate([p4, p7], 7, solves, 7200)
    assert abs(e7["training_seconds"] - 256) / 256 < 0.02, e7
    e5 = runtime.estimate([p4, p7], 5, solves, 7200)
    assert est["training_seconds"] < e5["training_seconds"] < e7["training_seconds"], e5
    assert "interpolado" in e5["training_method"]


def test_threads_choice_hybrid_and_measured():
    p4 = {**runtime.point_from_run(REF_META, SIM_META, source="a"), "threads": 4}
    p7 = runtime.point_from_run(REF_META_7, SIM_META_7, source="b")
    ref = {"level": 3, "points": [p4, p7]}
    hybrid = {**MOCK_MACHINE, "performance_cpus": 4}
    assert run_plan.choose_threads(hybrid, None, None)[0] == 4
    assert run_plan.choose_threads(MOCK_MACHINE, None, None)[0] == 7  # cores − 1
    t, basis = run_plan.choose_threads(MOCK_MACHINE, ref, None)
    assert t == 4 and "medido" in basis, (t, basis)  # dado medido vence
    assert run_plan.choose_threads(MOCK_MACHINE, ref, 6)[0] == 6  # informado vence


def test_find_reference_same_host_only():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name, host, total in (
            ("a", HOST, 15408),
            ("b", "outra-maquina", 99999),
            ("c", HOST, 0),
        ):
            tr = root / name / "output" / "training"
            tr.mkdir(parents=True)
            meta = {
                **REF_META,
                "hostname": host,
                "solve_stats": {**REF_META["solve_stats"], "total_lp_solves": total},
            }
            (tr / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        runs = runtime.find_reference_runs([d], HOST.upper() + ".local")  # normalizado
        assert len(runs) == 1 and f"{os.sep}a{os.sep}" in runs[0]["source"], runs
        assert runs[0]["sim"] is None
        assert runtime.find_reference_runs([d], "ninguem") == []


def test_reference_prefers_same_modeling_and_reports_range():
    with _sandbox() as d:
        (d / "pen").mkdir()
        (d / "trn").mkdir()
        (d / "alvo").mkdir()
        _make_case(d / "pen", modeling="penalty")
        trn = _make_case(d / "trn", modeling="truncation")
        # truncation: LP mais barato e run MAIS RECENTE (antes vencia o desempate)
        meta = {**REF_META, "duration_seconds": 186.6, "completed_at": "2026-12-31T00:00:00Z"}
        (trn / "output" / "training" / "metadata.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )
        case = _make_case(d / "alvo", modeling="penalty", meta_host=None)
        plan = make_plan(
            str(case), load_settings(), machine={**MOCK_MACHINE, "performance_cpus": 4}
        )
        assert plan["reference"]["level"] == "mesma_modelagem", plan["reference"]
        src = plan["reference"]["points"][0]["source"]
        assert f"{os.sep}pen{os.sep}" in src, src
        rng = plan["time"]["range"]
        assert rng["n_groups"] == 2 and rng["min_seconds"] < rng["max_seconds"], rng
        assert f"{os.sep}trn{os.sep}" in rng["min_source"], rng


# ── plano ─────────────────────────────────────────────────────────────────────


def test_plan_fits_with_reference():
    with _sandbox() as d:
        case = _make_case(d)
        plan = make_plan(str(case), load_settings(), time_budget_s=900, machine=MOCK_MACHINE)
        assert plan["status"] == "ok", plan
        assert plan["verdict"] == "cabe", plan
        assert plan["target_threads"] == 7 and plan["threads_basis"] == "cores − 1", plan
        src = plan["reference"]["points"][0]["source"]
        assert src.endswith(os.path.join("training", "metadata.json")), plan
        assert any("SEM ganho" in w or "NÃO aceleram" in w for w in plan["warnings"])
        assert plan["machine"]["hostname"] == HOST
        assert any("NÃO CONVERGIR" in w for w in plan["warnings"]), plan["warnings"]
        assert plan["apply_overrides"] == {}, plan
        assert plan["params_current"]["forward_passes"] == 4
        assert plan["dimensions"]["num_hydros"] == 159


def test_plan_suggests_reductions_deterministically():
    with _sandbox() as d:
        case = _make_case(d, fwd=20, iters=50)
        p1 = make_plan(str(case), load_settings(), time_budget_s=300, machine=MOCK_MACHINE)
        p2 = make_plan(str(case), load_settings(), time_budget_s=300, machine=MOCK_MACHINE)
        assert p1["verdict"] == "cabe_com_ajustes", p1
        assert p1["time"]["suggested"]["total_seconds"] <= 300, p1["time"]
        assert p1["apply_overrides"] == p2["apply_overrides"], "não determinístico"
        ov = p1["apply_overrides"]
        assert ov.get("forward_passes", 20) < 20 or ov.get("iteration_limit", 50) < 50, ov
        assert set(ov) <= set(run_plan.CONFIG_KNOBS), ov


def test_plan_reduces_simulation_when_it_alone_breaks_budget():
    with _sandbox() as d:
        case = _make_case(d)  # simulação sozinha ~149 s a 4 threads
        m = {**MOCK_MACHINE, "performance_cpus": 4}
        plan = make_plan(str(case), load_settings(), time_budget_s=120, machine=m)
        assert plan["verdict"] == "cabe_com_ajustes", plan
        assert plan["time"]["suggested"]["total_seconds"] <= 120, plan["time"]["suggested"]
        ov = plan["apply_overrides"]
        assert 0 < ov["simulation_scenarios"] < 100, ov
        assert plan["time"]["suggested"]["simulation_seconds"] <= 60, plan["time"]
        alt = plan["alternatives"][0]
        assert alt["apply_overrides"] == {"simulation_enabled": False}, alt
        assert any("NÃO comparáveis" in w for w in plan["warnings"]), plan["warnings"]
        tiny = make_plan(str(case), load_settings(), time_budget_s=20, machine=m)
        assert tiny["apply_overrides"].get("simulation_enabled") is False, tiny


def test_plan_nao_cabe_and_indeterminado():
    with _sandbox() as d:
        case = _make_case(d)
        plan = make_plan(str(case), load_settings(), time_budget_s=1, machine=MOCK_MACHINE)
        assert plan["verdict"] == "nao_cabe", plan
    with _sandbox() as d:
        case = _make_case(d, meta_host="outra-maquina")
        plan = make_plan(str(case), load_settings(), machine=MOCK_MACHINE)
        assert plan["verdict"] == "indeterminado", plan
        assert plan["reference"] is None
        assert any("calibração" in w for w in plan["warnings"]), plan["warnings"]


def test_plan_memory_gate():
    with _sandbox() as d:
        case = _make_case(d, fwd=200, iters=50)
        tiny = {**MOCK_MACHINE, "ram_bytes": 64 * 1024**2}  # 64 MiB
        plan = make_plan(str(case), load_settings(), time_budget_s=10**9, machine=tiny)
        assert plan["memory"]["level"] == "nao_cabe", plan["memory"]
        assert plan["verdict"] == "nao_cabe", plan


# ── tools: init / apply ───────────────────────────────────────────────────────


def test_init_list_and_guard():
    with _sandbox(NOVOMODELO_MCP_SOLVER_BIN=FAKE) as d:
        t = _tools()
        env = t["case_init"](list=True)
        assert env["status"] == "ok" and env["exit_code"] == 0, env
        assert env["templates"][0]["name"] == "1dtoy", env
        out = t["case_init"](directory=str(d.parent / "fora-do-ws"), template="1dtoy")
        assert out["status"] == "error" and out["exit_code"] == 13, out
        target = str(d / "novo")
        ok = t["case_init"](directory=target, template="1dtoy")
        assert ok["status"] == "ok" and ok["artifacts"]["case_dir"] == target, ok
        again = t["case_init"](directory=target, template="1dtoy")
        assert again["status"] == "error", again
        forced = t["case_init"](directory=target, template="1dtoy", force=True)
        assert forced["exit_code"] == 13, "force deveria exigir NOVOMODELO_MCP_ALLOW_FORCE"
        assert t["case_init"]()["exit_code"] == 22
        # nome de template vindo do agente não pode virar opção da CLI
        for bad in ("--force", "-x", "../x", "a b"):
            r = t["case_init"](directory=target, template=bad)
            assert r["exit_code"] == 22, (bad, r)


def test_cli_paths_are_absolute_even_for_dash_prefixed_input():
    from novomodelo_mcp.tools.run import _cli_path

    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            out = _cli_path("-output")
            assert Path(out).is_absolute() and not out.startswith("-"), out
        finally:
            os.chdir(cwd)


def test_run_apply_config_only():
    with _sandbox() as d:
        case = _make_case(d, meta_host=None)
        t = _tools()
        r = t["run_apply"](str(case), {"forward_passes": 2, "iteration_limit": 3})
        assert r["status"] == "ok" and r["written"] is True, r
        cfg = json.loads((case / "config.json").read_text(encoding="utf-8"))
        assert cfg["training"]["selection"]["forward_passes"] == 2
        assert cfg["training"]["stopping_rules"][0]["limit"] == 3
        assert (case / "config.json.bak").exists()
        bad = t["run_apply"](str(case), {"num_openings": 2})
        assert bad["status"] == "error" and bad["exit_code"] == 22, bad
        neg = t["run_apply"](str(case), {"forward_passes": -5})
        import importlib.util

        if importlib.util.find_spec("jsonschema"):
            assert neg["status"] == "error", neg
        else:
            assert "validação por schema pulada" in (neg.get("note") or ""), neg
        dry = t["run_apply"](str(case), {"simulation_scenarios": 5}, dry_run=True)
        assert dry["written"] is False, dry
        assert (
            json.loads((case / "config.json").read_text(encoding="utf-8"))["simulation"][
                "selection"
            ]["num_scenarios"]
            == 100
        )


# ── tools: run assíncrono ─────────────────────────────────────────────────────


def test_run_async_lifecycle():
    with _sandbox(NOVOMODELO_MCP_SOLVER_BIN=FAKE, FAKE_NOVOMODELO_SLEEP="0.3") as d:
        case = _make_case(d, meta_host=None)
        t = _tools()
        t0 = time.time()
        r = t["run_start"](str(case), threads=2)
        assert r["status"] == "ok" and r["job_id"], r
        assert time.time() - t0 < 5, "start deveria voltar na hora"
        assert r["cmd"][-6:] == [
            "--output",
            str((case / "output").resolve()),
            "--threads",
            "2",
            "--comm-backend",
            "local",
        ], r["cmd"]
        busy = t["run_start"](str(case), threads=2)
        assert busy["status"] == "error" and busy["exit_code"] == 16, busy
        st = _wait(t, r["job_id"])
        assert st["state"] == "succeeded" and st["exit_code"] == 0, st
        assert st["milestones"]["training"] is True, st
        logs = t["run_logs"](r["job_id"])
        assert "fake run: done" in logs["saida"], logs
        assert t["run_status"]("../../etc")["status"] == "error"


def test_run_logs_mostra_os_dois_canais_em_ordem_sem_duplicar():
    for canal in ("stderr", "stdout"):  # relatório da 0.18.0 e da 0.18.1
        with _sandbox(NOVOMODELO_MCP_SOLVER_BIN=FAKE, FAKE_NOVOMODELO_RELATORIO=canal) as d:
            case = _make_case(d, meta_host=None)
            t = _tools()
            r = t["run_start"](str(case), threads=1)
            assert _wait(t, r["job_id"])["state"] == "succeeded"
            logs = t["run_logs"](r["job_id"])
            assert "stdout" not in logs and "stderr" not in logs, logs
            linhas = [x for x in logs["saida"].splitlines() if "relatorio" in x or "aviso" in x]
            marca = "[stderr] " if canal == "stderr" else ""
            assert linhas == [
                f"{marca}relatorio: banner",
                "[stderr] aviso: limite baixo",
                f"{marca}relatorio: iteracao 1",
                f"{marca}relatorio: iteracao 2",
                f"{marca}relatorio: resumo",
            ], (canal, logs)


def test_run_async_failure_and_cancel():
    with _sandbox(NOVOMODELO_MCP_SOLVER_BIN=FAKE, FAKE_NOVOMODELO_RC="3") as d:
        case = _make_case(d, meta_host=None)
        t = _tools()
        st = _wait(t, t["run_start"](str(case))["job_id"])
        assert st["state"] == "failed" and st["exit_code"] == 3, st
        assert "solver falhou" in st["stderr_tail"], st
    with _sandbox(NOVOMODELO_MCP_SOLVER_BIN=FAKE, FAKE_NOVOMODELO_SLEEP="30") as d:
        case = _make_case(d, meta_host=None)
        t = _tools()
        job = t["run_start"](str(case))["job_id"]
        time.sleep(0.3)
        c = t["run_cancel"](job)
        assert c["state"] == "cancelled", c
        assert t["run_status"](job)["state"] == "cancelled"


def test_run_start_refuses_nao_cabe():
    with _sandbox(NOVOMODELO_MCP_SOLVER_BIN=FAKE) as d:
        case = _make_case(d, meta_host=socket.gethostname().upper())  # casa normalizado
        t = _tools()
        r = t["run_start"](str(case), time_budget_s=0.01)
        assert r["status"] == "error" and r["plan"]["verdict"] == "nao_cabe", r
        ok = t["run_start"](str(case), time_budget_s=0.01, override=True)
        assert ok["status"] == "ok", ok
        _wait(t, ok["job_id"])
        outside = t["run_start"](str(case), output=str(Path(d).parent / "fora-do-ws"))
        assert outside["exit_code"] == 13, outside


def test_run_start_nao_sobrescreve_rodada_concluida():
    with _sandbox(NOVOMODELO_MCP_SOLVER_BIN=FAKE) as d:
        case = _make_case(d, meta_host=None)
        t = _tools()
        assert _wait(t, t["run_start"](str(case), override=True)["job_id"])["state"] == "succeeded"
        de_novo = t["run_start"](str(case), override=True)
        assert de_novo["status"] == "error" and de_novo["exit_code"] == 17, de_novo
        assert any("overwrite=True" in x for x in de_novo["diagnostics"]), de_novo
        assert de_novo["output_sugerido"] != str((case / "output").resolve()), de_novo
        outro = t["run_start"](str(case), output=de_novo["output_sugerido"], override=True)
        assert outro["status"] == "ok", outro
        _wait(t, outro["job_id"])
        assert t["run_start"](str(case), override=True, overwrite=True)["status"] == "ok"


def test_calibration_registry_by_machine_id():
    """Run via run_start alimenta o registro; o plano o usa mesmo se o hostname mudar."""
    with _sandbox(NOVOMODELO_MCP_SOLVER_BIN=FAKE, FAKE_NOVOMODELO_META=json.dumps(REF_META)) as d:
        case = _make_case(d, meta_host=None)
        t = _tools()
        st = _wait(t, t["run_start"](str(case), override=True)["job_id"])
        assert st["state"] == "succeeded", st
        reg = json.loads((d / "state" / "calibration.json").read_text(encoding="utf-8"))
        mid = machine.detect_machine_id()
        assert reg["version"] == 2 and len(reg["entries"]) == 1, reg
        assert reg["entries"][0]["machine_id"] == mid, reg
        assert reg["entries"][0]["config_sig"], reg  # assinatura gravada no start
        # hostname "novo" (rede/VPN mudou), mesmo machine_id -> referência encontrada
        other = d / "outro"
        other.mkdir()
        case2 = _make_case(other, meta_host=None)
        m = {**MOCK_MACHINE, "machine_id": mid, "hostname": "hostname-mudou"}
        plan = make_plan(str(case2), load_settings(), machine=m)
        assert plan["reference"]["points"][0]["origin"] == "run_start", plan
        # outra máquina NÃO herda a calibração
        plan = make_plan(
            str(case2), load_settings(), machine={**m, "machine_id": "ffffffffffffffff"}
        )
        assert plan["verdict"] == "indeterminado", plan


def test_terminal_state_only_after_runner_exits():
    with _sandbox(NOVOMODELO_MCP_SOLVER_BIN=FAKE) as d:
        case = _make_case(d, meta_host=None)
        t = _tools()
        job = t["run_start"](str(case), override=True)["job_id"]
        st = _wait(t, job)
        assert st["state"] == "succeeded", st
        assert job not in jobs._PROCS, "estado terminal com o runner ainda vivo"


def test_job_lost_when_runner_dies():
    with _sandbox():
        settings = load_settings()
        d = jobs.jobs_root(settings) / "20200101-000000-abcdef"
        d.mkdir()
        (d / "job.json").write_text(
            json.dumps(
                {"job_id": d.name, "cmd": ["x"], "pid": 1, "started_at": time.time() - 3600}
            ),
            encoding="utf-8",
        )
        (d / "heartbeat").touch()
        old = time.time() - 3600
        os.utime(d / "heartbeat", (old, old))
        assert jobs.job_state(settings, d.name)["state"] == "lost"
        assert jobs.prune_jobs(settings, keep_days=0) == [d.name]


@pytest.mark.executaveis_reais
def test_real_solver():
    """Execução real: novomodelo init 1dtoy + 1 iteração."""
    with _sandbox() as d:
        t = _tools()
        case = str(d / "toy")
        assert t["case_init"](directory=case, template="1dtoy")["status"] == "ok"
        assert (
            t["run_apply"](case, {"iteration_limit": 1, "simulation_scenarios": 1})["status"]
            == "ok"
        )
        r = t["run_start"](case, threads=1, override=True)
        st = _wait(t, r["job_id"], timeout=300)
        assert st["state"] == "succeeded", (st, t["run_logs"](r["job_id"]))
