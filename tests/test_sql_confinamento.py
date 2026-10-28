"""`deck_sql` confinado ao workspace também no motor (DuckDB), e não só no texto:
identificador entre aspas e caminho montado por expressão não saem da pasta."""

import dataclasses

import pytest

from novomodelo_mcp.adapters.sql import run_readonly_sql
from novomodelo_mcp.config import load_settings

pytest.importorskip("duckdb")


@pytest.fixture
def ws(tmp_path):
    dentro, fora = tmp_path / "estudos ação", tmp_path / "fora"
    (dentro / "caso" / "output").mkdir(parents=True)
    fora.mkdir()
    (dentro / "caso" / "output" / "a.csv").write_text("x\n1\n", encoding="utf-8")
    (fora / "segredo.csv").write_text("s\nvalor-secreto-q7\n", encoding="utf-8")
    return dataclasses.replace(load_settings(), workspace=str(dentro)), dentro, fora


def _recusado(r):
    return r["status"] == "error" and "valor-secreto-q7" not in str(r)


def test_identificador_entre_aspas_fora_do_workspace_e_recusado(ws):
    settings, _, fora = ws
    assert _recusado(run_readonly_sql(f'SELECT * FROM "{fora}/segredo.csv"', settings=settings))


def test_caminho_montado_por_expressao_e_recusado(ws):
    settings, _, fora = ws
    q = "SELECT * FROM read_csv(" + " || ".join(f"'{p}'" for p in (str(fora), "/segredo.csv")) + ")"
    assert _recusado(run_readonly_sql(q, settings=settings))
    q = "SELECT content FROM read_text(chr(47) || 'etc' || chr(47) || 'hostname')"
    assert run_readonly_sql(q, settings=settings)["status"] == "error"


def test_link_simbolico_dentro_do_workspace_para_fora_e_recusado(ws):
    settings, dentro, fora = ws
    (dentro / "atalho").symlink_to(fora, target_is_directory=True)
    assert _recusado(
        run_readonly_sql(f'SELECT * FROM "{dentro}/atalho/segredo.csv"', settings=settings)
    )


def test_glob_dentro_do_workspace_continua_funcionando(ws):
    settings, dentro, _ = ws
    r = run_readonly_sql(f"SELECT sum(x) s FROM read_csv('{dentro}/**/*.csv')", settings=settings)
    assert r["status"] == "ok" and r["rows"] == [{"s": 1}]


def test_alias_ou_coluna_entre_aspas_com_barra_nao_e_caminho(ws):
    settings, dentro, _ = ws
    r = run_readonly_sql(
        f'SELECT x AS "custo R$/MWh", x AS "total.csv" FROM read_csv(\'{dentro}/**/*.csv\')',
        settings=settings,
    )
    assert r["status"] == "ok" and r["rows"] == [{"custo R$/MWh": 1, "total.csv": 1}]


def test_describe_e_summarize_sao_leitura_e_rodam(ws):
    settings, dentro, _ = ws
    csv = (dentro / "caso" / "output" / "a.csv").as_posix()
    d = run_readonly_sql(f"DESCRIBE SELECT * FROM read_csv('{csv}')", settings=settings)
    assert d["status"] == "ok" and d["rows"][0]["column_name"] == "x", d
    s = run_readonly_sql(f"SUMMARIZE SELECT * FROM read_csv('{csv}')", settings=settings)
    assert s["status"] == "ok" and s["rows"][0]["column_name"] == "x", s


def test_describe_fora_do_workspace_continua_recusado(ws):
    settings, _, fora = ws
    r = run_readonly_sql(
        f"DESCRIBE SELECT * FROM read_csv('{fora.as_posix()}/segredo.csv')", settings=settings
    )
    assert _recusado(r)


def test_barra_de_progresso_desligada_porque_ela_sai_no_stdout_do_protocolo(ws):
    """Num processo com o stdout num pipe (como o servidor MCP roda), o DuckDB liga a barra
    por padrão; dentro do pytest ela já vem desligada, por isso o teste usa um subprocesso."""
    import json
    import subprocess
    import sys

    settings, dentro, _ = ws
    codigo = (
        "import dataclasses, json\n"
        "from novomodelo_mcp.config import load_settings\n"
        "from novomodelo_mcp.adapters.sql import run_readonly_sql\n"
        f"s = dataclasses.replace(load_settings(), workspace={str(dentro)!r})\n"
        "r = run_readonly_sql(\"SELECT current_setting('enable_progress_bar') AS barra\", settings=s)\n"
        "print(json.dumps(r['rows']))\n"
    )
    out = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout.strip().splitlines()[-1]) == [{"barra": False}], out.stdout


def test_consulta_confinada_nao_importa_o_pandas(ws):
    """Num parâmetro (`?`), o DuckDB importa o pandas e o numpy. No Windows, esse import com o
    servidor MCP no ar trava o `deck_sql`; o confinamento não pode depender de parâmetro."""
    import json
    import subprocess
    import sys

    settings, dentro, _ = ws
    codigo = (
        "import dataclasses, json, sys\n"
        "from novomodelo_mcp.config import load_settings\n"
        "from novomodelo_mcp.adapters.sql import run_readonly_sql\n"
        f"s = dataclasses.replace(load_settings(), workspace={str(dentro)!r})\n"
        f"q = \"SELECT sum(x) s FROM read_csv('{dentro.as_posix()}/**/*.csv')\"\n"
        "r = run_readonly_sql(q, settings=s)\n"
        "print(json.dumps([r['status'], 'pandas' in sys.modules, 'numpy' in sys.modules]))\n"
    )
    out = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout.strip().splitlines()[-1]) == ["ok", False, False], out.stdout


def test_pasta_com_aspa_continua_confinada(tmp_path):
    dentro, fora = tmp_path / "estudo d'água", tmp_path / "fora"
    dentro.mkdir()
    fora.mkdir()
    (dentro / "a.csv").write_text("x\n1\n", encoding="utf-8")
    (fora / "segredo.csv").write_text("s\nvalor-secreto-q7\n", encoding="utf-8")
    settings = dataclasses.replace(load_settings(), workspace=str(dentro))
    literal = (dentro / "a.csv").as_posix().replace("'", "''")
    r = run_readonly_sql(f"SELECT sum(x) s FROM read_csv('{literal}')", settings=settings)
    assert r["status"] == "ok" and r["rows"] == [{"s": 1}], r
    assert _recusado(run_readonly_sql(f'SELECT * FROM "{fora}/segredo.csv"', settings=settings))
