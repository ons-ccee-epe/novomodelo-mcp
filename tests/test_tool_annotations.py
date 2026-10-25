"""Toda tool declara se só lê ou se escreve (anotações MCP), e a classificação é a esperada.

Se uma tool nova for criada sem anotação, ou mudar de categoria sem querer,
este teste falha e obriga a decidir de forma explícita.
"""

import re
from pathlib import Path

from novomodelo_mcp.server import build_server
from novomodelo_mcp.tools.annotations import NETWORK_TOOLS

READ_ONLY = {
    "server_info", "solver_version", "schema_list", "schema_get", "docs_list", "docs_read",
    "docs_search",
    "deck_list", "deck_read_json", "deck_read_parquet", "deck_describe_parquet", "deck_sql",
    "case_validate", "case_summary", "bridge_check_newave", "bridge_check_decomp",
    "results_status", "results_convergence", "results_list_entities", "results_query",
    "results_stochastic", "results_policy",
    "run_plan", "run_status", "run_logs",
}
WRITES = {
    "case_init", "schema_export", "bridge_convert_newave", "bridge_convert_decomp",
    "bridge_compare_newave", "bridge_compare_decomp", "bridge_dashboard", "incluir_pastas",
}
DESTRUCTIVE = {"deck_edit_json", "deck_edit_parquet", "run_apply", "run_start", "run_cancel",
               "instalar_novomodelo"}


def _tools():
    return {t.name: t for t in build_server()._tool_manager.list_tools()}


def test_toda_tool_tem_anotacao():
    sem = sorted(name for name, t in _tools().items() if t.annotations is None)
    assert not sem, f"tools sem anotação: {sem}"


def test_tools_com_rede_sao_as_declaradas():
    com_rede = {name for name, t in _tools().items() if t.annotations.openWorldHint}
    assert com_rede == NETWORK_TOOLS == {"server_info", "instalar_novomodelo"}


def test_classificacao_abrange_todas_as_tools():
    assert set(_tools()) == READ_ONLY | WRITES | DESTRUCTIVE


def test_leitura_escrita_e_destrutivas():
    for name, t in _tools().items():
        a = t.annotations
        assert a.openWorldHint is (name in NETWORK_TOOLS), name
        if name in READ_ONLY:
            assert a.readOnlyHint is True, name
        else:
            assert a.readOnlyHint is False, name
            assert a.destructiveHint is (name in DESTRUCTIVE), name


README = Path(__file__).resolve().parents[1] / "README.md"
_ROW = re.compile(r"^\| (Só leitura|Escreve arquivos novos|Altera ou interrompe) \| (.+) \|$")


def _secao(titulo: str) -> str:
    texto = README.read_text(encoding="utf-8")
    inicio = texto.index(f"\n## {titulo}")
    fim = texto.find("\n## ", inicio + 1)
    return texto[inicio:fim if fim != -1 else None]


def test_tabela_de_leitura_e_escrita_do_readme_bate_com_o_servidor():
    tabela = {}
    for linha in _secao("Leitura × escrita").splitlines():
        if m := _ROW.match(linha):
            tabela[m.group(1)] = set(re.findall(r"`([a-z_]+)`", m.group(2)))
    tools = _tools()
    leitura = {n for n, t in tools.items() if t.annotations.readOnlyHint}
    destrutivas = {n for n, t in tools.items() if t.annotations.destructiveHint}
    assert tabela == {"Só leitura": leitura,
                      "Escreve arquivos novos": set(tools) - leitura - destrutivas,
                      "Altera ou interrompe": destrutivas}


def test_readme_nao_congela_contagem_nem_lista_de_liberacao():
    texto = README.read_text(encoding="utf-8")
    assert not re.search(r"\| (Só leitura|Escreve arquivos novos|Altera ou interrompe) \(\d+\)",
                         texto)
    assert not re.search(r'"mcp__novomodelo__\w+"', texto) and '"autoApprove": [' not in texto
    assert not re.search(r"\b\d+ (tools|ferramentas)\b", texto)


def test_lista_de_ferramentas_do_readme_bate_com_o_servidor():
    citadas = set(re.findall(r"(?:^- |· | / )`([a-z_]+)", _secao("Ferramentas"), re.MULTILINE))
    assert citadas == set(_tools())
