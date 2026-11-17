"""Pontuação de uma conversa contra o cenário e o veredito do conjunto usuário."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

from novomodelo_mcp_e2e.config import Config
from novomodelo_mcp_e2e.conjuntos.usuario.cenario import Cenario
from novomodelo_mcp_e2e.conjuntos.usuario.juiz import Juiz, conferencias_das_tools, julgar
from novomodelo_mcp_e2e.executor.eventos import Evento, Leitura
from novomodelo_mcp_e2e.resultado.modelos import Avaliacao, Metricas

NOTA_MINIMA = 1
_LEITURA_POR_FORA = {"Bash", "Read", "Grep", "Glob", "WebFetch", "execute_bash", "fs_read", "shell"}
_NEUTRAS = {
    "server_info",
    "solver_version",
    "docs_search",
    "docs_read",
    "docs_list",
    "schema_list",
    "schema_get",
    "results_status",
    "results_list_entities",
    "deck_list",
    "case_summary",
}
_RECUSA = re.compile(r"fora do workspace|\"status\":\s*\"error\"|'status':\s*'error'")
_TERMINAL_SO_LEITURA = {
    "ls",
    "cat",
    "head",
    "tail",
    "find",
    "grep",
    "rg",
    "wc",
    "pwd",
    "echo",
    "stat",
    "file",
    "du",
    "jq",
    "sort",
    "uniq",
    "cut",
    "tree",
    "which",
    "cd",
    "true",
}
_NATIVAS_LEITURA = {"Read", "Glob", "Grep", "LS"}
_NATIVAS_ESCRITA = {"Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch"}
_PASTA = "/estudos"


@dataclass(frozen=True)
class Resultado:
    cenario: str
    agente: str
    repeticao: int
    acerto_tool: bool
    contornos: int
    aprovacoes: int
    rigidez: int
    erros_envelope: int
    t_primeira_tool: float | None
    t_total: float
    tokens_entrada: int | None
    tokens_saida: int | None
    resposta_correta: bool | None
    interrupcoes: int = 0
    t_primeira_interrupcao: float | None = None
    maior_trecho_sem_interrupcao: float = 0.0
    indice_autonomia: float = 1.0
    comandos_terminal: int = 0


def _caminhos(e: Evento) -> list[str]:
    a = e.args
    achados = [str(a[k]) for k in ("file_path", "path", "notebook_path") if a.get(k)]
    for op in a.get("operations") or []:
        if isinstance(op, dict) and op.get("path"):
            achados.append(str(op["path"]))
    return achados


def _terminal_so_leitura(cmd: str) -> bool:
    if re.search(r"(?<![<>&\d])>(?!&)|\btee\b", cmd):
        return False
    partes = [p.strip() for p in re.split(r"\|\||&&|\||;|\n", cmd) if p.strip()]
    return bool(partes) and all(
        p.split()[0].rsplit("/", 1)[-1] in _TERMINAL_SO_LEITURA for p in partes
    )


def pede_aprovacao(e: Evento, agente: str, leitura_mcp: Collection[str]) -> bool:
    """A pessoa teria de aprovar esta chamada, pelas regras de cada cliente sem liberar tudo?"""
    if e.do_mcp:
        return e.nome not in leitura_mcp
    if e.nome == "Bash":
        return agente != "claude" or not _terminal_so_leitura(str(e.args.get("command", "")))
    if e.nome in _NATIVAS_LEITURA:
        return any(
            not (c == _PASTA or c.startswith(_PASTA + "/") or not c.startswith("/"))
            for c in _caminhos(e)
        )
    return e.nome in _NATIVAS_ESCRITA


def _texto_da_chamada(e: Evento) -> str:
    return " ".join(str(v) for v in e.args.values())


def _checar(checagem: dict | None, resposta: str) -> bool | None:
    if not checagem:
        return None
    if checagem["tipo"] == "contem":
        return checagem["valor"].lower() in resposta.lower()
    if checagem["tipo"] == "numero":
        alvo, tol = float(checagem["valor"]), float(checagem.get("tol", 0))
        numeros = re.findall(r"-?\d+(?:[.,]\d+)?", resposta)
        return any(abs(float(x.replace(",", ".")) - alvo) <= tol for x in numeros)
    raise ValueError(f"checagem desconhecida: {checagem['tipo']}")


def _resposta(eventos: list[Evento]) -> str:
    fim = next((e for e in reversed(eventos) if e.tipo == "fim"), None)
    return fim.dados.get("resposta", "") if fim else ""


def _acerto(cenario: Cenario, tools: list[Evento]) -> bool:
    do_mcp = [e for e in tools if e.do_mcp]
    chamadas = {e.nome for e in do_mcp}
    esperadas = set(cenario.tools_esperadas)
    if not esperadas:
        return bool(set(cenario.nativas_esperadas) & {e.nome for e in tools if not e.do_mcp})
    # Orientar-se (versões, docs, o que existe na pasta) antes de agir não é desvio.
    primeira = next((e.nome for e in do_mcp if e.nome not in _NEUTRAS), None)
    alternativas = set(cenario.tools_alternativas)
    aceitas = esperadas | alternativas | set(cenario.primeira_aceita)
    return (esperadas <= chamadas or (bool(alternativas) and alternativas <= chamadas)) and (
        primeira is None or primeira in aceitas
    )


def pontuar(
    cenario: Cenario,
    eventos: list[Evento],
    agente: str = "claude",
    repeticao: int = 1,
    leitura_mcp: Collection[str] | None = None,
) -> Resultado:
    tools = [e for e in eventos if e.tipo == "tool"]
    do_mcp = [e for e in tools if e.do_mcp]
    acerto = _acerto(cenario, tools)
    padroes = [re.compile(p, re.IGNORECASE) for p in cenario.contorno]
    contornos = sum(
        1
        for e in tools
        if not e.do_mcp
        and e.nome in _LEITURA_POR_FORA
        and any(p.search(_texto_da_chamada(e)) for p in padroes)
    )
    recusas = [
        e
        for e in eventos
        if e.tipo == "resultado_tool"
        and e.do_mcp
        and (e.erro or _RECUSA.search(e.dados.get("conteudo", "")))
    ]
    rigidez = sum(1 for r in recusas if not any(e.do_mcp for e in tools if e.t >= r.t))
    fim = next((e for e in reversed(eventos) if e.tipo == "fim"), None)
    resposta = _resposta(eventos)
    if cenario.acerto_pela_resposta:
        acerto = bool(_checar(cenario.checagem, resposta)) and contornos == 0
    t_total = fim.t if fim else (eventos[-1].t if eventos else 0.0)
    marcas = sorted(e.t for e in tools if pede_aprovacao(e, agente, leitura_mcp or ()))
    bordas = [0.0, *marcas, t_total]
    maior = max((b - a for a, b in zip(bordas, bordas[1:], strict=False)), default=t_total)
    indice = round((marcas[0] if marcas else t_total) / t_total, 3) if t_total else 1.0
    return Resultado(
        cenario=cenario.id,
        agente=agente,
        repeticao=repeticao,
        acerto_tool=acerto,
        contornos=contornos,
        aprovacoes=sum(1 for e in eventos if e.tipo == "negacao"),
        rigidez=rigidez,
        erros_envelope=len(recusas),
        t_primeira_tool=do_mcp[0].t if do_mcp else None,
        t_total=t_total,
        tokens_entrada=fim.dados.get("tokens_entrada") if fim else None,
        tokens_saida=fim.dados.get("tokens_saida") if fim else None,
        resposta_correta=_checar(cenario.checagem, resposta),
        interrupcoes=len(marcas),
        t_primeira_interrupcao=marcas[0] if marcas else None,
        maior_trecho_sem_interrupcao=round(maior, 2),
        indice_autonomia=indice,
        comandos_terminal=sum(1 for e in tools if not e.do_mcp and e.nome == "Bash"),
    )


def metricas(r: Resultado, nota_juiz: int | None, agente: str) -> Metricas:
    """As métricas do registro; o Kiro não informa tokens, que ficam `None` e não zero."""
    informa_tokens = agente == "claude"
    return Metricas(
        acerto_tool=r.acerto_tool,
        contornos=r.contornos,
        aprovacoes=r.aprovacoes,
        rigidez=r.rigidez,
        erros_envelope=r.erros_envelope,
        t_primeira_tool=r.t_primeira_tool,
        t_total=r.t_total,
        tokens_entrada=r.tokens_entrada if informa_tokens else None,
        tokens_saida=r.tokens_saida if informa_tokens else None,
        resposta_correta=r.resposta_correta,
        interrupcoes=r.interrupcoes,
        t_primeira_interrupcao=r.t_primeira_interrupcao,
        maior_trecho_sem_interrupcao=r.maior_trecho_sem_interrupcao,
        indice_autonomia=r.indice_autonomia,
        comandos_terminal=r.comandos_terminal,
        nota_juiz=nota_juiz,
    )


def avaliar_usuario(
    c: Cenario,
    juiz: Juiz,
    cfg: Config,
    *,
    agente: str = "claude",
    repeticao: int = 1,
    leitura_mcp: Collection[str] = (),
    imagem: str | None = None,
    destino_log: Path | None = None,
) -> Callable[[Leitura], Avaliacao]:
    """O `avaliar` do executor: `passou` com o uso da tool certo e a nota do juiz na régua.

    `leitura_mcp` são as tools do MCP que o cliente roda sem pedir aprovação; `destino_log`
    é a pasta da execução, onde fica o log do juiz. `FalhaJuiz` e `LimiteDeUsoJuiz` sobem
    ao executor, que grava `erro_infra`.
    """

    def avaliar(leitura: Leitura) -> Avaliacao:
        r = pontuar(c, leitura.eventos, agente, repeticao, leitura_mcp)
        veredito = julgar(
            juiz,
            c,
            _resposta(leitura.eventos),
            cfg,
            imagem=imagem,
            destino_log=destino_log,
            conferencias=conferencias_das_tools(c, leitura.eventos),
        )
        nota = veredito["nota"]
        falhas = []
        if not r.acerto_tool:
            falhas.append("as tools esperadas não foram usadas no caminho do cenário")
        if nota < NOTA_MINIMA:
            falhas.append(f"nota do juiz {nota} abaixo de {NOTA_MINIMA}")
        justificativa = f"juiz: {veredito['justificativa']}"
        motivo = "; ".join([*falhas, justificativa])
        return Avaliacao("falhou" if falhas else "passou", motivo, metricas(r, nota, agente))

    return avaliar
