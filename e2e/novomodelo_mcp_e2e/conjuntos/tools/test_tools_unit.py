"""Conjunto tools pelo executor: casos públicos, envelope tirado do stream e validador."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import anyio
import pytest

from novomodelo_mcp_e2e.config import Config
from novomodelo_mcp_e2e.conjuntos.tools.adaptador import (
    CASES_PATH,
    avaliar_tools,
    carregar_casos,
    caso_logico,
    para_execucoes,
    para_query_result,
    tools_a_liberar,
)
from novomodelo_mcp_e2e.executor.casos import PUBLICOS
from novomodelo_mcp_e2e.executor.eventos import Leitura, ler_claude, ler_kiro
from novomodelo_mcp_e2e.executor.imagens import ConfigMCP, tag_imagem
from novomodelo_mcp_e2e.queries.loader import CasesLoader, CasesLoaderError
from novomodelo_mcp_e2e.queries.models import ExpectedResult, QueryResult, QueryTestCase
from novomodelo_mcp_e2e.queries.validator import MCP_TOOLS, QueryValidator

PREFIXO = "mcp__novomodelo__"
FIX = Path(__file__).resolve().parents[2] / "executor" / "fixtures"


def _caso(**expected) -> QueryTestCase:
    return QueryTestCase(
        id="c",
        query="Liste o caso {caso:exemplo_1dtoy}",
        expected=ExpectedResult(uses_mcp=True, **expected),
    )


def _claude(*chamadas: tuple, resposta: str = "feito") -> Leitura:
    """Stream do Claude: cada chamada é (nome, envelope[, argumentos]); envelope `None`
    deixa a chamada sem resultado."""
    linhas, t = [], 0.0
    for i, (nome, envelope, *args) in enumerate(chamadas):
        t += 1.0
        uso = {"type": "tool_use", "id": f"t{i}", "name": nome, "input": args[0] if args else {}}
        linhas.append({"t": t, "evento": {"type": "assistant", "message": {"content": [uso]}}})
        if envelope is not None:
            t += 0.5
            bloco = {
                "type": "tool_result",
                "tool_use_id": f"t{i}",
                "content": [{"type": "text", "text": json.dumps(envelope)}],
            }
            linhas.append({"t": t, "evento": {"type": "user", "message": {"content": [bloco]}}})
    t += 1.0
    fim = {"type": "result", "result": resposta, "usage": {}, "duration_ms": 1000}
    linhas.append({"t": t, "evento": fim})
    return ler_claude(json.dumps(linha) for linha in linhas)


def _kiro_leu_arquivo() -> Leitura:
    chamada = {
        "sessionUpdate": "tool_call",
        "toolCallId": "k1",
        "title": "Reading file",
        "kind": "read",
        "rawInput": {},
        "_meta": {"kiro": {"toolName": "fs_read"}},
    }
    linhas = [
        {"t": 1.0, "evento": {"type": "sessionUpdate", "data": {"update": chamada}}},
        {"t": 2.0, "evento": {"type": "runFinished", "data": {"status": "success"}}},
    ]
    return ler_kiro(json.dumps(linha) for linha in linhas)


def _cfg(tmp_path: Path) -> Config:
    return Config(
        motor="podman",
        resultados=tmp_path / "resultados",
        casos=None,
        cenarios_extra=None,
        token_claude=tmp_path / "token",
        volume_kiro="volume",
        cache=tmp_path / "cache",
    )


def test_cases_yaml_real_carrega() -> None:
    casos = carregar_casos()
    assert casos
    assert len({c.id for c in casos}) == len(casos)
    assert CASES_PATH.name == "cases.yaml"


def test_todo_caso_usa_caso_publico() -> None:
    texto = CASES_PATH.read_text(encoding="utf-8")
    assert "{FIXTURES}" not in texto
    assert "{caso:" in texto
    for caso in carregar_casos():
        assert not caso.requires, caso.id
        nome = caso_logico(caso)
        assert nome is None or nome in PUBLICOS, caso.id
        assert "{" not in caso.query.replace(f"{{caso:{nome}}}", ""), caso.id


def test_loader_recusa_caso_que_nao_e_publico(tmp_path: Path) -> None:
    yaml = tmp_path / "cases.yaml"
    yaml.write_text(
        "- id: x\n  query: Liste {caso:caso_interno}\n  expected:\n    uses_mcp: false\n",
        encoding="utf-8",
    )
    with pytest.raises(CasesLoaderError, match="caso_interno"):
        CasesLoader(yaml).load()


def test_toda_tool_da_develop_tem_caso() -> None:
    from novomodelo_mcp.server import build_server

    registradas = {t.name for t in anyio.run(build_server().list_tools)}
    esperadas = set()
    for caso in carregar_casos():
        esperadas |= {caso.expected.tool} if caso.expected.tool else set()
        esperadas |= set(caso.expected.tools or ())
    assert registradas - esperadas == set(), "tool registrada sem caso"
    assert esperadas - registradas == set(), "caso espera tool que o servidor não registra"
    assert registradas == set(MCP_TOOLS)


def test_envelope_vem_do_stream() -> None:
    caso = _caso(tool="deck_list", status="ok", content={"count": "__gt__:0"})
    envelope = {"status": "ok", "count": 11, "files": []}
    leitura = _claude(
        (f"{PREFIXO}server_info", {"versao_mcp": "1"}),
        (f"{PREFIXO}deck_list", envelope),
    )

    resultado = para_query_result(caso, leitura)
    assert [c.name for c in resultado.tool_calls] == ["server_info", "deck_list"]
    assert resultado.envelope == {"tool": "deck_list", "arguments": {}, "result": envelope}
    assert resultado.agent_response == "feito"

    avaliacao = avaliar_tools(caso)(leitura)
    assert avaliacao.estado == "passou", avaliacao.motivo
    assert avaliacao.metricas.acerto_tool is True
    assert avaliacao.metricas.erros_envelope == 0
    assert avaliacao.metricas.t_primeira_tool == 1.0
    assert avaliacao.metricas.t_total == 4.0
    assert avaliacao.metricas.nota_juiz is None


def test_envelope_com_o_status_esperado_vale_entre_as_chamadas_da_tool() -> None:
    caso = _caso(tool="results_status", status="ok")
    recusa = {"status": "error", "exit_code": 2, "diagnostics": ["não é a pasta de uma rodada"]}
    leitura = _claude(
        (f"{PREFIXO}results_status", recusa),
        (f"{PREFIXO}results_status", {"status": "ok"}),
    )
    avaliacao = avaliar_tools(caso)(leitura)
    assert avaliacao.estado == "passou", avaliacao.motivo
    assert avaliacao.metricas.erros_envelope == 1


def test_status_do_vocabulario_do_bridge_vai_pelo_content() -> None:
    caso = _caso(tool="bridge_check_decomp", content={"status": "__matches__:^(ok|warnings)$"})
    leitura = _claude((f"{PREFIXO}bridge_check_decomp", {"status": "warnings"}))
    assert avaliar_tools(caso)(leitura).estado == "passou"
    leitura = _claude((f"{PREFIXO}bridge_check_decomp", {"status": "will-not-convert"}))
    assert avaliar_tools(caso)(leitura).estado == "falhou"


def test_tool_sem_resultado_conta_como_chamada_e_falha_o_status() -> None:
    caso = _caso(tool="deck_list", status="ok")
    avaliacao = avaliar_tools(caso)(_claude((f"{PREFIXO}deck_list", None)))
    assert avaliacao.estado == "falhou"
    assert avaliacao.metricas.acerto_tool is True
    assert "envelope" in avaliacao.motivo


def test_tool_errada_falha_sem_acerto() -> None:
    caso = _caso(tool="deck_list", status="ok")
    avaliacao = avaliar_tools(caso)(_claude((f"{PREFIXO}case_summary", {"status": "ok"})))
    assert avaliacao.estado == "falhou"
    assert avaliacao.metricas.acerto_tool is False
    assert avaliacao.metricas.t_primeira_tool == 1.0


def _validar_erro(envelope: dict, trecho: str) -> bool:
    caso = _caso(tool="run_status", status="error", error_contains=trecho)
    resultado = QueryResult(
        test_case=caso,
        tool_calls=[],
        agent_response="",
        latency_ms=0.0,
        status="completed",
        stdout="",
        stderr="",
        envelope={"tool": "run_status", "arguments": {}, "result": envelope},
    )
    checagem = next(
        c for c in QueryValidator().validate(caso, resultado).checks if c.name == "error_contains"
    )
    return checagem.passed


def test_error_contains_olha_diagnostics() -> None:
    erro = {"status": "error", "exit_code": 2, "diagnostics": ["job inexistente: 99999"]}
    assert _validar_erro(erro, "job inexistente")
    assert _validar_erro(erro, "JOB INEXISTENTE")
    assert not _validar_erro(erro, "not found")
    assert not _validar_erro({"status": "error", "error": "job inexistente"}, "job inexistente")
    do_bridge = {
        "status": "will-not-convert",
        "diagnostics": [{"code": "source-file-missing", "summary": "caso.dat not found"}],
    }
    assert _validar_erro(do_bridge, "source-file-missing")


@pytest.mark.parametrize("proibidas", [["Read"], ["read_file"]])
def test_did_not_use_normaliza_nomes_dos_dois_agentes(proibidas: list[str]) -> None:
    caso = _caso(tool="deck_list", did_not_use=proibidas)
    so_mcp = _claude((f"{PREFIXO}deck_list", {"status": "ok"}))
    claude_leu = _claude((f"{PREFIXO}deck_list", {"status": "ok"}), ("Read", {"ok": 1}))
    kiro_leu = _kiro_leu_arquivo()

    assert avaliar_tools(caso)(so_mcp).estado == "passou"
    falhou = avaliar_tools(caso)(claude_leu)
    assert falhou.estado == "falhou"
    assert "Read" in falhou.motivo
    caso_kiro = replace(caso, expected=replace(caso.expected, uses_mcp=False, tool=None))
    assert avaliar_tools(caso_kiro)(kiro_leu).estado == "falhou"


def test_para_execucoes_monta_pedido_caso_e_imagem(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    preparados = tmp_path / "preparados"
    (preparados / "exemplo_1dtoy").mkdir(parents=True)
    sem_caso = QueryTestCase(
        id="docs", query="o que é SDDP?", expected=ExpectedResult(uses_mcp=True, tool="docs_search")
    )
    config = ConfigMCP("mcp-1_0", None)

    execucoes = para_execucoes(
        [_caso(tool="deck_list"), sem_caso],
        cfg,
        agentes=["claude", "kiro"],
        configs=[config],
        repeticoes=2,
        preparados=preparados,
    )

    assert len(execucoes) == 2 * 2 * 2
    primeira = execucoes[0]
    assert primeira.conjunto == "tools"
    assert primeira.caso == "c"
    assert primeira.pedido == "Liste o caso /estudos/exemplo_1dtoy"
    assert primeira.caso_origem == preparados / "exemplo_1dtoy"
    assert not primeira.somente_leitura
    assert {e.imagem for e in execucoes} == {
        tag_imagem(config, "claude"),
        tag_imagem(config, "kiro"),
    }
    assert {e.repeticao for e in execucoes} == {1, 2}
    docs = [e for e in execucoes if e.caso == "docs"]
    assert all(e.caso_origem is None and e.pedido == "o que é SDDP?" for e in docs)
    assert all(re.fullmatch(r"[0-9]+", str(e.timeout_s)) for e in execucoes)


def test_para_execucoes_caso_nao_preparado_fica_para_o_executor(tmp_path: Path) -> None:
    execucoes = para_execucoes(
        [_caso(tool="deck_list")],
        _cfg(tmp_path),
        agentes=["claude"],
        configs=[ConfigMCP("mcp-1_0", None)],
        repeticoes=1,
        preparados=tmp_path / "vazio",
    )
    assert execucoes[0].caso_origem == tmp_path / "vazio" / "exemplo_1dtoy"


def test_argumentos_e_envelope_vem_da_mesma_chamada() -> None:
    caso = _caso(tool="results_status", status="ok")
    recusa = {"status": "error", "exit_code": 2, "diagnostics": ["não é a pasta de uma rodada"]}
    leitura = _claude(
        (f"{PREFIXO}results_status", recusa, {"output_dir": "/estudos/x"}),
        (f"{PREFIXO}results_status", {"status": "ok"}, {"output_dir": "/estudos/x/output"}),
    )
    envelope = para_query_result(caso, leitura).envelope
    assert envelope["arguments"] == {"output_dir": "/estudos/x/output"}
    assert envelope["result"] == {"status": "ok"}


def test_chamada_escolhida_tambem_confere_o_content() -> None:
    caso = _caso(tool="case_init", status="ok", content={"artifacts.case_dir": "__any__"})
    leitura = _claude(
        (f"{PREFIXO}case_init", {"status": "ok", "templates": []}, {"list": True}),
        (
            f"{PREFIXO}case_init",
            {"status": "ok", "artifacts": {"case_dir": "/estudos/novo"}},
            {"directory": "/estudos/novo", "template": "1dtoy"},
        ),
    )
    assert para_query_result(caso, leitura).envelope["arguments"]["template"] == "1dtoy"
    assert avaliar_tools(caso)(leitura).estado == "passou"


def test_caso_logico_fora_dos_publicos_nunca_vira_caminho(tmp_path: Path) -> None:
    interno = QueryTestCase(
        id="x",
        query="Liste {caso:caso_interno}",
        expected=ExpectedResult(uses_mcp=True, tool="deck_list"),
    )
    with pytest.raises(ValueError, match="não é público"):
        caso_logico(interno)
    with pytest.raises(ValueError, match="não é público"):
        para_execucoes(
            [interno],
            _cfg(tmp_path),
            agentes=["claude"],
            configs=[ConfigMCP("mcp-1_0", None)],
            repeticoes=1,
            preparados=tmp_path,
        )


@pytest.mark.parametrize(
    ("esperado", "liberar"),
    [
        ({"tool": "run_start"}, ("run_start",)),
        ({"tool": "deck_edit_json"}, ("deck_edit_json",)),
        ({"tool": "deck_list"}, ()),
        ({"tool": "instalar_novomodelo"}, ()),
        ({"tools": ["case_validate", "bridge_check_newave"]}, ()),
        ({"tools": ["bridge_dashboard", "deck_list"]}, ("bridge_dashboard",)),
    ],
)
def test_para_execucoes_libera_so_as_esperadas_que_pedem_aprovacao(
    tmp_path: Path, esperado: dict, liberar: tuple[str, ...]
) -> None:
    caso = _caso(**esperado)
    assert tools_a_liberar(caso) == liberar
    (execucao,) = para_execucoes(
        [caso],
        _cfg(tmp_path),
        agentes=["claude"],
        configs=[ConfigMCP("mcp-1_0", None)],
        repeticoes=1,
        preparados=tmp_path,
    )
    assert execucao.liberar == liberar


def test_todo_caso_do_yaml_libera_so_tools_do_mcp_que_gravam() -> None:
    from novomodelo_mcp_e2e.executor.container import conferir_liberadas, tools_do_servidor

    registradas = tools_do_servidor()
    for caso in carregar_casos():
        liberar = tools_a_liberar(caso)
        assert conferir_liberadas(liberar) == liberar, caso.id
        assert all(registradas[n].so_leitura is False for n in liberar), caso.id


def _linha(t: float, evento: dict) -> str:
    return json.dumps({"t": t, "evento": evento})


def test_resultado_fora_de_ordem_pareia_pelo_id_da_chamada_no_claude() -> None:
    def uso(ident: str, pasta: str) -> dict:
        bloco = {
            "type": "tool_use",
            "id": ident,
            "name": f"{PREFIXO}results_status",
            "input": {"output_dir": pasta},
        }
        return {"type": "assistant", "message": {"content": [bloco]}}

    def resultado(ident: str, envelope: dict) -> dict:
        bloco = {
            "type": "tool_result",
            "tool_use_id": ident,
            "content": [{"type": "text", "text": json.dumps(envelope)}],
        }
        return {"type": "user", "message": {"content": [bloco]}}

    leitura = ler_claude(
        [
            _linha(1.0, uso("a", "/estudos/x")),
            _linha(1.1, uso("b", "/estudos/x/output")),
            _linha(2.0, resultado("b", {"status": "ok"})),
            _linha(2.5, resultado("a", {"status": "error", "diagnostics": ["recusa"]})),
            _linha(3.0, {"type": "result", "result": "", "usage": {}}),
        ]
    )
    caso = _caso(tool="results_status", status="ok")
    envelope = para_query_result(caso, leitura).envelope
    assert envelope["arguments"] == {"output_dir": "/estudos/x/output"}
    assert envelope["result"] == {"status": "ok"}
    caso_erro = _caso(tool="results_status", status="error")
    assert para_query_result(caso_erro, leitura).envelope["arguments"] == {
        "output_dir": "/estudos/x"
    }


def test_resultado_fora_de_ordem_pareia_pelo_id_da_chamada_no_kiro() -> None:
    def chamada(ident: str, pasta: str) -> dict:
        u = {
            "sessionUpdate": "tool_call",
            "toolCallId": ident,
            "title": "results_status",
            "rawInput": {"output_dir": pasta},
            "_meta": {"kiro": {"mcpServerName": "novomodelo", "toolName": "results_status"}},
        }
        return {"type": "sessionUpdate", "data": {"update": u}}

    def resultado(ident: str, envelope: dict) -> dict:
        u = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": ident,
            "status": "completed",
            "content": [{"type": "content", "content": {"text": json.dumps(envelope)}}],
        }
        return {"type": "sessionUpdate", "data": {"update": u}}

    leitura = ler_kiro(
        [
            _linha(1.0, chamada("k1", "/estudos/x")),
            _linha(1.1, chamada("k2", "/estudos/x/output")),
            _linha(2.0, resultado("k2", {"status": "ok"})),
            _linha(2.5, resultado("k1", {"status": "error", "diagnostics": ["recusa"]})),
            _linha(3.0, {"type": "runFinished", "data": {"status": "success"}}),
        ]
    )
    envelope = para_query_result(_caso(tool="results_status", status="ok"), leitura).envelope
    assert envelope["arguments"] == {"output_dir": "/estudos/x/output"}


def test_envelope_do_kiro_atual_vem_de_rawoutput() -> None:
    leitura = ler_kiro((FIX / "kiro-stream-sintetico-2.jsonl").read_text("utf-8").splitlines())
    resultado = para_query_result(_caso(tool="server_info", status="ok"), leitura)
    assert resultado.envelope["tool"] == "server_info"
    assert resultado.envelope["result"] == {"status": "ok", "versao": "0.0.0-exemplo"}
    erro = para_query_result(_caso(tool="case_validate", status="error"), leitura)
    assert erro.envelope["arguments"]["case_dir"] == "/estudos/caso-exemplo"
    assert erro.envelope["result"]["status"] == "error"
