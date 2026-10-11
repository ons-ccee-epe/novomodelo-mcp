"""Anotações MCP de cada tool: leitura × escrita (spec MCP, `ToolAnnotations`).

O cliente (Claude Desktop, Claude Code, Kiro…) pode usar essas dicas para decidir
quando pedir aprovação. São DICAS, não garantias: quem decide é o cliente e a
política da organização. Todas as tools são locais, então `openWorldHint=False`.

Toda tool nova precisa usar uma das três constantes; o teste
`tests/test_tool_annotations.py` falha se alguma ficar sem classificação.
"""
from __future__ import annotations

from mcp.types import ToolAnnotations

#: Só lê: não altera nenhum arquivo do usuário. Pode gravar cache ou estado
#: interno do próprio MCP (ex.: calibração em state_dir, schemas em /tmp).
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

#: Grava arquivos novos (deck convertido, relatório, dashboard, caso de template)
#: sem apagar dados existentes; sobrescrever exige `force`, que é controlado.
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

#: Altera ou substitui dados existentes, ou interrompe processos (edição de deck
#: com backup, run que grava sobre `output/`, cancelamento de run).
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)
