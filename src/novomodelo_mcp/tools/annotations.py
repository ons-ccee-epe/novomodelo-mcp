"""Anotações MCP de cada tool: leitura × escrita (spec MCP, `ToolAnnotations`).

O cliente (Claude Desktop, Claude Code, Kiro…) pode usar essas dicas para decidir
quando pedir aprovação. São DICAS, não garantias: quem decide é o cliente e a
política da organização. Só as tools de `NETWORK_TOOLS` falam com a rede
(`openWorldHint=True`); as demais são locais.

Toda tool nova precisa usar uma das três constantes; o teste
`tests/test_tool_annotations.py` falha se alguma ficar sem classificação.
"""
from __future__ import annotations

try:
    from mcp.types import ToolAnnotations
except ImportError:  # smoke com Python puro (sem o pacote mcp): as dicas viram dict simples
    def ToolAnnotations(**hints):
        return hints

#: Só lê: não altera nenhum arquivo do usuário. Pode gravar cache ou estado
#: interno do próprio MCP (ex.: calibração em state_dir, schemas em /tmp).
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

#: Só lê, e consulta a rede (domínios oficiais; sem rede, devolve aviso).
READ_ONLY_NET = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

#: Tools que usam a rede: o teste de anotações confere que são exatamente as de
#: `openWorldHint=True`.
NETWORK_TOOLS = frozenset({"server_info", "instalar_novomodelo"})

#: Grava arquivos novos (deck convertido, relatório, dashboard, caso de template)
#: sem apagar dados existentes; sobrescrever exige `force`, que é controlado.
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

#: Altera ou substitui dados existentes, ou interrompe processos (edição de deck
#: com backup, run que grava sobre `output/`, cancelamento de run).
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

#: Destrutiva e com rede: baixa e executa o instalador oficial.
DESTRUCTIVE_NET = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
