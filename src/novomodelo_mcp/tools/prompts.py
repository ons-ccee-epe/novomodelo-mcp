"""Prompts MCP: conversas que o cliente oferece como comando, já ancoradas nas docs.

No Claude Code o prompt aparece como `/novomodelo:metodologia`; os argumentos vão
separados por espaço, por isso `tema` é opcional e de uma palavra.
"""

from __future__ import annotations

from ..config import Settings

_METODOLOGIA = """\
Responda sobre a metodologia do novomodelo usando as docs oficiais embutidas no MCP
novomodelo, que são as da versão instalada.

1. Busque com `docs_search`, em inglês (as docs estão em inglês). Para termos em
   português, use o equivalente do glossário das docs (`reference/glossary`); a busca
   também traduz os termos que estão nele.
2. Leia as seções relevantes com `docs_read(page, secao)`.
3. Responda em português, citando página e seção de cada afirmação (`pagina#secao`).
4. Se as docs não tratam do assunto, diga isso claramente: não complete de memória.
5. Avise que as docs descrevem a intenção do modelo e que o código pode divergir delas
   (há divergências conhecidas, como no tratamento da afluência negativa).
"""


def metodologia_text(tema: str | None = None) -> str:
    if tema and tema.strip():
        return f"Tema: {tema.strip()}\n\n{_METODOLOGIA}"
    return (
        f"{_METODOLOGIA}\nA pergunta vem na próxima mensagem: espere por ela e siga os "
        "passos acima, começando por `docs_search`."
    )


def register_prompts(mcp, settings: Settings) -> None:
    """Registra os prompts MCP no servidor `mcp`."""

    @mcp.prompt(
        name="metodologia",
        description="Conversar sobre a metodologia do novomodelo com base nas docs "
        "oficiais, citando página e seção. `tema` (opcional, uma palavra, "
        "ex.: CVaR): sem ele, a pergunta vem na mensagem seguinte.",
    )
    def metodologia(tema: str | None = None) -> str:
        return metodologia_text(tema)
