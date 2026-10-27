"""Ponta a ponta contra os programas reais (novomodelo, novomodelo-bridge).

Sobe o servidor como um cliente MCP faria (stdio), confere as anotações que ele anuncia
pelo protocolo e chama todas as tools num rascunho dentro de um workspace temporário.
Roda com `--executaveis-reais`; o que acessa a rede, também com `--com-rede`. As tools do
bridge usam os decks mínimos públicos do `novomodelo-bridge` (`--bridge-repo`) ou casos
próprios (`--newave-src`, `--decomp-src`); sem eles, ficam puladas.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from _cliente_mcp import ClienteMCP
from mcp import StdioServerParameters

pytestmark = pytest.mark.executaveis_reais

ROOT = Path(__file__).resolve().parents[1]

# Classificação esperada, escrita aqui de propósito (independente do código do
# servidor): se o servidor mudar, o teste acusa a diferença.
READ_ONLY = {
    "server_info",
    "solver_version",
    "schema_list",
    "schema_get",
    "docs_list",
    "docs_read",
    "docs_search",
    "deck_list",
    "deck_read_json",
    "deck_read_parquet",
    "deck_describe_parquet",
    "deck_sql",
    "case_validate",
    "case_summary",
    "bridge_check_newave",
    "bridge_check_decomp",
    "results_status",
    "results_convergence",
    "results_list_entities",
    "results_query",
    "results_stochastic",
    "results_policy",
    "run_plan",
    "run_status",
    "run_logs",
}
WRITES = {
    "case_init",
    "schema_export",
    "bridge_convert_newave",
    "bridge_convert_decomp",
    "bridge_compare_newave",
    "bridge_compare_decomp",
    "bridge_dashboard",
    "incluir_pastas",
}
DESTRUCTIVE = {
    "deck_edit_json",
    "deck_edit_parquet",
    "run_apply",
    "run_start",
    "run_cancel",
    "instalar_novomodelo",
}
ALL = READ_ONLY | WRITES | DESTRUCTIVE
NETWORK = {"server_info", "instalar_novomodelo"}
NEWAVE = {"bridge_check_newave", "bridge_convert_newave", "bridge_compare_newave"}
DECOMP = {"bridge_check_decomp", "bridge_convert_decomp", "bridge_compare_decomp"}

#: Decks mínimos públicos do novomodelo-bridge (Apache-2.0), dentro do clone.
_MINI = {"newave": Path("tests/decks/newave_mini"), "decomp": Path("tests/decks/decomp_mini")}


def _ok(env: dict) -> None:
    assert env.get("status") == "ok", str(env.get("diagnostics", env))[:300]


def _recusa(env: dict) -> None:
    assert env.get("status") == "error", f"exit_code={env.get('exit_code')}"


def _tem_status(env: dict) -> None:
    assert "status" in env, env


def _esperar(cliente: ClienteMCP, job_id: str, *, segundos: int = 120) -> dict:
    estado: dict = {}
    for _ in range(segundos):
        estado = cliente.chamar("run_status", {"job_id": job_id})
        if estado.get("state") not in ("running", "starting", None):
            break
        time.sleep(1)
    return estado


# ---------- servidor, workspace e caso ----------


def _parametros(config: pytest.Config, ws: Path) -> StdioServerParameters:
    env = dict(os.environ)
    env["NOVOMODELO_MCP_WORKSPACE"] = str(ws)
    instalado = config.getoption("--mcp-instalado")
    if instalado is None:
        env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
        return StdioServerParameters(command=sys.executable, args=["-m", "novomodelo_mcp"], env=env)
    exe = instalado or shutil.which("novomodelo-mcp")
    if not exe:
        pytest.fail("--mcp-instalado: novomodelo-mcp não está no PATH; passe o caminho")
    env.pop("PYTHONPATH", None)
    return StdioServerParameters(command=exe, args=[], env=env)


@pytest.fixture(scope="module")
def ws(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("estudos").resolve()


@pytest.fixture(scope="module")
def rascunho(ws) -> Path:
    pasta = ws / "_e2e"
    pasta.mkdir()
    return pasta


@pytest.fixture(scope="module")
def cliente(request, ws):
    c = ClienteMCP(_parametros(request.config, ws))
    c.instalacao = None
    if request.config.getoption("--instalar-executavel"):
        c.instalacao = c.chamar("instalar_novomodelo", {"confirmar": True})
    yield c
    c.fechar()


@pytest.fixture(scope="module")
def info(cliente) -> dict:
    return cliente.chamar("server_info")


@pytest.fixture(scope="module")
def toy(cliente, rascunho) -> Path:
    caso = rascunho / "1dtoy"
    env = cliente.chamar("case_init", {"directory": str(caso), "template": "1dtoy"})
    _ok(env)
    return caso


@pytest.fixture(scope="module")
def parquet(toy) -> str:
    return str(toy / "scenarios" / "inflow_seasonal_stats.parquet")


@pytest.fixture(scope="module")
def rodada(cliente, toy) -> dict:
    """run_apply, run_plan e um run curto, até o fim; os envelopes de cada passo."""
    passos = {
        "apply": cliente.chamar(
            "run_apply",
            {
                "case_dir": str(toy),
                "overrides": {"iteration_limit": 5, "simulation_scenarios": 10},
            },
        ),
        "plan": cliente.chamar("run_plan", {"case_dir": str(toy), "time_budget_s": 120}),
        "start": cliente.chamar("run_start", {"case_dir": str(toy), "time_budget_s": 120}),
    }
    job = passos["start"].get("job_id")
    passos["status"] = _esperar(cliente, job) if job else {}
    passos["logs"] = cliente.chamar("run_logs", {"job_id": job, "lines": 5}) if job else {}
    passos["output"] = str(toy / "output")
    return passos


@pytest.fixture(scope="module")
def caso_bridge(request, rascunho):
    """Casos NEWAVE/DECOMP copiados para o rascunho: os próprios ou os decks mínimos."""
    repo = request.config.getoption("--bridge-repo")
    casos = {}
    for nome in ("newave", "decomp"):
        proprio = request.config.getoption(f"--{nome}-src")
        origem = Path(proprio) if proprio else (Path(repo) / _MINI[nome] if repo else None)
        if origem is None or not origem.expanduser().is_dir():
            casos[nome] = None
            continue
        destino = rascunho / "entradas" / f"{nome}-src"
        shutil.copytree(origem.expanduser(), destino)
        casos[nome] = destino
    return casos


def _caso(caso_bridge, nome: str) -> Path:
    if caso_bridge[nome] is None:
        pytest.skip(f"sem caso {nome.upper()} (use --bridge-repo ou --{nome}-src)")
    return caso_bridge[nome]


# ---------- protocolo e anotações ----------


def test_versao_anunciada_e_a_do_pacote_instalado(request, cliente):
    instalado = request.config.getoption("--mcp-instalado")
    if instalado is None:
        pytest.skip("só com --mcp-instalado")
    real = Path(cliente.params.command).resolve().parent
    python = next((p for p in (real / "python", real / "python.exe") if p.exists()), None)
    assert python, f"sem Python ao lado de {cliente.params.command}"
    proc = subprocess.run(
        [str(python), "-c", "import importlib.metadata as m; print(m.version('novomodelo-mcp'))"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.stdout.strip() == cliente.versao_anunciada


def test_todas_as_tools_anunciadas(cliente):
    nomes = set(cliente.ferramentas())
    assert nomes == ALL, f"faltam={sorted(ALL - nomes)} sobram={sorted(nomes - ALL)}"


@pytest.mark.parametrize("nome", sorted(ALL))
def test_anotacao(cliente, nome):
    a = cliente.ferramentas()[nome].annotations
    assert a is not None, "sem anotação"
    leitura = nome in READ_ONLY
    assert a.readOnlyHint is leitura
    assert a.openWorldHint is (nome in NETWORK)
    assert leitura or a.destructiveHint is (nome in DESTRUCTIVE)


# ---------- diagnóstico e referência ----------


@pytest.mark.rede
def test_instalar_novomodelo_instala(request, cliente):
    if not request.config.getoption("--instalar-executavel"):
        pytest.skip("só com --instalar-executavel")
    e = cliente.instalacao
    assert e.get("executado") is True and e.get("versao_instalada"), e.get("diagnostics", e)


def test_server_info_binarios_e_versoes(info):
    assert info.get("novomodelo", {}).get("available"), info.get("novomodelo")
    assert info.get("bridge", {}).get("available"), info.get("bridge")


@pytest.mark.rede
def test_instalar_novomodelo_so_o_plano(cliente):
    e = cliente.chamar("instalar_novomodelo")
    assert e.get("executado") is False, e
    assert (e.get("plano") or {}).get("sha256"), e.get("aviso_rede") or e


def test_solver_version(cliente):
    e = cliente.chamar("solver_version")
    assert e.get("status") == "ok" and e.get("version"), e


def test_schema_list(cliente):
    assert len(cliente.chamar("schema_list").get("types", [])) >= 18


def test_schema_get_penalties(cliente):
    _ok(cliente.chamar("schema_get", {"tipo": "penalties"}))


def test_schema_get_recusa_traversal(cliente):
    _recusa(cliente.chamar("schema_get", {"tipo": "../config"}))


def test_docs_list_reference(cliente):
    assert cliente.chamar("docs_list", {"section": "reference"}).get("count", 0) > 0


def test_docs_read_cli_reference(cliente):
    _ok(cliente.chamar("docs_read", {"page": "reference/cli-reference"}))


def test_docs_read_changelog_pela_versao(cliente, info):
    esperada = (info.get("versoes") or {}).get("esperada")
    e = cliente.chamar("docs_read", {"page": "changelog/novomodelo", "secao": esperada or ""})
    assert str(e.get("content", "")).startswith(f"## {esperada}"), e.get("diagnostics")


@pytest.mark.parametrize(
    ("consulta", "alvo"),
    [
        ("negative inflow", "running/configuration#modelinginflow_non_negativity"),
        ("CVaR", "math/risk-measures"),
        ("inflow non-negativity", "math/inflow-nonnegativity"),
    ],
)
def test_docs_search_no_top_5(cliente, consulta, alvo):
    achados = [
        f"{r['pagina']}#{r['secao']}"
        for r in cliente.chamar("docs_search", {"consulta": consulta}).get("resultados") or []
    ]
    assert any(a.startswith(alvo) for a in achados), achados[:3]


def test_docs_search_termo_em_portugues(cliente):
    e = cliente.chamar("docs_search", {"consulta": "afluência"})
    assert "Inflow" in (e.get("termos_do_glossario") or []), e.get("termos_do_glossario")


def test_docs_read_recusa_traversal(cliente):
    _recusa(cliente.chamar("docs_read", {"page": "../../../../etc/hosts"}))


# ---------- caso de exemplo (1dtoy) ----------


def test_case_init_lista_templates(cliente):
    templates = cliente.chamar("case_init", {"list": True}).get("templates", [])
    assert any(t.get("name") == "1dtoy" for t in templates)


def test_case_init_cria_1dtoy(toy):
    assert (toy / "config.json").is_file()


def test_deck_list(cliente, toy):
    assert cliente.chamar("deck_list", {"case_dir": str(toy)}).get("count", 0) >= 10


def test_deck_read_json(cliente, toy):
    _ok(cliente.chamar("deck_read_json", {"path": str(toy / "config.json")}))


def test_deck_read_json_recusa_fora_do_workspace(cliente):
    _recusa(cliente.chamar("deck_read_json", {"path": "/etc/hosts"}))


def test_incluir_pastas_recusa_a_raiz_do_disco(cliente, ws):
    _recusa(cliente.chamar("incluir_pastas", {"pastas": [ws.anchor]}))


def test_incluir_pastas_ja_incluida_nao_grava(cliente, rascunho):
    e = cliente.chamar("incluir_pastas", {"pastas": [str(rascunho)]})
    assert e.get("status") == "ok" and not e.get("incluidas") and e.get("ja_incluidas"), e


def test_deck_read_parquet(cliente, parquet):
    _ok(cliente.chamar("deck_read_parquet", {"path": parquet, "limit": 2}))


def test_deck_describe_parquet(cliente, parquet):
    _ok(cliente.chamar("deck_describe_parquet", {"path": parquet}))


def test_deck_sql_agregacao(cliente, parquet):
    _ok(
        cliente.chamar(
            "deck_sql", {"query": f"SELECT count(*) AS n FROM read_parquet('{parquet}')"}
        )
    )


def test_deck_sql_recusa_copy(cliente):
    _recusa(cliente.chamar("deck_sql", {"query": "COPY (SELECT 1) TO 'x.csv'"}))


def test_case_validate_1dtoy(cliente, toy):
    e = cliente.chamar("case_validate", {"case_dir": str(toy)})
    assert e.get("valid") is True, f"erros={e.get('n_errors')} avisos={e.get('n_warnings')}"


def test_case_summary_1dtoy(cliente, toy):
    contagens = cliente.chamar("case_summary", {"case_dir": str(toy)}).get("contagens") or {}
    assert {k: contagens.get(k) for k in ("barras", "hidros", "termicas", "estagios")} == {
        "barras": 1,
        "hidros": 1,
        "termicas": 2,
        "estagios": 4,
    }, contagens


def test_schema_export(cliente, rascunho):
    _ok(cliente.chamar("schema_export", {"output_dir": str(rascunho / "schemas")}))


def test_deck_edit_json_dry_run(cliente, toy):
    mudanca = [{"path": "training.selection.forward_passes", "value": 2}]
    _ok(
        cliente.chamar(
            "deck_edit_json",
            {"path": str(toy / "config.json"), "changes": mudanca, "dry_run": True},
        )
    )


def test_deck_edit_json_fora_do_schema_nao_grava(cliente, toy):
    mudanca = [{"path": "training.selection.forward_passes", "value": "abc"}]
    e = cliente.chamar("deck_edit_json", {"path": str(toy / "config.json"), "changes": mudanca})
    assert e.get("status") == "error" and e.get("written") is False, e


def test_deck_edit_json_ensure_valid_reverte(cliente, toy):
    # passa no schema e reprova na validação: sem os cenários externos que o esquema exige
    mudanca = [{"path": "training.scenario_source.inflow", "value": {"scheme": "external"}}]
    e = cliente.chamar(
        "deck_edit_json",
        {"path": str(toy / "config.json"), "changes": mudanca, "ensure_valid": True},
    )
    assert e.get("reverted") is True, str(e)[:300]


def test_deck_edit_parquet_dry_run(cliente, parquet):
    e = cliente.chamar(
        "deck_edit_parquet",
        {
            "path": parquet,
            "where": {"hydro_id": 0, "stage_id": 0},
            "set_values": {"mean_m3s": 41},
            "dry_run": True,
        },
    )
    assert e.get("matched_rows") == 1 and e.get("schema_preserved") is True, e


# ---------- execução ----------


def test_run_apply(rodada):
    _ok(rodada["apply"])


def test_run_plan(rodada):
    assert rodada["plan"].get("status") == "ok" and rodada["plan"].get("verdict") is not None


def test_run_start(rodada):
    assert rodada["start"].get("job_id"), rodada["start"]


def test_run_status_terminou(rodada):
    assert rodada["status"].get("state") == "succeeded", rodada["status"]


def test_run_logs(rodada):
    _ok(rodada["logs"])


def test_results_status(cliente, rodada):
    e = cliente.chamar("results_status", {"output_dir": rodada["output"]})
    assert e.get("run_status") == "complete" and e.get("software_version"), e


def test_case_validate_com_output_dir(cliente, toy, rodada):
    e = cliente.chamar("case_validate", {"case_dir": str(toy), "output_dir": rodada["output"]})
    assert e.get("status") in ("ok", "error") and e.get("exit_code") != 127, e


def test_results_convergence(cliente, rodada):
    _ok(cliente.chamar("results_convergence", {"output_dir": rodada["output"], "tail": 2}))


def test_results_policy(cliente, rodada):
    estagios = cliente.chamar("results_policy", {"output_dir": rodada["output"]}).get("estagios")
    assert any(s["n_cortes"] > 0 for s in estagios or []), estagios


def test_results_list_entities(cliente, rodada):
    e = cliente.chamar("results_list_entities", {"output_dir": rodada["output"]})
    assert "hydros" in e.get("entities", []), e.get("entities")


def test_results_query(cliente, rodada):
    consulta = {
        "output_dir": rodada["output"],
        "entity": "hydros",
        "group_by": ["stage_id"],
        "agg": "p10",
        "columns": ["storage_final_hm3"],
    }
    _ok(cliente.chamar("results_query", consulta))


def test_bridge_dashboard(cliente, toy, rodada):
    _ok(cliente.chamar("bridge_dashboard", {"case_dir": str(toy)}))


def test_bridge_dashboard_em_arquivo_escolhido(cliente, toy, rodada, rascunho):
    destino = rascunho / "d1.html"
    e = cliente.chamar("bridge_dashboard", {"case_dir": str(toy), "output": str(destino)})
    assert destino.is_file() and destino.stat().st_size > 0, e
    assert (e.get("artifacts") or {}).get("dashboard") == str(destino), e


def _copia_do_toy(toy: Path, destino: Path) -> Path:
    shutil.copytree(toy, destino, ignore=shutil.ignore_patterns("output", "dashboard.html"))
    return destino


def test_results_stochastic(cliente, toy, rodada, rascunho):
    # modelo estocástico: só gravado com exports.stochastic ligado
    caso = _copia_do_toy(toy, rascunho / "1dtoy-estocastico")
    cliente.chamar(
        "deck_edit_json",
        {
            "path": str(caso / "config.json"),
            "changes": [{"path": "exports", "value": {"stochastic": True}}],
        },
    )
    cliente.chamar(
        "run_apply",
        {"case_dir": str(caso), "overrides": {"iteration_limit": 2, "simulation_enabled": False}},
    )
    job = cliente.chamar("run_start", {"case_dir": str(caso), "override": True}).get("job_id")
    if job:
        _esperar(cliente, job)
    e = cliente.chamar(
        "results_stochastic", {"output_dir": str(caso / "output"), "aberturas_do_estagio": 0}
    )
    assert (e.get("par") or {}).get("total") == 0, e.get("par")
    assert (e.get("aberturas") or {}).get("n_aberturas") == 10, e.get("aberturas")


def test_run_cancel_interrompe_run_longo(cliente, toy, rodada, rascunho):
    caso = _copia_do_toy(toy, rascunho / "1dtoy-longo")
    cliente.chamar(
        "run_apply",
        {
            "case_dir": str(caso),
            "overrides": {"iteration_limit": 1_000_000, "simulation_enabled": False},
        },
    )
    res = cliente.chamar("run_start", {"case_dir": str(caso), "override": True, "time_budget_s": 1})
    assert res.get("job_id"), f"run longo não iniciou: {res}"
    time.sleep(2)
    e = cliente.chamar("run_cancel", {"job_id": res["job_id"]})
    assert e.get("state") == "cancelled", e


def test_run_status_job_inexistente(cliente):
    _recusa(cliente.chamar("run_status", {"job_id": "nao-existe"}))


# ---------- bridge ----------


def test_bridge_check_newave(cliente, caso_bridge):
    _tem_status(cliente.chamar("bridge_check_newave", {"src": str(_caso(caso_bridge, "newave"))}))


def test_bridge_convert_newave(cliente, caso_bridge, rascunho):
    src = _caso(caso_bridge, "newave")
    argumentos = {"src": str(src), "dst": str(rascunho / "newave"), "validate": True}
    _ok(cliente.chamar("bridge_convert_newave", argumentos, timeout=1800))


def test_bridge_compare_newave(cliente, caso_bridge, rodada):
    src = _caso(caso_bridge, "newave")
    argumentos = {"newave_dir": str(src), "output_dir": rodada["output"]}
    _tem_status(cliente.chamar("bridge_compare_newave", argumentos))


def test_bridge_check_decomp(cliente, caso_bridge):
    _tem_status(cliente.chamar("bridge_check_decomp", {"src": str(_caso(caso_bridge, "decomp"))}))


def test_bridge_convert_decomp_dry_run(cliente, caso_bridge, rascunho):
    src = _caso(caso_bridge, "decomp")
    argumentos = {"src": str(src), "dst": str(rascunho / "decomp"), "dry_run": True}
    e = cliente.chamar("bridge_convert_decomp", argumentos, timeout=1800)
    assert e.get("status") == "dry-run", e.get("status")


def test_bridge_convert_decomp_sem_importar_a_fcf(cliente, caso_bridge, rascunho):
    src = _caso(caso_bridge, "decomp")
    argumentos = {"src": str(src), "dst": str(rascunho / "decomp-sem-fcf"), "importar_fcf": False}
    e = cliente.chamar("bridge_convert_decomp", argumentos, timeout=1800)
    assert e.get("exit_code") == 0, e


def test_bridge_compare_decomp_formato_fora_da_lista(cliente, caso_bridge, rodada):
    src = _caso(caso_bridge, "decomp")
    argumentos = {"decomp_dir": str(src), "output_dir": rodada["output"], "fmt": "xml"}
    _recusa(cliente.chamar("bridge_compare_decomp", argumentos))


def test_bridge_compare_decomp_tolerancia(cliente, caso_bridge, rodada):
    src = _caso(caso_bridge, "decomp")
    argumentos = {"decomp_dir": str(src), "output_dir": rodada["output"], "tolerance": 1.5}
    _tem_status(cliente.chamar("bridge_compare_decomp", argumentos))


# ---------- fechamento: dependem de todos os anteriores ----------


def _bateria_inteira(request) -> bool:
    c = request.config
    return not (c.getoption("keyword") or c.getoption("markexpr")) and not any(
        "::" in a for a in c.args
    )


def test_sem_aviso_de_versoes_com_tudo_alinhado(request, cliente):
    if not _bateria_inteira(request):
        pytest.skip("só com a bateria inteira")
    assert not cliente.avisos, cliente.avisos[:3]


def test_todas_as_tools_chamadas(request, cliente, caso_bridge):
    if not _bateria_inteira(request):
        pytest.skip("só com a bateria inteira")
    esperadas = set(ALL)
    if not request.config.getoption("--com-rede"):
        esperadas.discard("instalar_novomodelo")
    if caso_bridge["newave"] is None:
        esperadas -= NEWAVE
    if caso_bridge["decomp"] is None:
        esperadas -= DECOMP
    assert not esperadas - cliente.chamadas, sorted(esperadas - cliente.chamadas)
