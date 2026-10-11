"""Tools de referência (read-only): JSON Schemas de entrada e documentação.

Também registra o resource `novomodelo://schema/{tipo}` como afordância para o agente
consultar sem uma chamada de tool. Sem regra de negócio.
"""
from __future__ import annotations

import json

from ..adapters import reference as REF
from ..config import Settings
from ..names import URI_SCHEME
from .shaping import cap_envelope


def register_reference(mcp, settings: Settings) -> None:
    """Registra as tools de referência e o resource de schema no servidor `mcp`."""

    @mcp.tool()
    def schema_list() -> dict:
        """Lista os tipos de arquivo de deck que têm JSON Schema oficial disponível."""
        return {"status": "ok", "types": REF.list_schema_types(settings)}

    @mcp.tool()
    def schema_get(tipo: str) -> dict:
        """JSON Schema oficial de um tipo de arquivo do deck (ex.: hydros, config, penalties)."""
        return cap_envelope(REF.read_schema(settings, tipo), settings)

    @mcp.tool()
    def docs_list(section: str | None = None) -> dict:
        """Lista páginas da documentação do Cobre (opcional: filtra por seção, ex.: 'reference')."""
        return cap_envelope(REF.list_docs(settings, section), settings)

    @mcp.tool()
    def docs_read(page: str) -> dict:
        """Lê uma página da documentação, offline (ex.: 'reference/cli-reference')."""
        return cap_envelope(REF.read_doc(settings, page, settings.max_summary_chars), settings)

    # Afordância de resource (best-effort: não derruba o servidor se o cliente/SDK
    # não suportar templates de resource).
    try:
        @mcp.resource(f"{URI_SCHEME}://schema/{{tipo}}")
        def _schema_resource(tipo: str) -> str:  # pragma: no cover
            r = REF.read_schema(settings, tipo)
            return json.dumps(r.get("schema", r), ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass
