"""Subprocessos do servidor não herdam o stdin, que é o canal JSON-RPC com o cliente.

No Windows, com uma leitura pendente do servidor nesse pipe, o filho que consulta o
stdin (a inicialização do Python faz isso) fica bloqueado até o cliente mandar outra
mensagem; como o cliente espera a resposta da tool, a chamada só sai no timeout.
"""

import ast
import json
import os
import sys
import time
from pathlib import Path

import anyio
import pytest
from _fakes import fake_bin

SRC = Path(__file__).resolve().parents[1] / "src" / "novomodelo_mcp"
CHAMADAS = {"run", "Popen", "check_output", "check_call", "call"}


def _chamadas_sem_stdin():
    faltando = []
    for arquivo in sorted(SRC.rglob("*.py")):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and isinstance(no.func.value, ast.Name)
                and no.func.value.id == "subprocess"
                and no.func.attr in CHAMADAS
                and not any(k.arg == "stdin" for k in no.keywords)
            ):
                faltando.append(f"{arquivo.relative_to(SRC)}:{no.lineno}")
    return faltando


def test_todo_subprocesso_define_o_stdin():
    assert _chamadas_sem_stdin() == []


def test_bridge_responde_pelo_servidor_aberto_por_um_cliente_mcp(tmp_path):
    mcp = pytest.importorskip("mcp")
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def chamar():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from novomodelo_mcp.server import main; main()"],
            env={
                **os.environ,
                "NOVOMODELO_MCP_BRIDGE_BIN": fake_bin("fake_novomodelo_bridge.py"),
                "NOVOMODELO_MCP_WORKSPACE": str(tmp_path),
                "NOVOMODELO_MCP_TIMEOUT": "30",
            },
        )
        async with stdio_client(params) as (r, w), mcp.ClientSession(r, w) as sessao:
            await sessao.initialize()
            inicio = time.monotonic()
            res = await sessao.call_tool("bridge_check_newave", {"src": str(tmp_path)})
            return json.loads(res.content[0].text), time.monotonic() - inicio

    async def com_limite():
        with anyio.fail_after(120):
            return await chamar()

    env, duracao = anyio.run(com_limite)
    assert env["exit_code"] == 0, env
    assert duracao < 20
