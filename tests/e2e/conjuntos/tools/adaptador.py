"""Casos por tool pelo executor: uma `Execucao` por caso e o `avaliar` que valida o stream.

O caso cita o caso público pelo marcador `{caso:<nome lógico>}` no pedido; no container
ele vira `/estudos/<nome lógico>`, a cópia que o executor monta.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from tests.e2e.config import Config
from tests.e2e.executor.casos import pasta_preparados
from tests.e2e.executor.container import PASTA_ESTUDOS, Execucao
from tests.e2e.executor.eventos import Evento, Leitura
from tests.e2e.executor.imagens import ConfigMCP, tag_imagem
from tests.e2e.queries.loader import MARCADOR_CASO, CasesLoader
from tests.e2e.queries.models import QueryResult, QueryTestCase, ToolCall
from tests.e2e.queries.validator import QueryValidator
from tests.e2e.resultado.modelos import Avaliacao, Metricas

CONJUNTO = "tools"
CASES_PATH = Path(__file__).resolve().parents[2] / "queries" / "cases.yaml"
TIMEOUT_PADRAO = 300


def carregar_casos(caminho: Path = CASES_PATH) -> list[QueryTestCase]:
    """Os casos do `cases.yaml`, validados pelo loader.

    Raises:
        CasesLoaderError: o arquivo não carrega ou não valida.
    """
    return CasesLoader(caminho).load()


def caso_logico(caso: QueryTestCase) -> str | None:
    achado = MARCADOR_CASO.search(caso.query)
    return achado.group(1) if achado else None


def _pedido(caso: QueryTestCase) -> str:
    return MARCADOR_CASO.sub(lambda m: f"{PASTA_ESTUDOS}/{m.group(1)}", caso.query)


def para_execucoes(
    casos: Sequence[QueryTestCase],
    cfg: Config,
    *,
    agentes: Sequence[str],
    configs: Sequence[ConfigMCP],
    repeticoes: int,
    preparados: Path | None = None,
) -> list[Execucao]:
    """Uma execução por caso, configuração, agente e repetição, numa cópia do caso.

    Um caso público ausente de `preparados` segue com o caminho esperado: o executor
    grava `erro_infra` (o preparo não rodou), e não um caso pulado.
    """
    base = preparados if preparados is not None else pasta_preparados(cfg)
    execucoes = []
    for caso in casos:
        nome = caso_logico(caso)
        for config in configs:
            for agente in agentes:
                for repeticao in range(1, repeticoes + 1):
                    execucoes.append(
                        Execucao(
                            conjunto=CONJUNTO,
                            caso=caso.id,
                            agente=agente,
                            config=config.nome,
                            repeticao=repeticao,
                            pedido=_pedido(caso),
                            caso_origem=base / nome if nome else None,
                            somente_leitura=False,
                            timeout_s=int(caso.timeout_s or TIMEOUT_PADRAO),
                            imagem=tag_imagem(config, agente),
                        )
                    )
    return execucoes


def _envelope(ev: Evento) -> dict | None:
    texto = (ev.dados.get("conteudo") or "").strip()
    for candidato in (texto, texto[texto.find("{") : texto.rfind("}") + 1]):
        try:
            valor = json.loads(candidato)
        except ValueError:
            continue
        if isinstance(valor, dict):
            return valor
    return None


def _esperadas(caso: QueryTestCase) -> set[str]:
    e = caso.expected
    return {e.tool} if e.tool else set(e.tools or ())


def _resultados_mcp(leitura: Leitura) -> list[tuple[str, dict | None]]:
    return [
        (ev.nome, _envelope(ev))
        for ev in leitura.eventos
        if ev.tipo == "resultado_tool" and ev.do_mcp and ev.nome
    ]


def _escolher_envelope(caso: QueryTestCase, leitura: Leitura) -> tuple[str, dict] | None:
    """O primeiro envelope da tool esperada com o status esperado, senão o último dela.

    O agente pode receber uma recusa guiada (`output_sugerido`) e acertar na segunda
    chamada, ou provocar o erro pedido e seguir com outra chamada: vale a chamada que
    mostra o comportamento do caso, não sempre a primeira tool do MCP.
    """
    alvo = _esperadas(caso)
    da_tool = [(n, env) for n, env in _resultados_mcp(leitura) if env is not None and n in alvo]
    if not da_tool:
        return None
    esperado = caso.expected.status
    return next((r for r in da_tool if r[1].get("status") == esperado), da_tool[-1])


def _fim(leitura: Leitura) -> Evento | None:
    return next((ev for ev in reversed(leitura.eventos) if ev.tipo == "fim"), None)


def para_query_result(caso: QueryTestCase, leitura: Leitura) -> QueryResult:
    chamadas = [
        ToolCall(name=ev.nome, args=dict(ev.args))
        for ev in leitura.eventos
        if ev.tipo == "tool" and ev.nome
    ]
    escolhido = _escolher_envelope(caso, leitura)
    envelope = None
    if escolhido is not None:
        nome, resultado = escolhido
        args = next((c.args for c in chamadas if c.name == nome), {})
        envelope = {"tool": nome, "arguments": args, "result": resultado}
    fim = _fim(leitura)
    t_total = fim.t if fim else (leitura.eventos[-1].t if leitura.eventos else 0.0)
    return QueryResult(
        test_case=caso,
        tool_calls=chamadas,
        agent_response=fim.dados.get("resposta", "") if fim else "",
        latency_ms=t_total * 1000,
        status="completed",
        stdout="",
        stderr="",
        envelope=envelope,
    )


def _metricas(caso: QueryTestCase, leitura: Leitura, acerto: bool) -> Metricas:
    tools_mcp = [ev for ev in leitura.eventos if ev.tipo == "tool" and ev.do_mcp]
    erros = sum(
        1
        for ev in leitura.eventos
        if ev.tipo == "resultado_tool"
        and ev.do_mcp
        and (ev.erro or (_envelope(ev) or {}).get("status") == "error")
    )
    fim = _fim(leitura)
    return Metricas(
        acerto_tool=acerto,
        aprovacoes=sum(1 for ev in leitura.eventos if ev.tipo == "negacao"),
        erros_envelope=erros,
        t_primeira_tool=tools_mcp[0].t if tools_mcp else None,
        t_total=fim.t if fim else (leitura.eventos[-1].t if leitura.eventos else 0.0),
    )


def avaliar_tools(caso: QueryTestCase) -> Callable[[Leitura], Avaliacao]:
    """O `avaliar` do executor: `passou` quando todas as checagens do validador passam."""
    validador = QueryValidator()

    def avaliar(leitura: Leitura) -> Avaliacao:
        resultado = validador.validate(caso, para_query_result(caso, leitura))
        por_nome = {c.name: c.passed for c in resultado.checks}
        acerto = por_nome.get("correct_tool", por_nome.get("uses_mcp", False))
        motivo = resultado.failure_reason or "todas as checagens passaram"
        return Avaliacao(
            "passou" if resultado.valid else "falhou", motivo, _metricas(caso, leitura, acerto)
        )

    return avaliar
