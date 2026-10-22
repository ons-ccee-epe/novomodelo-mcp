"""A versão e os autores do pacote vêm de um lugar só: os metadados instalados.

O `initialize` mostra a versão do MCP (sem isso o FastMCP manda a do SDK `mcp`), e o
`server_info` e o `__version__` repetem a mesma.
"""
import tomllib
from importlib import metadata
from pathlib import Path

import novomodelo_mcp
from novomodelo_mcp.adapters import versions
from novomodelo_mcp.names import BINDING_DIST, BRIDGE_DIST, MCP_DIST
from novomodelo_mcp.server import build_server

PYPROJECT = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml")
                          .read_text(encoding="utf-8"))["project"]


def test_versao_instalada_e_a_do_pyproject_e_a_do_modulo():
    assert metadata.version(MCP_DIST) == PYPROJECT["version"] == novomodelo_mcp.__version__


def test_initialize_mostra_a_versao_do_mcp_e_nao_a_do_sdk():
    options = build_server()._mcp_server.create_initialization_options()
    assert options.server_version == PYPROJECT["version"]
    assert options.server_version != metadata.version("mcp")


def test_server_info_mostra_a_versao_do_mcp(monkeypatch):
    monkeypatch.setattr(versions, "update_check", lambda settings: {"mcp": {"status": "atual"}})
    tools = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}
    assert tools["server_info"]()["versao_mcp"] == PYPROJECT["version"]


def test_versao_do_mcp_acompanha_a_do_novomodelo():
    base = PYPROJECT["version"].split(".post")[0]
    assert base == versions.expected_version()


def test_pin_exato_so_no_bridge_e_a_biblioteca_instalada_e_a_mesma():
    deps = PYPROJECT["dependencies"]
    assert f"{BRIDGE_DIST}=={versions.expected_version()}" in deps
    assert BINDING_DIST in deps, "a biblioteca fica sem pin: o bridge fixa a versão dela"
    assert metadata.version(BINDING_DIST) == metadata.version(BRIDGE_DIST)


def test_autores_sao_os_tres_mantenedores_do_novomodelo():
    meta = metadata.metadata(MCP_DIST)
    autores = meta.get("Author-email", "") + meta.get("Author", "")
    for nome in ("Operador Nacional do Sistema Elétrico - ONS",
                 "Câmara de Comercialização de Energia Elétrica - CCEE",
                 "Empresa de Pesquisa Energética - EPE"):
        assert nome in autores, nome
    assert meta.get("License-Expression") == "Apache-2.0"
