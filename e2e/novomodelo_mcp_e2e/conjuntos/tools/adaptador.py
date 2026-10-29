"""Casos por tool pelo executor: uma `Execucao` por caso e o `avaliar` que valida o stream.

O caso cita o caso público pelo marcador `{caso:<nome lógico>}` no pedido; no container
ele vira `/estudos/<nome lógico>`, a cópia que o executor monta. As tools esperadas que
pedem aprovação vão em `Execucao.liberar`, para o envelope delas chegar ao stream.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from novomodelo_mcp_e2e.config import Config
from novomodelo_mcp_e2e.executor.casos import PUBLICOS, pasta_preparados
from novomodelo_mcp_e2e.executor.container import (
    NUNCA_LIBERADAS,
    PASTA_ESTUDOS,
    Agente,
    Execucao,
    tools_do_servidor,
)
from novomodelo_mcp_e2e.executor.eventos import Evento, Leitura
from novomodelo_mcp_e2e.executor.imagens import ConfigMCP, tag_imagem
from novomodelo_mcp_e2e.queries.loader import MARCADOR_CASO, CasesLoader
from novomodelo_mcp_e2e.queries.models import QueryResult, QueryTestCase, ToolCall
from novomodelo_mcp_e2e.queries.validator import QueryValidator, campos_conferem
from novomodelo_mcp_e2e.resultado.modelos import Avaliacao, Conjunto, Metricas

CONJUNTO: Conjunto = "tools"
CASES_PATH = Path(__file__).resolve().parents[2] / "queries" / "cases.yaml"
TIMEOUT_PADRAO = 300


def carregar_casos(caminho: Path = CASES_PATH) -> list[QueryTestCase]:
    """Os casos do `cases.yaml`, validados pelo loader.

    Raises:
        CasesLoaderError: o arquivo não carrega ou não valida.
    """
    return CasesLoader(caminho).load()


def caso_logico(caso: QueryTestCase) -> str | None:
    """O nome lógico do caso público citado no pedido, ou `None` sem marcador.

    Raises:
        ValueError: o nome não é de um caso público; o caminho nunca é montado.
    """
    achado = MARCADOR_CASO.search(caso.query)
    if achado is None:
        return None
    if achado.group(1) not in PUBLICOS:
        raise ValueError(f"caso {caso.id!r} cita um caso que não é público")
    return achado.group(1)


def _esperadas(caso: QueryTestCase) -> set[str]:
    e = caso.expected
    return {e.tool} if e.tool else set(e.tools or ())


def tools_a_liberar(caso: QueryTestCase) -> tuple[str, ...]:
    """As tools esperadas que pedem aprovação, menos as que o executor nunca libera."""
    registradas = tools_do_servidor()
    return tuple(
        sorted(
            n
            for n in _esperadas(caso)
            if n in registradas and registradas[n].so_leitura is False and n not in NUNCA_LIBERADAS
        )
    )


def pedido_do_caso(caso: QueryTestCase) -> str:
    """O pedido do caso com o marcador `{caso:<nome>}` resolvido para a pasta do container."""
    return MARCADOR_CASO.sub(lambda m: f"{PASTA_ESTUDOS}/{m.group(1)}", caso.query)


def para_execucoes(
    casos: Sequence[QueryTestCase],
    cfg: Config,
    *,
    agentes: Sequence[Agente],
    configs: Sequence[ConfigMCP],
    repeticoes: int,
    preparados: Path | None = None,
) -> list[Execucao]:
    """Uma execução por caso, configuração, agente e repetição, numa cópia do caso.

    Um caso público ausente de `preparados` segue com o caminho esperado: o executor
    grava `erro_infra` (o preparo não rodou), e não um caso pulado.

    Raises:
        ValueError: um caso cita um caso que não é público.
    """
    base = preparados if preparados is not None else pasta_preparados(cfg)
    execucoes = []
    for caso in casos:
        nome = caso_logico(caso)
        liberar = tools_a_liberar(caso)
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
                            pedido=pedido_do_caso(caso),
                            caso_origem=base / nome if nome else None,
                            somente_leitura=False,
                            timeout_s=int(caso.timeout_s or TIMEOUT_PADRAO),
                            imagem=tag_imagem(config, agente),
                            liberar=liberar,
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


def _chamadas_com_resultado(leitura: Leitura) -> list[tuple[str, dict, dict | None]]:
    """(nome, argumentos, envelope) de cada chamada do MCP que teve resultado.

    O resultado fecha a chamada com o mesmo id (`dados["id"]`): argumentos e envelope
    são sempre da mesma chamada, mesmo com resultados fora de ordem. Sem id no stream,
    fecha a chamada aberta mais antiga da mesma tool.
    """
    abertas: list[Evento] = []
    pares = []
    for ev in leitura.eventos:
        if not ev.do_mcp or not ev.nome:
            continue
        if ev.tipo == "tool":
            abertas.append(ev)
        elif ev.tipo == "resultado_tool":
            ident = ev.dados.get("id")
            chamada = next(
                (
                    a
                    for a in abertas
                    if (a.dados.get("id") == ident if ident else a.nome == ev.nome)
                ),
                None,
            )
            if chamada is not None:
                abertas.remove(chamada)
            pares.append((ev.nome, dict(chamada.args) if chamada else {}, _envelope(ev)))
    return pares


def _mostra_o_caso(caso: QueryTestCase, envelope: dict) -> bool:
    e = caso.expected
    if e.status is not None and envelope.get("status") != e.status:
        return False
    return campos_conferem(envelope, e.content or {})


def _escolher_envelope(caso: QueryTestCase, leitura: Leitura) -> tuple[str, dict, dict] | None:
    """A primeira chamada da tool esperada com o status e o content do caso, senão a última.

    O agente pode receber uma recusa guiada (`suggested_output`) e acertar na segunda
    chamada, listar antes de agir, ou provocar o erro pedido e seguir com outra chamada:
    vale a chamada que mostra o comportamento do caso, não sempre a primeira do MCP.
    """
    alvo = _esperadas(caso)
    da_tool = [
        (nome, args, env)
        for nome, args, env in _chamadas_com_resultado(leitura)
        if env is not None and nome in alvo
    ]
    if not da_tool:
        return None
    return next((c for c in da_tool if _mostra_o_caso(caso, c[2])), da_tool[-1])


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
        nome, args, resultado = escolhido
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
