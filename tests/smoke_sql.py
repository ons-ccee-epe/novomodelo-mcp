#!/usr/bin/env python3
"""Smoke test do deck_sql / adapters.sql.

Duas camadas:
  - GUARD (puro, stdlib): sempre roda — e a parte critica de seguranca.
  - EXECUCAO (DuckDB + Polars): so roda se as libs existirem; senao, SKIP.

Roda: python3 tests/smoke_sql.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novomodelo_mcp.adapters import sql as S  # noqa: E402

WS = [Path("/work").resolve()]


# ---------- GUARD (sem duckdb) ----------

def test_guard_ok_select_within_workspace():
    q = "SELECT hydro_id, min(value_m3s) FROM read_parquet('/work/a.parquet') GROUP BY 1"
    assert S.guard_sql(q, WS) is None


def test_guard_blocks_path_outside_workspace():
    q = "SELECT * FROM read_parquet('/etc/passwd.parquet')"
    err = S.guard_sql(q, WS)
    assert err and err["status"] == "error" and err["exit_code"] == 13, err


def test_guard_refusal_brings_no_bypass_and_suggested_folder():
    from novomodelo_mcp.adapters.paths import NAO_CONTORNE
    err = S.guard_sql("SELECT * FROM read_parquet('/estudos/x.parquet')", WS)
    assert err["exit_code"] == 13 and NAO_CONTORNE in err["diagnostics"], err
    assert err["pasta_sugerida"] == str(Path("/estudos").resolve()), err


def test_guard_dotdot_escape_is_resolved_and_blocked():
    q = "SELECT * FROM read_parquet('/work/../etc/x.parquet')"
    err = S.guard_sql(q, WS)
    assert err and err["exit_code"] == 13, err  # resolve() neutraliza o ..


def test_guard_blocks_remote_scheme():
    q = "SELECT * FROM read_parquet('s3://bucket/x.parquet')"
    err = S.guard_sql(q, WS)
    assert err and err["exit_code"] == 13, err


def test_guard_blocks_copy_to():
    q = "COPY (SELECT 1) TO '/work/out.csv'"
    err = S.guard_sql(q, WS)
    assert err and err["exit_code"] == 13, err


def test_guard_blocks_copy_hidden_in_select():
    # COPY como palavra em qualquer posicao e barrado (defesa em profundidade)
    q = "SELECT 1; COPY (SELECT 1) TO '/work/x.csv'"
    err = S.guard_sql(q, WS)
    assert err and err["status"] == "error", err  # >1 comando OU palavra proibida


def test_guard_blocks_attach_and_install():
    for q in ("ATTACH '/work/x.db'", "INSTALL httpfs", "SELECT 1; DROP TABLE t"):
        err = S.guard_sql(q, WS)
        assert err and err["status"] == "error", (q, err)


def test_guard_allows_with_cte():
    q = "WITH t AS (SELECT * FROM read_parquet('/work/a.parquet')) SELECT count(*) FROM t"
    assert S.guard_sql(q, WS) is None


def test_guard_path_in_comment_is_ignored_not_executed():
    # caminho de fora citado num comentario nao deve derrubar nem liberar leitura real
    q = "SELECT 1 -- read_parquet('/etc/secret.parquet')\n"
    assert S.guard_sql(q, WS) is None


def test_guard_offset_not_confused_with_set():
    q = "SELECT * FROM read_parquet('/work/a.parquet') LIMIT 5 OFFSET 10"
    assert S.guard_sql(q, WS) is None


def test_guard_empty_query():
    assert S.guard_sql("   ", WS)["status"] == "error"


def test_guard_unrestricted_allows_any_local_path():
    # sem raizes (workspace irrestrito): caminho local passa, remoto ainda barra
    assert S.guard_sql("SELECT * FROM read_parquet('/anywhere/a.parquet')", []) is None
    assert S.guard_sql("SELECT * FROM read_parquet('http://h/a.parquet')", [])["exit_code"] == 13


# ---------- EXECUCAO (precisa de duckdb + polars) ----------

def _has_exec_libs() -> bool:
    try:
        import duckdb  # noqa: F401
        import polars  # noqa: F401
        return True
    except ModuleNotFoundError:
        return False


def _settings_for(ws: str, max_rows: int = 1000):
    os.environ["NOVOMODELO_MCP_WORKSPACE"] = ws
    os.environ["NOVOMODELO_MCP_TIMEOUT"] = "30"
    import dataclasses
    from novomodelo_mcp.config import load_settings
    return dataclasses.replace(load_settings(), max_rows=max_rows)


def test_exec_group_by_and_conditional_count():
    if not _has_exec_libs():
        print("  SKIP test_exec_group_by_and_conditional_count (sem duckdb/polars)")
        return
    import polars as pl
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "inflow.parquet"
        pl.DataFrame({
            "hydro_id": [0, 0, 0, 1, 1],
            "value_m3s": [-5.0, 10.0, 20.0, 3.0, -1.0],
        }).write_parquet(p)
        st = _settings_for(d)
        q = (f"SELECT hydro_id, min(value_m3s) AS mn, "
             f"count(*) FILTER (WHERE value_m3s < 0) AS n_neg "
             f"FROM read_parquet('{p}') GROUP BY hydro_id ORDER BY hydro_id")
        out = S.run_readonly_sql(q, settings=st)
        assert out["status"] == "ok", out
        rows = {r["hydro_id"]: r for r in out["rows"]}
        assert rows[0]["mn"] == -5.0 and rows[0]["n_neg"] == 1, out
        assert rows[1]["n_neg"] == 1, out


def test_exec_truncation_flag():
    if not _has_exec_libs():
        print("  SKIP test_exec_truncation_flag (sem duckdb/polars)")
        return
    import polars as pl
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.parquet"
        pl.DataFrame({"x": list(range(10))}).write_parquet(p)
        st = _settings_for(d, max_rows=3)
        out = S.run_readonly_sql(f"SELECT x FROM read_parquet('{p}')", settings=st)
        assert out["status"] == "ok" and out["row_count"] == 3, out
        assert out["truncated"] is True, out


def test_exec_path_outside_workspace_blocked_before_run():
    if not _has_exec_libs():
        print("  SKIP test_exec_path_outside_workspace_blocked_before_run (sem duckdb/polars)")
        return
    with tempfile.TemporaryDirectory() as d:
        st = _settings_for(d)
        out = S.run_readonly_sql("SELECT * FROM read_parquet('/etc/x.parquet')", settings=st)
        assert out["status"] == "error" and out["exit_code"] == 13, out


def test_exec_date_is_jsonable():
    if not _has_exec_libs():
        print("  SKIP test_exec_date_is_jsonable (sem duckdb/polars)")
        return
    import json

    import polars as pl
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "dt.parquet"
        pl.DataFrame({"d": [pl.date(2026, 1, 1)]}).select(
            pl.date(2026, 1, 1).alias("d")
        ).write_parquet(p)
        st = _settings_for(d)
        out = S.run_readonly_sql(f"SELECT d FROM read_parquet('{p}')", settings=st)
        assert out["status"] == "ok", out
        json.dumps(out["rows"])  # nao pode lancar (date -> isoformat str)


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passaram")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
