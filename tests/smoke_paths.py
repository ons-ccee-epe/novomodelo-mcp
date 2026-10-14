#!/usr/bin/env python3
"""Smoke test do guard de workspace (stdlib puro). Roda: python3 tests/smoke_paths.py"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novomodelo_mcp.config import load_settings              # noqa: E402
from novomodelo_mcp.adapters.paths import ensure_in_workspace  # noqa: E402


def test_unrestricted():
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)
    assert ensure_in_workspace("/etc/passwd", settings=load_settings()) is None


def test_within_root():
    with tempfile.TemporaryDirectory() as d:
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = d
        inside = str(Path(d) / "deck" / "config.json")
        assert ensure_in_workspace(inside, settings=load_settings()) is None
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


def test_outside_root_blocked():
    with tempfile.TemporaryDirectory() as d:
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = d
        err = ensure_in_workspace("/etc/passwd", settings=load_settings())
        assert err is not None and err["status"] == "error", err
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


def test_traversal_blocked():
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d) / "ws"
        ws.mkdir()
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = str(ws)
        escape = str(ws / ".." / "secret.txt")
        err = ensure_in_workspace(escape, settings=load_settings())
        assert err is not None and err["status"] == "error", err
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


def test_results_query_entity_traversal_blocked():
    from novomodelo_mcp.adapters.results import simulation_query
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d) / "ws"
        (ws / "output" / "simulation").mkdir(parents=True)
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = str(ws)
        err = simulation_query(str(ws / "output"), "../x", settings=load_settings())
        assert err["status"] == "error" and err["exit_code"] == 13, err
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


def test_find_case_dir_stops_at_workspace_root():
    from novomodelo_mcp.adapters.deck_io import find_case_dir
    from novomodelo_mcp.adapters.paths import allowed_roots
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "config.json").write_text("{}", encoding="utf-8")
        ws = Path(d) / "ws"
        ws.mkdir()
        (ws / "x.json").write_text("{}", encoding="utf-8")
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = str(ws)
        roots = allowed_roots(load_settings())
        assert find_case_dir(str(ws / "x.json"), stop_at=roots) is None
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


def test_schema_tipo_must_be_a_plain_name():
    from novomodelo_mcp.adapters.reference import read_schema
    for tipo in ("D:segredo", "../config", "a.b"):
        assert read_schema(load_settings(), tipo)["status"] == "error", tipo


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passaram")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
