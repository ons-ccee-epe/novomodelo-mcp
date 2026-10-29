"""As tools respondem só em texto: sem `outputSchema`, o FastMCP não manda `structuredContent`.

O `-> dict[str, Any]` das tools pediria saída estruturada, e a resposta iria duas vezes
ao cliente, cada cópia do tamanho que o `cap_envelope` permite.
"""

from novomodelo_mcp.server import build_server


def test_nenhuma_tool_declara_output_schema():
    tools = build_server()._tool_manager.list_tools()
    com_schema = sorted(t.name for t in tools if t.output_schema is not None)
    assert not com_schema, f"tools com saída estruturada: {com_schema}"
