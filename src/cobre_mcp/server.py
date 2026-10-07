"""Ponto de entrada do servidor MCP do Cobre (transporte stdio, offline)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .adapters.discovery import find_bridge, find_cobre, tool_version
from .adapters.paths import allowed_roots
from .adapters.reference import docs_root
from .adapters.state import state_dir
from .config import load_settings
from .tools.deck import register_deck
from .tools.post_run import register_post_run
from .tools.pre_run import register_pre_run
from .tools.reference import register_reference
from .tools.results import register_results
from .tools.run import register_run


def build_server() -> FastMCP:
    """Constrói e configura o servidor com todas as ferramentas registradas."""
    settings = load_settings()
    mcp = FastMCP("cobre")

    register_pre_run(mcp, settings)     # pré-rodada: check / convert / validate
    register_post_run(mcp, settings)    # pós-rodada: compare_* / dashboard
    register_deck(mcp, settings)        # manipulador de decks (JSON/Parquet)
    register_results(mcp, settings)     # leitura/análise de resultados (pós-rodada)
    register_reference(mcp, settings)   # schemas + documentação (referência)
    register_run(mcp, settings)         # init / plano / apply / run assíncrono

    @mcp.tool()
    def cobre_mcp_info() -> dict:
        """Diagnóstico do próprio MCP: binários descobertos e suas versões."""
        bridge = find_bridge(settings)
        cobre = find_cobre(settings)
        return {
            "server": "cobre-mcp",
            "bridge": {"path": bridge, "version": tool_version(bridge),
                       "available": bridge is not None},
            "cobre": {"path": cobre, "version": tool_version(cobre),
                      "available": cobre is not None},
            "schemas_dir": settings.schemas_dir,
            "docs_dir": docs_root(settings),
            "workspace": [str(r) for r in allowed_roots(settings)] or "irrestrito (defina COBRE_MCP_WORKSPACE)",
            "allow_force": settings.allow_force,
            "state_dir": str(state_dir(settings)),
            "max_jobs": settings.max_jobs,
            "settings": {
                "default_timeout": settings.default_timeout,
                "max_diagnostics": settings.max_diagnostics,
                "max_summary_chars": settings.max_summary_chars,
                "max_inline_rows": settings.max_inline_rows,
                "max_query_rows": settings.max_query_rows,
            },
        }

    return mcp


def main() -> None:
    """Executável `cobre-mcp`: sobe o servidor no transporte stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
