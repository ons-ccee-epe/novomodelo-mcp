#!/usr/bin/env python3
"""Smoke test das tools de meta do novomodelo (version/schema export), stdlib puro.

Prova os contratos de transporte e de guarda sem binário `novomodelo` real e sem
rede: binário ausente -> 127; saída não-JSON -> envelope com texto bruto;
output_dir fora do workspace -> recusa 13 pelo guard. Roda:
python3 tests/smoke_novomodelo_meta.py"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novomodelo_mcp.config import load_settings            # noqa: E402
from novomodelo_mcp.tools.novomodelo_meta import register_novomodelo_meta  # noqa: E402


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
        "    argv = argv[2:]\n"
        + body
    )
    launcher = dir_path / ("novomodelo.cmd" if os.name == "nt" else "novomodelo")
    if os.name == "nt":
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n')
    else:
        launcher.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n'
        )
        launcher.chmod(0o755)
    return str(launcher)


def test_missing_binary_is_127():
    """find_novomodelo -> None (sem NOVOMODELO_MCP_SOLVER_BIN e PATH vazio) vira envelope 127, sem exceção."""
    old_bin = os.environ.pop("NOVOMODELO_MCP_SOLVER_BIN", None)
    saved = {k: os.environ.get(k) for k in ("PATH", "HOME", "USERPROFILE")}
    empty_home = tempfile.mkdtemp()
    os.environ["PATH"] = ""
    # HOME vazio também: a descoberta procura em ~/.cargo/bin, onde a máquina pode ter um real
    os.environ["HOME"] = os.environ["USERPROFILE"] = empty_home
    try:
        env = _tools()["solver_version"]()
        assert env["status"] == "error", env
        assert env["exit_code"] == 127, env
    finally:
        if old_bin is not None:
            os.environ["NOVOMODELO_MCP_SOLVER_BIN"] = old_bin
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.rmdir(empty_home)


def test_nonjson_output_lands_in_diagnostics():
    """Saída não-JSON da CLI vira Error_Envelope carregando o texto bruto."""
    with tempfile.TemporaryDirectory() as d:
        binpath = _write_fake_novomodelo(
            Path(d),
            "print('isto nao e json: falha simulada da CLI')\n"
            "sys.exit(1)\n",
        )
        old_bin = os.environ.get("NOVOMODELO_MCP_SOLVER_BIN")
        os.environ["NOVOMODELO_MCP_SOLVER_BIN"] = binpath
        try:
            env = _tools()["solver_version"]()
            assert env["status"] == "error", env
            blob = " ".join(env.get("diagnostics", []))
            assert "isto nao e json" in blob, env
        finally:
            if old_bin is not None:
                os.environ["NOVOMODELO_MCP_SOLVER_BIN"] = old_bin
            else:
                os.environ.pop("NOVOMODELO_MCP_SOLVER_BIN", None)


def test_output_dir_outside_workspace_refused_13():
    """output_dir fora da raiz é recusado pelo Workspace_Guard com exit_code 13."""
    with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as outside:
        old_ws = os.environ.get("NOVOMODELO_MCP_WORKSPACE")
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = ws
        try:
            target = str(Path(outside) / "schemas")
            env = _tools()["schema_export"](output_dir=target)
            assert env["status"] == "error", env
            assert env["exit_code"] == 13, env
        finally:
            if old_ws is not None:
                os.environ["NOVOMODELO_MCP_WORKSPACE"] = old_ws
            else:
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
