"""Importa todos os submódulos do pacote — pega import quebrado em qualquer arquivo.

É o gate que teria pego o bug recorrente `from .config` -> `..config` na hora,
sem depender de rodar o smoke certo. Requer as deps instaladas (mcp etc.), o que
o CI garante via `uv sync`.
"""

import importlib
import pkgutil

import novomodelo_mcp


def test_all_submodules_import():
    for mod in pkgutil.walk_packages(novomodelo_mcp.__path__, novomodelo_mcp.__name__ + "."):
        importlib.import_module(mod.name)


def test_servidor_expoe_instructions_em_portugues():
    from novomodelo_mcp.server import build_server

    server = build_server()
    texto = server.instructions or ""
    enviado = server._mcp_server.create_initialization_options().instructions
    assert texto and enviado == texto
    for trecho in (
        "server_info",
        "docs_search",
        "em inglês",
        "página e a seção",
        "não complete de memória",
        "aprovação",
    ):
        assert trecho in texto, trecho
