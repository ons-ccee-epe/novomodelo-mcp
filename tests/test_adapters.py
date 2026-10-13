"""Testes de contrato do adaptador (pytest). Usam o novomodelo-bridge falso."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from novomodelo_mcp.adapters.bridge import run_bridge
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.shaping import cap_envelope

from _fakes import fake_bin  # noqa: E402

FAKE = fake_bin("fake_novomodelo_bridge.py")


def test_ok_envelope(monkeypatch):
    monkeypatch.setenv("NOVOMODELO_MCP_BRIDGE_BIN", FAKE)
    env = run_bridge(["check", "newave", "/x"], settings=load_settings())
    assert env["status"] == "ok"
    assert env["exit_code"] == 0
    assert env["command"] == "check newave"


def test_error_exit_code(monkeypatch):
    monkeypatch.setenv("NOVOMODELO_MCP_BRIDGE_BIN", FAKE)
    env = run_bridge(["boom"], settings=load_settings())
    assert env["status"] == "error"
    assert env["exit_code"] == 3


def test_missing_binary(monkeypatch):
    monkeypatch.setenv("NOVOMODELO_MCP_BRIDGE_BIN", "/nope/novomodelo-bridge")
    env = run_bridge(["check", "newave", "x"], settings=load_settings())
    assert env["status"] == "error"


def test_cap_diagnostics():
    s = load_settings()
    big = {"diagnostics": [f"d{i}" for i in range(s.max_diagnostics + 5)]}
    out = cap_envelope(big, s)
    assert len(out["diagnostics"]) == s.max_diagnostics + 1
