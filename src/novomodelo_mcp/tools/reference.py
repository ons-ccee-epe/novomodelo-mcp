"""Tools de referência (read-only): JSON Schemas de entrada e documentação.

Também registra o resource `novomodelo://schema/{tipo}` como afordância para o agente
consultar sem uma chamada de tool. Sem regra de negócio.
"""

from __future__ import annotations

import json

from ..adapters import reference as REF
from ..config import Settings
from ..names import URI_SCHEME
from .annotations import READ_ONLY
from .shaping import cap_envelope


def register_reference(mcp, settings: Settings) -> None:
    """Registra as tools de referência e o resource de schema no servidor `mcp`."""

    @mcp.tool(annotations=READ_ONLY)
    def schema_list() -> dict:
        """Lista os tipos de arquivo de deck que têm JSON Schema oficial disponível."""
        return {"status": "ok", "types": REF.list_schema_types(settings)}

    @mcp.tool(annotations=READ_ONLY)
    def schema_get(tipo: str) -> dict:
        """JSON Schema oficial de um tipo de arquivo do deck (ex.: hydros, config, penalties)."""
        return cap_envelope(REF.read_schema(settings, tipo), settings)

    @mcp.tool(annotations=READ_ONLY)
    def docs_list(section: str | None = None) -> dict:
        """Páginas das docs embutidas, com título e descrição (opcional: filtra por prefixo,
        ex.: 'reference')."""
        return cap_envelope(REF.list_docs(settings, section), settings)

    @mcp.tool(annotations=READ_ONLY)
    def docs_search(consulta: str, k: int = 5) -> dict:
        """Busca nas docs embutidas do novomodelo (as da versão instalada) por palavra.

        Use sempre que a pergunta for sobre como o novomodelo modela, calcula ou
        configura algo: a definição dele pode diferir da literatura e do NEWAVE.
        Ex.: CVaR, PAR(p), FPHA, SDDP, cortes de Benders, FCF, afluência,
        árvore de aberturas, valor da água, EARM. Busque em inglês: as docs estão em
        inglês, e os termos em português que estão no glossário das docs são traduzidos
        (ex.: afluência → inflow). Devolve as `k` seções mais relevantes (até 20):
        `page`, `section` (âncora), `title`, `snippet` e `score`. Abra a seção com
        `docs_read(page, secao)`.
        """
        return cap_envelope(REF.search_docs(settings, consulta, k), settings)

    @mcp.tool(annotations=READ_ONLY)
    def docs_read(page: str | None = None, secao: str | None = None) -> dict:
        """Lê uma página das docs embutidas (ex.: 'reference/cli-reference').

        `secao`: âncora (a `section` que o docs_search devolve) ou título; devolve só a
        seção, com as subseções. Seção inexistente → erro com a lista de seções.
        Sem `page`: a lista de páginas, como o docs_list.
        """
        if not page:
            return {
                **cap_envelope(REF.list_docs(settings, None), settings),
                "note": "faltou `page`: escolha uma das páginas abaixo e chame docs_read(page, secao)",
            }
        return cap_envelope(
            REF.read_doc(settings, page, settings.max_summary_chars, secao), settings
        )

    # Afordância de resource (best-effort: não derruba o servidor se o cliente/SDK
    # não suportar templates de resource).
    try:

        @mcp.resource(f"{URI_SCHEME}://schema/{{tipo}}")
        def _schema_resource(tipo: str) -> str:  # pragma: no cover
            r = REF.read_schema(settings, tipo)
            return json.dumps(r.get("schema", r), ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass
