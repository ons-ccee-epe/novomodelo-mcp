"""`docs_read` sem `page` devolve a lista de páginas (a do `docs_list`), em vez do erro
de validação do framework fora do envelope."""

import asyncio

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.reference import register_reference


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco

    def resource(self, *args, **kwargs):
        return lambda fn: fn


def _tools():
    mcp = _CaptureMCP()
    register_reference(mcp, load_settings())
    return mcp.tools


def test_sem_pagina_devolve_a_lista_de_paginas():
    t = _tools()
    sem = t["docs_read"]()
    assert sem["status"] == "ok" and sem["items"] == t["docs_list"]()["items"], sem
    assert "page" in sem["note"], sem


def test_no_servidor_page_nao_e_obrigatorio():
    from novomodelo_mcp.server import build_server

    srv = build_server()
    tools = asyncio.run(srv.list_tools())
    schema = next(x for x in tools if x.name == "docs_read").inputSchema
    assert "page" not in schema.get("required", []), schema
