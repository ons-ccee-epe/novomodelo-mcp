"""Prompt `metodologia` e descrição do `docs_search` que leva o agente às docs."""
import anyio

from novomodelo_mcp.server import build_server


def _prompt_text(server, args):
    result = anyio.run(lambda: server.get_prompt("metodologia", args))
    return " ".join(m.content.text for m in result.messages)


def test_prompt_metodologia_listado_com_tema_opcional():
    server = build_server()
    prompts = {p.name: p for p in anyio.run(server.list_prompts)}
    assert "metodologia" in prompts
    args = {a.name: a for a in prompts["metodologia"].arguments or []}
    assert "tema" in args and args["tema"].required is False


def test_texto_do_prompt_ancorado_nas_docs():
    texto = _prompt_text(build_server(), {"tema": "CVaR"})
    for trecho in ("CVaR", "docs_search", "em inglês", "glossário", "docs_read",
                   "pagina#secao", "não complete de memória", "o código pode divergir"):
        assert trecho in texto, trecho


def test_prompt_sem_tema_pede_a_pergunta():
    texto = _prompt_text(build_server(), {})
    assert "próxima mensagem" in texto and "docs_search" in texto


def test_descricao_do_docs_search_dispara_a_busca():
    tools = {t.name: t for t in build_server()._tool_manager.list_tools()}
    desc = tools["docs_search"].description
    assert "Use sempre que a pergunta for sobre como o novomodelo modela" in desc
    for termo in ("CVaR", "PAR(p)", "FPHA", "SDDP", "Benders", "FCF", "afluência",
                  "árvore de aberturas", "valor da água", "EARM"):
        assert termo in desc, termo
