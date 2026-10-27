"""O servidor lê o protocolo de uma cópia do stdin, e o fd 0 do processo fica no NUL.

No Windows, uma leitura pendente no pipe do stdin trava a carga de DLL nativa (o
numpy, numa tool) até chegar a próxima mensagem. Com a troca, quem consulta o stdin
do processo encontra o NUL.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from novomodelo_mcp import server

FILHO = r"""
import os, sys
from novomodelo_mcp.server import _stdin_proprio
_stdin_proprio()
print(repr(sys.stdin.readline()))
print(repr(os.read(0, 16)))
"""


def test_protocolo_sai_da_copia_e_o_fd0_vai_para_o_nul():
    proc = subprocess.run(
        [sys.executable, "-c", FILHO],
        input="mensagem\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["'mensagem\\n'", "b''"]


def test_stdin_fechado_nao_derruba_o_servidor(monkeypatch):
    def sem_stdin(_fd):
        raise OSError("fd 0 fechado")

    monkeypatch.setattr(server.os, "dup", sem_stdin)
    antes = sys.stdin
    server._stdin_proprio()
    assert sys.stdin is antes


def test_main_troca_o_stdin_antes_de_subir(monkeypatch):
    ordem: list[str] = []

    class Falso:
        def run(self):
            ordem.append("run")

    monkeypatch.setattr(server, "_stdin_proprio", lambda: ordem.append("stdin"))
    monkeypatch.setattr(server, "build_server", Falso)
    monkeypatch.setattr(sys, "argv", ["novomodelo-mcp"])
    server.main()
    assert ordem == ["stdin", "run"]


def test_configurar_nao_troca_o_stdin(monkeypatch):
    from novomodelo_mcp import client_config

    chamado: list[bool] = []
    monkeypatch.setattr(server, "_stdin_proprio", lambda: chamado.append(True))
    monkeypatch.setattr(client_config, "main", lambda _args: 0)
    monkeypatch.setattr(sys, "argv", ["novomodelo-mcp", "configurar"])
    with pytest.raises(SystemExit):
        server.main()
    assert chamado == []
