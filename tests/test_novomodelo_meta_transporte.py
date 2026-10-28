"""Tools de meta do novomodelo (version/schema export): contratos de transporte e de guarda.

Sem binário `novomodelo` real e sem rede: binário ausente -> 127; saída não-JSON ->
envelope com texto bruto; output_dir fora do workspace -> recusa 13 pelo guard."""

import os
import sys
from pathlib import Path

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.novomodelo_meta import register_novomodelo_meta


class _CaptureMCP:
    """mcp falso: `@mcp.tool()` apenas captura a função registrada pelo nome."""

    def __init__(self):
        self.tools: dict[str, object] = {}

    def tool(self, *args, **kwargs):  # aceita annotations=… como o FastMCP
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _tools():
    mcp = _CaptureMCP()
    register_novomodelo_meta(mcp, load_settings())
    return mcp.tools


def _write_fake_novomodelo(dir_path: Path, body: str) -> str:
    """Gera um `novomodelo` falso em stdlib puro que delega a este mesmo python."""
    script = dir_path / "fake_novomodelo.py"
    script.write_text(
        "import sys\n"
        "argv = sys.argv[1:]\n"
        "if argv[:2] == ['--color', 'never']:\n"
        "    argv = argv[2:]\n" + body,
        encoding="utf-8",
    )
    launcher = dir_path / ("novomodelo.cmd" if os.name == "nt" else "novomodelo")
    if os.name == "nt":
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        launcher.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    return str(launcher)


def test_missing_binary_is_127(tmp_path, monkeypatch):
    """find_novomodelo -> None (sem NOVOMODELO_MCP_SOLVER_BIN e PATH vazio) vira envelope 127, sem exceção."""
    monkeypatch.delenv("NOVOMODELO_MCP_SOLVER_BIN", raising=False)
    monkeypatch.setenv("PATH", "")
    # HOME vazio também: a descoberta procura em ~/.cargo/bin, onde a máquina pode ter um real
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    env = _tools()["solver_version"]()
    assert env["status"] == "error", env
    assert env["exit_code"] == 127, env


def test_nonjson_output_lands_in_diagnostics(tmp_path, monkeypatch):
    """Saída não-JSON da CLI vira Error_Envelope carregando o texto bruto."""
    binpath = _write_fake_novomodelo(
        tmp_path,
        "print('isto nao e json: falha simulada da CLI')\nsys.exit(1)\n",
    )
    monkeypatch.setenv("NOVOMODELO_MCP_SOLVER_BIN", binpath)
    env = _tools()["solver_version"]()
    assert env["status"] == "error", env
    blob = " ".join(env.get("diagnostics", []))
    assert "isto nao e json" in blob, env


def test_output_dir_outside_workspace_refused_13(tmp_path, monkeypatch):
    """output_dir fora da raiz é recusado pelo Workspace_Guard com exit_code 13."""
    ws, outside = tmp_path / "ws", tmp_path / "fora"
    ws.mkdir()
    outside.mkdir()
    monkeypatch.setenv("NOVOMODELO_MCP_WORKSPACE", str(ws))
    env = _tools()["schema_export"](output_dir=str(outside / "schemas"))
    assert env["status"] == "error", env
    assert env["exit_code"] == 13, env
