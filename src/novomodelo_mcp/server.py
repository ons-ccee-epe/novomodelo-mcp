"""Ponto de entrada do servidor MCP do Novomodelo (transporte stdio)."""
from __future__ import annotations

import asyncio
import functools

from mcp.server.fastmcp import FastMCP

from . import __version__

from .adapters import versions
from .adapters.envelope import as_error

from .adapters.discovery import bridge_origin, bridge_version, find_novomodelo, tool_version
from .adapters.paths import (AVISO_NA_TOOL, NAO_CONTORNE, allowed_roots, included_roots,
                             is_guarded_tool)
from .adapters.reference import docs_origin
from .adapters.state import state_dir
from .config import load_settings
from .names import SERVER_NAME
from .tools.novomodelo_meta import register_novomodelo_meta
from .tools.pastas import register_pastas
from .tools.deck import register_deck
from .tools.post_run import register_post_run
from .tools.prompts import register_prompts
from .tools.pre_run import register_pre_run
from .tools.reference import register_reference
from .tools.results import register_results
from .tools.run import register_run
from .tools.annotations import READ_ONLY_NET
from .tools.shaping import attach_version_warnings


SERVER_INSTRUCTIONS = f"""\
Servidor MCP do novomodelo: valida, converte (NEWAVE/DECOMP), roda, compara e lê os
resultados de casos, e responde sobre a metodologia pelas docs oficiais.

- Comece por `server_info`: versões das peças, workspace e se há versão nova.
- Se faltar o executável do novomodelo, ofereça a tool `instalar_novomodelo` (a pessoa
  pode pedir “instale o executável do novomodelo”); o comando manual é a alternativa.
- As docs embutidas são as oficiais da versão instalada. Para a metodologia e o uso do
  novomodelo, use `docs_search` antes de responder, e não a web nem a memória: a
  definição do novomodelo pode diferir da literatura e do NEWAVE.
- Busque em inglês (as docs estão em inglês); termos em português do glossário das
  docs são traduzidos. Depois leia a seção com `docs_read(page, secao)`.
- Toda resposta sobre metodologia cita a página e a seção (`pagina#secao`) de onde veio.
- Se as docs não cobrem o assunto, diga isso: não complete de memória.
- A rede só é usada para versões e para instalar o executável.
- Pedido sobre resultados de um caso (status, convergência, CMO, geração, política):
  vá direto às tools `results_*`. Se não souber a pasta da rodada, passe a do caso: a
  recusa traz a rodada encontrada em `output_sugerido`, ou, se houver várias, a lista
  em `rodadas` para o usuário escolher.
- Resultados de muitos cenários: agregue ou filtre com o `deck_sql` sobre as partições
  de `simulation/` e só depois detalhe; não leia os parquets por outras ferramentas.
- As tools que gravam ou alteram arquivos pedem aprovação.
- Com pasta de trabalho definida (`workspace` no `server_info`), as tools só leem e
  gravam dentro dela.
  {NAO_CONTORNE}
"""


_PROPAGAR = (KeyboardInterrupt, SystemExit, asyncio.CancelledError, GeneratorExit)


def _never_raise(fn):
    """A falha de uma tool vira envelope, inclusive `BaseException` de biblioteca nativa
    (o pânico do PyO3 não é `Exception` e derrubaria o stdio); só o que é do próprio
    processo (interrupção, saída, cancelamento) segue adiante."""
    @functools.wraps(fn)
    def guarded(*a, **k):
        try:
            return fn(*a, **k)
        except _PROPAGAR:
            raise
        except BaseException as exc:  # noqa: BLE001 - never-raise: envelope em vez de derrubar o servidor
            return as_error(exc)
    return guarded


class _WithVersionWarnings:
    """`mcp` cujo `.tool()` faz toda resposta levar `avisos_de_versao` quando houver,
    e põe `AVISO_NA_TOOL` na descrição de toda tool guardada (`is_guarded_tool`).

    Embrulhar no registro, e não no `cap_envelope`: parte das tools não passa por ele.
    """

    def __init__(self, mcp: FastMCP, settings) -> None:
        self._mcp, self._settings = mcp, settings

    def __getattr__(self, name):
        return getattr(self._mcp, name)

    def tool(self, *args, **kwargs):
        register = self._mcp.tool(*args, **kwargs)

        def deco(fn):
            guarded = _never_raise(fn)

            @functools.wraps(fn)
            def with_warnings(*a, **k):
                result = guarded(*a, **k)
                try:
                    warnings = versions.version_warnings(self._settings)
                except Exception:  # noqa: BLE001 - never-raise: o aviso é extra, não pode derrubar a tool
                    warnings = []
                return attach_version_warnings(result, warnings)

            with_warnings._avisos_de_versao = True
            if is_guarded_tool(fn):
                with_warnings.__doc__ = f"{(fn.__doc__ or '').rstrip()}\n\n{AVISO_NA_TOOL}"
            return register(with_warnings)

        return deco


def build_server() -> FastMCP:
    """Constrói e configura o servidor com todas as ferramentas registradas."""
    settings = load_settings()
    server = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    # O FastMCP não recebe versão: sem isto o `initialize` anuncia a do SDK `mcp`.
    server._mcp_server.version = __version__
    mcp = _WithVersionWarnings(server, settings)

    register_pre_run(mcp, settings)     # pré-rodada: check / convert / validate
    register_post_run(mcp, settings)    # pós-rodada: compare_* / dashboard
    register_deck(mcp, settings)        # manipulador de decks (JSON/Parquet)
    register_results(mcp, settings)     # leitura/análise de resultados (pós-rodada)
    register_reference(mcp, settings)   # schemas + documentação (referência)
    register_novomodelo_meta(mcp, settings)  # meta do novomodelo: version + schema export
    register_run(mcp, settings)         # init / plano / apply / run assíncrono
    register_prompts(mcp, settings)     # prompts: metodologia
    register_pastas(mcp, settings)      # inclusão de pastas de estudo no guard

    @mcp.tool(annotations=READ_ONLY_NET)
    def server_info() -> dict:
        """Diagnóstico do próprio MCP: binários, versões e se há versão nova.

        `versoes`: executável, biblioteca, bridge e docs, com a versão esperada.
        `versao_nova`: consulta, no máximo a cada 6 horas e em até alguns segundos, os
        releases do novomodelo e do bridge (domínios oficiais); sem rede, diz que
        não foi possível verificar e mostra onde conferir.
        """
        bridge, bridge_from = bridge_origin(settings)
        novomodelo = find_novomodelo(settings)
        try:
            pieces = versions.local_versions(settings)
            newer = versions.update_check(settings)
        except Exception as exc:  # noqa: BLE001 - never-raise: diagnóstico parcial em vez de derrubar
            pieces, newer = {"erro": str(exc)}, {"erro": str(exc)}
        return {
            "server": f"{SERVER_NAME}-mcp",
            "versao_mcp": __version__,
            "versoes": {**pieces, "esperada": versions.expected_version()},
            "versao_nova": newer,
            "bridge": {"path": bridge, "version": bridge_version(bridge, bridge_from),
                       "available": bridge is not None, "origem": bridge_from},
            "novomodelo": {"path": novomodelo, "version": tool_version(novomodelo),
                      "available": novomodelo is not None},
            "schemas_dir": settings.schemas_dir,
            "docs": docs_origin(settings),
            "workspace": [str(r) for r in allowed_roots(settings)] or "irrestrito (defina NOVOMODELO_MCP_WORKSPACE)",
            "pastas_incluidas": [str(r) for r in included_roots(settings)],
            "allow_force": settings.allow_force,
            "state_dir": str(state_dir(settings)),
            "max_jobs": settings.max_jobs,
            "settings": {
                "default_timeout": settings.default_timeout,
                "max_diagnostics": settings.max_diagnostics,
                "max_summary_chars": settings.max_summary_chars,
                "max_response_kb": settings.max_response_kb,
            },
        }

    return server


def main() -> None:
    """Executável `novomodelo-mcp`: sobe o servidor no stdio; `configurar` grava o cliente."""
    import sys
    if sys.argv[1:2] == ["configurar"]:
        from .client_config import main as configure
        raise SystemExit(configure(sys.argv[2:]))
    build_server().run()


if __name__ == "__main__":
    main()
