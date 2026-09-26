"""Testes de contrato do adaptador (pytest). Usam o cobre-bridge falso."""
from pathlib import Path

from cobre_mcp.adapters.bridge import run_bridge
from cobre_mcp.config import load_settings
from cobre_mcp.tools.shaping import cap_envelope

FAKE = str(Path(__file__).resolve().parent / "fake_cobre_bridge.py")


def test_ok_envelope(monkeypatch):
    monkeypatch.setenv("COBRE_BRIDGE_BIN", FAKE)
    env = run_bridge(["check", "newave", "/x"], settings=load_settings())
    assert env["status"] == "ok"
    assert env["exit_code"] == 0
    assert env["command"] == "check newave"


def test_error_exit_code(monkeypatch):
    monkeypatch.setenv("COBRE_BRIDGE_BIN", FAKE)
    env = run_bridge(["boom"], settings=load_settings())
    assert env["status"] == "error"
    assert env["exit_code"] == 3


def test_missing_binary(monkeypatch):
    monkeypatch.setenv("COBRE_BRIDGE_BIN", "/nope/cobre-bridge")
    env = run_bridge(["check", "newave", "x"], settings=load_settings())
    assert env["status"] == "error"


def test_cap_diagnostics():
    s = load_settings()
    big = {"diagnostics": [f"d{i}" for i in range(s.max_diagnostics + 5)]}
    out = cap_envelope(big, s)
    assert len(out["diagnostics"]) == s.max_diagnostics + 1
