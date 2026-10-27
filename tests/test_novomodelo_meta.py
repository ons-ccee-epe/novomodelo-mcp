"""Testes por exemplo da Version_Tool (pytest). Usam o `novomodelo` falso.

Toda a suíte é offline: a CLI `novomodelo` falsa é alcançada via `NOVOMODELO_MCP_SOLVER_BIN`
(`monkeypatch.setenv`), espelhando o padrão de `test_adapters.py`. Nenhum teste
exige o binário real nem faz requisição de rede.

O `novomodelo` falso (`fake_novomodelo.py`) é um script Python; `version_cli` o executa
diretamente como `NOVOMODELO_MCP_SOLVER_BIN`. Em POSIX o shebang basta; para rodar o mesmo
script de forma portátil, cada teste aponta `NOVOMODELO_MCP_SOLVER_BIN` para um lançador gerado
em diretório temporário que invoca o script com o interpretador corrente.
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


def _version_tool(settings):
    mcp = _CaptureMCP()
    register_novomodelo_meta(mcp, settings)
    return mcp.tools["solver_version"]


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


def test_happy_path_parses_version_fields(monkeypatch, fake_novomodelo_bin):
    monkeypatch.setenv("NOVOMODELO_MCP_SOLVER_BIN", fake_novomodelo_bin)
    env = _version_tool(load_settings())()
    assert env["status"] == "ok"
    assert env["exit_code"] == 0
    assert env["version"] == "v9.9.9"
    assert env["solver"] == "HiGHS 1.13.1"
    assert "novomodelo" in env["raw"]
    assert "v9.9.9" in env["raw"]


def test_version_runs_without_json_flag(monkeypatch, fake_novomodelo_bin):
    """`version_cli` roda `novomodelo version` SEM `--json` (que a CLI real rejeitaria).

    A prova é indireta mas honesta: a CLI falsa só emite o texto parseável para
    `version` puro. Se `--json` (ou qualquer flag extra) fosse enviado, o ramo de
    texto não dispararia e `version`/`raw` não bateriam.
    """
    monkeypatch.setenv("NOVOMODELO_MCP_SOLVER_BIN", fake_novomodelo_bin)
    env = _version_tool(load_settings())()
    assert env["status"] == "ok"
    assert env["version"] == "v9.9.9"
    assert env["raw"].splitlines()[0].split()[0] == "novomodelo"


def test_missing_binary_returns_127(monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_SOLVER_BIN", raising=False)
    monkeypatch.setattr("novomodelo_mcp.adapters.novomodelo.find_novomodelo", lambda settings: None)
    env = _version_tool(load_settings())()
    assert env["status"] == "error"
    assert env["exit_code"] == 127


def test_timeout_returns_minus_one(monkeypatch):
    monkeypatch.setattr(novomodelo_meta, "version_cli", _version_cli_envelope(-1))
    env = _version_tool(load_settings())()
    assert env["status"] == "error"
    assert env["exit_code"] == -1


def test_error_exit_carries_text(monkeypatch):
    """Saída de erro (exit != 0) vira Error_Envelope carregando o texto da CLI."""
    monkeypatch.setattr(
        novomodelo_meta,
        "version_cli",
        _version_cli_envelope(2, detail="error: unexpected argument '--json'"),
    )
    env = _version_tool(load_settings())()
    assert env["status"] == "error"
    assert env["exit_code"] == 2
    assert any("--json" in d for d in env["diagnostics"])


def test_never_raises_on_adapter_exception(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("falha de transporte simulada")

    monkeypatch.setattr(novomodelo_meta, "version_cli", boom)
    env = _version_tool(load_settings())()
    assert env["status"] == "error"
    assert "exit_code" in env
    assert isinstance(env["diagnostics"], list) and env["diagnostics"]


def _version_cli_envelope(exit_code, *, detail=""):
    """Substitui `version_cli` por um sentinela que devolve um Error_Envelope fixo.

    `version_cli` não aceita `subargv` (roda sempre `novomodelo version` puro), logo os
    códigos de transporte (-1 timeout, erro != 0) são exercidos devolvendo o
    envelope diretamente, pelos construtores do owner.
    """
    from novomodelo_mcp.adapters.envelope import error as _error

    def fake(*args, **kwargs):
        return _error(exit_code, "novomodelo version encerrou com erro", detail)

    return fake


def test_version_parse_does_not_depend_on_program_name(monkeypatch):
    """A 1ª linha é lida por posição: o parse vale para qualquer nome de programa.

    Regressão do rename: antes, `version` só era preenchido se a 1ª palavra fosse
    exatamente o nome antigo; com o binário renomeado o campo sumia em silêncio.
    """
    import subprocess

    from novomodelo_mcp.adapters import novomodelo as adapter

    text = "qualquernome   v0.18.0\nsolver: HiGHS 1.13.1\narch:   aarch64-macos\n"
    monkeypatch.setattr(adapter, "find_novomodelo", lambda settings: "/fake/bin")
    monkeypatch.setattr(
        adapter.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=text, stderr=""),
    )
    env = adapter.version_cli(settings=load_settings())
    assert env["status"] == "ok"
    assert env["program"] == "qualquernome"
    assert env["version"] == "v0.18.0"
    assert env["solver"] == "HiGHS 1.13.1"
