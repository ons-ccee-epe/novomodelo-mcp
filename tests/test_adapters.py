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


def _scripts_dir_with_fake_bridge(tmp_path, monkeypatch):
    import os
    import sysconfig
    scripts = tmp_path / "venv-bin"
    scripts.mkdir()
    name = "novomodelo-bridge.exe" if os.name == "nt" else "novomodelo-bridge"
    fake = scripts / name
    fake.write_text("#!/bin/sh\necho novomodelo-bridge 0.18.0\n")
    fake.chmod(0o755)
    real = sysconfig.get_path
    monkeypatch.setattr(sysconfig, "get_path",
                        lambda key, *a, **k: str(scripts) if key == "scripts" else real(key, *a, **k))
    return str(fake)


def test_bridge_do_pacote_vem_antes_do_path(tmp_path, monkeypatch):
    from novomodelo_mcp.adapters.discovery import bridge_origin
    fake = _scripts_dir_with_fake_bridge(tmp_path, monkeypatch)
    monkeypatch.delenv("NOVOMODELO_MCP_BRIDGE_BIN", raising=False)
    assert bridge_origin(load_settings()) == (fake, "pacote")


def test_variavel_vence_o_bridge_do_pacote(tmp_path, monkeypatch):
    from novomodelo_mcp.adapters.discovery import bridge_origin, find_bridge
    _scripts_dir_with_fake_bridge(tmp_path, monkeypatch)
    monkeypatch.setenv("NOVOMODELO_MCP_BRIDGE_BIN", FAKE)
    assert bridge_origin(load_settings()) == (FAKE, "variavel")
    assert find_bridge(load_settings()) == FAKE


def test_sem_pacote_cai_no_path(tmp_path, monkeypatch):
    import sysconfig
    from novomodelo_mcp.adapters.discovery import bridge_origin
    empty = tmp_path / "vazio"
    empty.mkdir()
    real = sysconfig.get_path
    monkeypatch.setattr(sysconfig, "get_path",
                        lambda key, *a, **k: str(empty) if key == "scripts" else real(key, *a, **k))
    monkeypatch.delenv("NOVOMODELO_MCP_BRIDGE_BIN", raising=False)
    no_path = tmp_path / "no-path"
    no_path.mkdir()
    import os
    name = "novomodelo-bridge.exe" if os.name == "nt" else "novomodelo-bridge"
    (no_path / name).write_text("#!/bin/sh\n")
    (no_path / name).chmod(0o755)
    monkeypatch.setenv("PATH", str(no_path))
    assert bridge_origin(load_settings()) == (str(no_path / name), "path")


def test_server_info_mostra_a_origem_do_bridge(tmp_path, monkeypatch):
    import urllib.error
    from novomodelo_mcp.adapters import versions
    from novomodelo_mcp.server import build_server
    _scripts_dir_with_fake_bridge(tmp_path, monkeypatch)
    monkeypatch.delenv("NOVOMODELO_MCP_BRIDGE_BIN", raising=False)
    monkeypatch.setattr(versions, "_open", lambda req, **k: (_ for _ in ()).throw(
        urllib.error.URLError("sem rede no teste")))
    versions.reset_caches()
    info = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}["server_info"]()
    versions.reset_caches()
    assert info["bridge"]["origem"] == "pacote"
    assert info["versoes"]["bridge"]["origem"] == "pacote"
