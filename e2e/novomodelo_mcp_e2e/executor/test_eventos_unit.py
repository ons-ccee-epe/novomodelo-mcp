"""Leitura dos streams do Claude Code e do Kiro CLI em eventos normalizados."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novomodelo_mcp_e2e.executor.eventos import ler_claude, ler_kiro

FIX = Path(__file__).parent / "fixtures"


def _wrap(objs):
    return [json.dumps({"t": float(i), "evento": o}) for i, o in enumerate(objs)]


def _linhas(nome: str) -> list[str]:
    return (FIX / nome).read_text(encoding="utf-8").splitlines()


def test_le_o_stream_do_claude():
    leitura = ler_claude(_linhas("claude-stream-sintetico.jsonl"))
    nomes = [e.nome for e in leitura.eventos if e.tipo == "tool"]
    assert nomes == ["server_info", "Bash", "case_validate"]
    assert next(e for e in leitura.eventos if e.nome == "server_info" and e.tipo == "tool").do_mcp
    assert not next(e for e in leitura.eventos if e.nome == "Bash").do_mcp
    resultados = [(e.nome, e.erro) for e in leitura.eventos if e.tipo == "resultado_tool"]
    assert resultados == [("server_info", False), ("Bash", False), ("case_validate", False)]
    fim = leitura.eventos[-1]
    assert fim.tipo == "fim" and fim.dados["tokens_saida"] > 0
    assert fim.dados["tokens_entrada"] == 60 and fim.dados["duracao_s"] == 4.2


def test_permission_denials_viram_negacao():
    linhas = _wrap(
        [
            {
                "type": "result",
                "result": "ok",
                "usage": {},
                "permission_denials": [
                    {"tool_name": "mcp__novomodelo__case_validate", "tool_input": {}}
                ],
            }
        ]
    )
    [neg, _] = ler_claude(linhas).eventos
    assert neg.tipo == "negacao" and neg.nome == "case_validate" and neg.do_mcp


def test_linha_corrompida_e_ignorada_e_contada():
    leitura = ler_claude(["{quebrado", *_wrap([{"type": "result", "result": "", "usage": {}}])])
    assert leitura.linhas_invalidas == 1 and leitura.eventos[-1].tipo == "fim"


def test_negacao_do_system_conta_uma_vez_e_message_texto_nao_quebra():
    linhas = _wrap(
        [
            {
                "type": "system",
                "subtype": "permission_denied",
                "tool_name": "Bash",
                "tool_use_id": "b1",
                "message": "This command requires approval",
            },
            {
                "type": "result",
                "result": "ok",
                "usage": {},
                "permission_denials": [
                    {"tool_name": "Bash", "tool_use_id": "b1", "tool_input": {}}
                ],
            },
        ]
    )
    ev = ler_claude(linhas).eventos
    assert [e.tipo for e in ev] == ["negacao", "fim"]


def test_le_as_tools_nativas_do_kiro_com_o_nome_do_claude():
    ev = ler_kiro(_linhas("kiro-stream-sintetico.jsonl")).eventos
    nativas = [e for e in ev if e.tipo == "tool" and not e.do_mcp]
    assert [e.nome for e in nativas] == ["Kiro Powers", "Grep", "Read"]
    assert ev[-1].tipo == "fim" and "server_info" in ev[-1].dados["resposta"]


def _u(update):
    return json.dumps({"type": "sessionUpdate", "data": {"update": update}})


def test_le_chamada_de_tool_mcp_e_tempo_monotono():
    linhas = [
        json.dumps(
            {
                "t": 1.0,
                "evento": json.loads(
                    _u(
                        {
                            "sessionUpdate": "tool_call",
                            "toolCallId": "a",
                            "title": "server_info",
                            "_meta": {"kiro": {"toolOrigin": "novomodelo"}},
                        }
                    )
                ),
            }
        ),
        json.dumps(
            {
                "t": 2.0,
                "evento": json.loads(
                    _u(
                        {
                            "sessionUpdate": "tool_call_update",
                            "toolCallId": "a",
                            "status": "completed",
                            "content": [],
                        }
                    )
                ),
            }
        ),
        json.dumps(
            {
                "t": 3.0,
                "evento": {"type": "runFinished", "data": {"status": "success", "finalText": "ok"}},
            }
        ),
    ]
    ev = ler_kiro(linhas).eventos
    assert ev[0].nome == "server_info" and ev[0].do_mcp and ev[0].t == 1.0
    assert [e.t for e in ev] == sorted(e.t for e in ev)


def test_kiro_mcp_pelo_meta_e_aprovacao_negada_vira_negacao():
    ev = ler_kiro(_linhas("kiro-stream-sintetico.jsonl")).eventos
    tools = [e for e in ev if e.tipo == "tool"]
    assert [(e.nome, e.do_mcp) for e in tools] == [
        ("Kiro Powers", False),
        ("Grep", False),
        ("server_info", True),
        ("Read", False),
        ("solver_version", True),
        ("case_validate", True),
    ]
    negadas = [e.nome for e in ev if e.tipo == "negacao"]
    assert negadas == ["server_info", "case_validate"]
    assert not [e for e in ev if e.tipo == "resultado_tool" and e.do_mcp and e.erro]


def test_kiro_atual_le_o_resultado_de_rawoutput_com_o_id_da_chamada():
    ev = ler_kiro(_linhas("kiro-stream-sintetico-2.jsonl")).eventos
    resultados = {e.dados["id"]: e for e in ev if e.tipo == "resultado_tool"}
    assert {i: e.nome for i, e in resultados.items()} == {
        "m1": "server_info",
        "m2": "case_validate",
        "m3": "deck_list",
    }
    assert json.loads(resultados["m1"].dados["conteudo"])["status"] == "ok"
    assert json.loads(resultados["m2"].dados["conteudo"])["status"] == "error"
    assert [resultados[i].erro for i in ("m1", "m2", "m3")] == [False, False, True]
    assert all(e.do_mcp for e in resultados.values())


def test_kiro_junta_os_itens_de_texto_e_ignora_os_de_outro_tipo():
    saida = {"items": [{"Json": {"content": [{"type": "text", "text": "a"}, {"type": "image"}]}}]}
    saida["items"].append({"Json": {"content": [{"type": "text", "text": "b"}], "isError": False}})
    update = {"sessionUpdate": "tool_call_update", "toolCallId": "x", "status": "completed"}
    linha = {"type": "sessionUpdate", "data": {"update": {**update, "rawOutput": saida}}}
    [resultado] = ler_kiro(_wrap([linha])).eventos
    assert resultado.dados["conteudo"] == "a\nb" and not resultado.erro


def test_kiro_negacao_vale_tambem_no_formato_de_rawoutput():
    texto = "Permission request failed: Internal error: approval is not supported"
    saida = {"items": [{"Json": {"content": [{"type": "text", "text": texto}], "isError": True}}]}
    update = {"sessionUpdate": "tool_call_update", "toolCallId": "x", "status": "failed"}
    linha = {"type": "sessionUpdate", "data": {"update": {**update, "rawOutput": saida}}}
    [evento] = ler_kiro(_wrap([linha])).eventos
    assert evento.tipo == "negacao"


def _resultado_com(**campos):
    update = {"sessionUpdate": "tool_call_update", "toolCallId": "x", "status": "completed"}
    linha = {"type": "sessionUpdate", "data": {"update": {**update, **campos}}}
    [evento] = ler_kiro(_wrap([linha])).eventos
    return evento


@pytest.mark.parametrize("bruto", ["texto", 7, ["a"], None, {}, {"items": []}, {"items": "x"}])
def test_kiro_rawoutput_fora_do_formato_cai_na_forma_antiga(bruto):
    antigo = [{"type": "content", "content": {"type": "text", "text": "antigo"}}]
    evento = _resultado_com(rawOutput=bruto, content=antigo)
    assert evento.dados["conteudo"] == "antigo" and not evento.erro


@pytest.mark.parametrize(
    "item",
    [
        {},
        {"Json": None},
        {"Json": "x"},
        {"Json": {"content": "x"}},
        {"Json": {"content": None}},
        "x",
    ],
)
def test_kiro_item_de_rawoutput_malformado_nao_derruba_a_leitura(item):
    evento = _resultado_com(rawOutput={"items": [item]})
    assert evento.tipo == "resultado_tool" and evento.dados["conteudo"] == ""


def test_kiro_dois_blocos_de_texto_sao_unidos_por_quebra_de_linha():
    blocos = [{"type": "text", "text": "um"}, {"type": "text", "text": "dois"}]
    evento = _resultado_com(rawOutput={"items": [{"Json": {"content": blocos}}]})
    assert evento.dados["conteudo"] == "um\ndois"
