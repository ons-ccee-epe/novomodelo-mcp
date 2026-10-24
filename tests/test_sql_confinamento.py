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
    (fora / "segredo.csv").write_text("s\n42\n", encoding="utf-8")
    return dataclasses.replace(load_settings(), workspace=str(dentro)), dentro, fora


def _recusado(r):
    return r["status"] == "error" and "42" not in str(r)


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
    assert _recusado(run_readonly_sql(f'SELECT * FROM "{dentro}/atalho/segredo.csv"', settings=settings))


def test_glob_dentro_do_workspace_continua_funcionando(ws):
    settings, dentro, _ = ws
    r = run_readonly_sql(f"SELECT sum(x) s FROM read_csv('{dentro}/**/*.csv')", settings=settings)
    assert r["status"] == "ok" and r["rows"] == [{"s": 1}]
