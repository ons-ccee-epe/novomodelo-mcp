"""Testes por exemplo da Schema_Export_Tool (pytest). Usam o `novomodelo` falso.

Toda a suíte é offline: a CLI `novomodelo` falsa é alcançada via `NOVOMODELO_MCP_SOLVER_BIN`
(`monkeypatch.setenv`), espelhando o padrão de `test_novomodelo_meta.py`. Nenhum
teste exige o binário real nem faz requisição de rede.

O `novomodelo` falso (`fake_novomodelo.py`) é um script Python; `run_novomodelo` o executa
diretamente como `NOVOMODELO_MCP_SOLVER_BIN`. Para rodá-lo de forma portátil, cada teste aponta
`NOVOMODELO_MCP_SOLVER_BIN` para um lançador gerado em diretório temporário que invoca o script
com o interpretador corrente.
"""

import os
import stat
import sys
from pathlib import Path

import pytest

import novomodelo_mcp.tools.novomodelo_meta as novomodelo_meta
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.novomodelo_meta import register_novomodelo_meta

FAKE = Path(__file__).resolve().parent / "fake_novomodelo.py"


class _CaptureMCP:
    """`mcp` falso cujo `tool()` captura a função registrada, para chamá-la direto.

    Dispensa a maquinaria async do FastMCP: a tool é uma função Python comum e o
    teste a invoca como o servidor faria após o despacho stdio.
    """

    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _schema_export_tool(settings):
    mcp = _CaptureMCP()
    register_novomodelo_meta(mcp, settings)
    return mcp.tools["schema_export"]


@pytest.fixture
def fake_novomodelo_bin(tmp_path):
    """Lançador executável do `novomodelo` falso, confinado a um diretório temporário.

    Devolve o caminho a apontar em `NOVOMODELO_MCP_SOLVER_BIN`. Portátil: em Windows gera um
    `.cmd`; em POSIX, um shell script. Ambos repassam o argv ao script falso via
    o interpretador corrente.
    """
    if os.name == "nt":
        launcher = tmp_path / "novomodelo.cmd"
        launcher.write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
    else:
        launcher = tmp_path / "novomodelo"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    return str(launcher)


def test_happy_path_status_ok(monkeypatch, fake_novomodelo_bin):
    monkeypatch.setenv("NOVOMODELO_MCP_SOLVER_BIN", fake_novomodelo_bin)
    # the caller's environment may set NOVOMODELO_MCP_WORKSPACE; drop it so the guard lets us reach the fake CLI.
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    env = _schema_export_tool(load_settings())()
    assert env["status"] == "ok"
    assert env["exit_code"] == 0


def test_single_subcommand_is_schema_export(monkeypatch, fake_novomodelo_bin):
    monkeypatch.setenv("NOVOMODELO_MCP_SOLVER_BIN", fake_novomodelo_bin)
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    env = _schema_export_tool(load_settings())()
    non_flag = [a for a in env["argv"] if not a.startswith("--")]
    assert non_flag == ["schema", "export"]


def test_output_dir_appends_flag(monkeypatch, fake_novomodelo_bin, tmp_path):
    monkeypatch.setenv("NOVOMODELO_MCP_SOLVER_BIN", fake_novomodelo_bin)
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    out_dir = str(tmp_path / "schemas")
    env = _schema_export_tool(load_settings())(output_dir=out_dir)
    assert env["argv"][:2] == ["schema", "export"]
    assert "--output-dir" in env["argv"]
    assert env["argv"][env["argv"].index("--output-dir") + 1] == out_dir
    assert env["artifacts"]["schemas"] == out_dir


def test_missing_binary_returns_127(monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_SOLVER_BIN", raising=False)
    monkeypatch.setattr("novomodelo_mcp.adapters.novomodelo.find_novomodelo", lambda settings: None)
    env = _schema_export_tool(load_settings())()
    assert env["status"] == "error"
    assert env["exit_code"] == 127


def test_timeout_returns_minus_one(monkeypatch, fake_novomodelo_bin):
    monkeypatch.setenv("NOVOMODELO_MCP_SOLVER_BIN", fake_novomodelo_bin)
    monkeypatch.setattr(
        novomodelo_meta, "run_novomodelo", _run_novomodelo_with_mode("timeout", timeout=2.0)
    )
    env = _schema_export_tool(load_settings())()
    assert env["status"] == "error"
    assert env["exit_code"] == -1


def test_nonjson_output_carries_raw_text(monkeypatch, fake_novomodelo_bin):
    monkeypatch.setenv("NOVOMODELO_MCP_SOLVER_BIN", fake_novomodelo_bin)
    monkeypatch.setattr(novomodelo_meta, "run_novomodelo", _run_novomodelo_with_mode("nonjson"))
    env = _schema_export_tool(load_settings())()
    assert env["status"] == "error"
    assert any("isto nao e json" in d for d in env["diagnostics"])


def test_never_raises_on_adapter_exception(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("falha de transporte simulada")

    monkeypatch.setattr(novomodelo_meta, "run_novomodelo", boom)
    env = _schema_export_tool(load_settings())()
    assert env["status"] == "error"
    assert "exit_code" in env
    assert isinstance(env["diagnostics"], list) and env["diagnostics"]


def test_long_diagnostics_are_capped(monkeypatch):
    s = load_settings()

    def flood(subargv, **kwargs):
        return {
            "status": "error",
            "exit_code": 3,
            "diagnostics": [f"d{i}" for i in range(s.max_diagnostics + 5)],
        }

    monkeypatch.setattr(novomodelo_meta, "run_novomodelo", flood)
    env = _schema_export_tool(s)()
    assert len(env["diagnostics"]) == s.max_diagnostics + 1


def _run_novomodelo_with_mode(mode, *, timeout=10.0):
    """Encapsula `run_novomodelo` injetando a flag de modo da CLI falsa no subargv.

    `timeout` curto é passado só no modo `timeout`, para provar o `-1` sem
    esperar o teto padrão de produção; os demais modos usam uma folga suficiente
    para o custo de iniciar o interpretador.
    """
    real = novomodelo_meta.run_novomodelo

    def wrapped(subargv, **kwargs):
        kwargs.setdefault("timeout", timeout)
        return real([*subargv, f"--mode={mode}"], **kwargs)

    return wrapped
