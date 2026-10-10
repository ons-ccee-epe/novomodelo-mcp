#!/usr/bin/env python3
"""Smoke test do guard de workspace (stdlib puro). Roda: python3 tests/smoke_paths.py"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cobre_mcp.config import load_settings              # noqa: E402
from cobre_mcp.adapters.paths import ensure_in_workspace  # noqa: E402


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
