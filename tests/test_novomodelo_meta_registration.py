"""Testes de registro no servidor e de forma do envelope de erro (pytest).

Dois contratos distintos:

- **Registro**: construir o servidor real via `build_server()` e afirmar que
  `solver_version` e `schema_export` aparecem entre as tools registradas,
  provando que `register_novomodelo_meta` está ligado ao bootstrap padrão.
- **Forma do envelope de erro**: nos casos de erro, afirmar as chaves
  `status` / `exit_code` / `diagnostics` do contrato único de `Error_Envelope`,
  provando que o resultado veio dos construtores do owner (`error` / `as_error`
  em `adapters/envelope.py`) e não de um dicionário montado à mão.

Offline por contrato: `build_server()` não fala com a rede e os casos de erro
são alcançados sem o binário `novomodelo` real (binário ausente ⇒ `error(127, ...)`;
adaptador que levanta ⇒ `as_error(exc)`).
"""

import novomodelo_mcp.tools.novomodelo_meta as novomodelo_meta
from novomodelo_mcp.adapters.envelope import as_error, error
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.server import build_server
from novomodelo_mcp.tools.novomodelo_meta import register_novomodelo_meta


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


def _registered_tool_names():
    """Nomes das tools no servidor real; `_tool_manager.list_tools()` é síncrono."""
    server = build_server()
    return {tool.name for tool in server._tool_manager.list_tools()}


def _meta_tool(name, settings):
    mcp = _CaptureMCP()
    register_novomodelo_meta(mcp, settings)
    return mcp.tools[name]


def test_build_server_registers_solver_version():
    assert "solver_version" in _registered_tool_names()


def test_build_server_registers_schema_export():
    assert "schema_export" in _registered_tool_names()


def _assert_error_envelope_shape(env):
    """Afirma a tripla canônica do owner: status/exit_code/diagnostics."""
    assert env["status"] == "error"
    assert isinstance(env["exit_code"], int)
    assert isinstance(env["diagnostics"], list) and env["diagnostics"]


def test_error_constructor_shape_is_the_contract():
    """Fixa a forma produzida pelos construtores do owner (`error` / `as_error`)."""
    _assert_error_envelope_shape(error(127, "novomodelo não encontrado"))
    _assert_error_envelope_shape(as_error(RuntimeError("boom")))


def test_version_missing_binary_envelope_came_from_owner(monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_SOLVER_BIN", raising=False)
    monkeypatch.setattr("novomodelo_mcp.adapters.novomodelo.find_novomodelo", lambda settings: None)
    env = _meta_tool("solver_version", load_settings())()
    _assert_error_envelope_shape(env)
    assert env["exit_code"] == 127


def test_schema_export_missing_binary_envelope_came_from_owner(monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_SOLVER_BIN", raising=False)
    monkeypatch.setattr("novomodelo_mcp.adapters.novomodelo.find_novomodelo", lambda settings: None)
    env = _meta_tool("schema_export", load_settings())()
    _assert_error_envelope_shape(env)
    assert env["exit_code"] == 127


def test_version_adapter_exception_maps_to_as_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("falha de transporte simulada")

    monkeypatch.setattr(novomodelo_meta, "version_cli", boom)
    env = _meta_tool("solver_version", load_settings())()
    _assert_error_envelope_shape(env)


def test_schema_export_adapter_exception_maps_to_as_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("falha de transporte simulada")

    monkeypatch.setattr(novomodelo_meta, "run_novomodelo", boom)
    env = _meta_tool("schema_export", load_settings())()
    _assert_error_envelope_shape(env)
