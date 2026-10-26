"""Nomes dos programas externos que o MCP chama, declarados num lugar só.

Mesmo espírito do `SOFTWARE_NAME` do solver (`novomodelo-io/src/output/software.rs`):
evita repetir a mesma string em vários módulos. Não é mecanismo de rename — o
rename do produto é feito pela ferramenta `rebrand.py` + `map.toml`, que
reescreve este arquivo junto com o resto do repositório.
"""
from __future__ import annotations

#: Nome do servidor MCP (o cliente prefixa as tools com ele: `mcp__<nome>__<tool>`).
SERVER_NAME = "novomodelo"
#: Esquema dos URIs de resource (ex.: `novomodelo://schema/hydros`).
URI_SCHEME = "novomodelo"
#: Executável do solver (CLI Rust).
SOLVER_CLI = "novomodelo"
#: Executável do conversor/comparador NEWAVE/DECOMP.
BRIDGE_CLI = "novomodelo-bridge"
#: Distribuição (PyPI) dos bindings — o que `importlib.metadata.version` consulta.
BINDING_DIST = "novomodelo-python"
#: Distribuição (PyPI) do bridge — a única com pin exato no MCP; ela fixa a dos bindings.
BRIDGE_DIST = "novomodelo-bridge"
#: Prefixo de todas as variáveis de ambiente do MCP.
ENV_PREFIX = "NOVOMODELO_MCP_"
#: Distribuição do próprio MCP (metadados: versão e pin da biblioteca).
MCP_DIST = "novomodelo-mcp"
#: Base do link do release do MCP, completada com `v<versão>` no aviso de versão nova.
MCP_RELEASE_TAG_URL = "https://github.com/<organização interna>/novomodelo-mcp/releases/tag/"
