"""Relatório de go/no-go em Markdown, determinístico e só com caminhos relativos."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from statistics import mean

from tests.e2e.go_no_go.criterio import Decisao
from tests.e2e.go_no_go.estatistica import wilson
from tests.e2e.resultado.modelos import Manifesto, Registro

LIMITE_TOOLS = 10
SEM_DADO = "—"
SEM_MCP = "sem-mcp"
METRICAS_AMPLAS = (
    ("acerto_tool", "uso da tool esperada (0–1)"),
    ("nota_juiz", "nota juiz (0–2)"),
    ("contornos", "contornos"),
    ("interrupcoes", "interrupções"),
    ("indice_autonomia", "autonomia"),
    ("t_total", "tempo (s)"),
    ("tokens_entrada", "tokens entrada"),
)
POR_CENARIO = ("acerto_tool", "nota_juiz", "interrupcoes", "t_total")
INTRO_AMPLA = (
    "Médias por conversa. Autonomia = fração do tempo até a 1ª interrupção (1 = nenhuma). "
    "Interrupções = aprovações que a pessoa teria de dar. Nota do juiz: qualidade da resposta "
    "(0, 1 ou 2). Uso da tool esperada: fração das conversas que chamaram as tools do MCP "
    "previstas (sem MCP é ~0 por construção). Tempo: o do agente, medido no stream. "
    f"{SEM_DADO} = o agente não informa a métrica."
)
_PARTE_VERSAO = re.compile(r"[._+-]")


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def _tabela(cabecalho: Sequence[str], linhas: Sequence[Sequence[str]]) -> list[str]:
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "---|" * len(cabecalho)]
    saida += ["| " + " | ".join(_celula(c) for c in linha) + " |" for linha in linhas]
    return saida


def _lista(titulo: str, itens: Sequence[str], vazio: str) -> list[str]:
    corpo = [f"- `{item}`" for item in sorted(itens)] or [vazio]
    return [f"## {titulo}", "", *corpo, ""]


def _taxa(registros: Sequence[Registro]) -> str:
    passou = sum(r.estado == "passou" for r in registros)
    contaveis = passou + sum(r.estado == "falhou" for r in registros)
    if contaveis == 0:
        return SEM_DADO
    baixo, alto = wilson(passou, contaveis)
    return f"{round(100 * passou / contaveis)}% [{round(100 * baixo)}–{round(100 * alto)}%]"


def _grupos(registros: Sequence[Registro]) -> dict[tuple[str, str, str], list[Registro]]:
    grupos: dict[tuple[str, str, str], list[Registro]] = defaultdict(list)
    for r in registros:
        grupos[(r.conjunto, r.agente, r.config)].append(r)
    return dict(sorted(grupos.items()))


def _bloqueios(decisao: Decisao) -> list[str]:
    linhas = [
        [b.regra, b.conjunto, b.caso, b.agente, "<br>".join(f"`{e}`" for e in sorted(b.evidencia))]
        for b in sorted(decisao.bloqueios, key=lambda b: (b.conjunto, b.caso, b.agente, b.regra))
    ]
    corpo = _tabela(["Regra", "Conjunto", "Caso", "Agente", "Evidência"], linhas)
    return ["## Bloqueios", "", *(corpo if linhas else ["Nenhum bloqueio."]), ""]


def _dependentes_da_baseline(decisao: Decisao, base: str | None) -> list[str]:
    if base is None:
        aviso = ["Sem baseline: só a determinística bloqueia; não há grupos sem base nem ausentes."]
        return ["## Sem base e ausentes", "", *aviso, ""]
    return [
        *_lista("Sem base", decisao.sem_base, "Nenhum."),
        *_lista("Ausentes", decisao.ausentes, "Nenhum."),
    ]


def _taxas(registros: Sequence[Registro]) -> list[str]:
    linhas = []
    for (conjunto, agente, config), grupo in _grupos(registros).items():
        estados = Counter(r.estado for r in grupo)
        linhas.append(
            [
                conjunto,
                agente,
                config,
                _taxa(grupo),
                str(estados["passou"]),
                str(estados["falhou"]),
                str(estados["pulado"]),
                str(estados["erro_infra"]),
            ]
        )
    cabecalho = [
        "Conjunto",
        "Agente",
        "Config",
        "Acerto",
        "Passou",
        "Falhou",
        "Pulado",
        "Erro infra",
    ]
    return ["## Taxa de acerto", "", *_tabela(cabecalho, linhas), ""]


def _lado_a_lado(m: Manifesto, registros: Sequence[Registro]) -> list[str]:
    if len(m.configs) <= 1 and not m.flags.get("completa"):
        return []
    por_celula: dict[tuple[str, str], dict[str, list[Registro]]] = defaultdict(dict)
    for (conjunto, agente, config), grupo in _grupos(registros).items():
        por_celula[(conjunto, agente)][config] = grupo
    configs = sorted({*m.configs, *(r.config for r in registros)})
    linhas = [
        [conjunto, agente, *(_taxa(celulas.get(c, [])) for c in configs)]
        for (conjunto, agente), celulas in sorted(por_celula.items())
    ]
    return [
        "## Configurações lado a lado",
        "",
        *_tabela(["Conjunto", "Agente", *configs], linhas),
        "",
    ]


def _tempos(registros: Sequence[Registro]) -> list[str]:
    linhas = []
    for (conjunto, agente, config), grupo in _grupos(registros).items():
        contaveis = [r.duracao_s for r in grupo if r.estado in ("passou", "falhou")]
        media = f"{sum(contaveis) / len(contaveis):.1f}" if contaveis else SEM_DADO
        linhas.append([conjunto, agente, config, media])
    cabecalho = ["Conjunto", "Agente", "Config", "Tempo médio (s)"]
    return ["## Tempo médio por execução", "", *_tabela(cabecalho, linhas), ""]


def _mais_chamadas(registros: Sequence[Registro]) -> list[str]:
    chamadas: Counter[str] = Counter()
    falhas: Counter[str] = Counter()
    for r in registros:
        for t in r.tools:
            chamadas[t.nome] += 1
            falhas[t.nome] += t.ok is False
    ordem = sorted(chamadas, key=lambda nome: (-chamadas[nome], nome))[:LIMITE_TOOLS]
    linhas = [[f"`{nome}`", str(chamadas[nome]), str(falhas[nome])] for nome in ordem]
    corpo = _tabela(["Tool", "Chamadas", "Com falha"], linhas)
    return [f"## {LIMITE_TOOLS} tools mais chamadas", "", *(corpo if linhas else ["Nenhuma."]), ""]


def ordenar_configs(configs: Iterable[str]) -> list[str]:
    """Sem MCP primeiro, depois as versões do MCP em ordem crescente, e o resto no fim."""

    def chave(config: str) -> tuple:
        if config == SEM_MCP:
            return (0, ())
        if config.startswith("mcp-"):
            partes = _PARTE_VERSAO.split(config.removeprefix("mcp-"))
            return (1, tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in partes))
        return (2, (config,))

    return sorted(set(configs), key=chave)


def _valor(r: Registro, metrica: str) -> float | None:
    bruto = getattr(r.metricas, metrica)
    return None if bruto is None else float(bruto)


def _media(registros: Sequence[Registro], metrica: str) -> str:
    valores = [v for r in registros if (v := _valor(r, metrica)) is not None]
    if not valores:
        return SEM_DADO
    m = mean(valores)
    return f"{m:.0f}" if m >= 100 else f"{m:.2f}"


def avaliacao_ampla(registros: Sequence[Registro]) -> list[str]:
    """Médias das métricas do conjunto usuário por agente, com as configurações lado a lado."""
    rs = [r for r in registros if r.conjunto == "usuario" and r.estado in ("passou", "falhou")]
    if not rs:
        return []
    configs = ordenar_configs(r.config for r in rs)
    saida = [f"## Avaliação ampla — {len(rs)} conversas", "", INTRO_AMPLA, ""]
    for agente in sorted({r.agente for r in rs}):
        do_agente = [r for r in rs if r.agente == agente]
        resumo = []
        for config in configs:
            grupo = [r for r in do_agente if r.config == config]
            if grupo:
                medias = [_media(grupo, k) for k, _ in METRICAS_AMPLAS]
                resumo.append([config, str(len(grupo)), *medias])
        cabecalho = ["condição", "n", *(nome for _, nome in METRICAS_AMPLAS)]
        saida += [f"### {agente}: resumo", "", *_tabela(cabecalho, resumo), ""]
        por: dict[tuple[str, str], list[Registro]] = defaultdict(list)
        for r in do_agente:
            por[(r.caso, r.config)].append(r)
        linhas = [
            [
                caso,
                *(
                    " / ".join(_media(por[(caso, c)], k) for k in POR_CENARIO)
                    if por.get((caso, c))
                    else SEM_DADO
                    for c in configs
                ),
            ]
            for caso in sorted({caso for caso, _ in por})
        ]
        titulo = f"### {agente}: por cenário (uso da tool / nota / interrupções / tempo)"
        saida += [titulo, "", *_tabela(["cenário", *configs], linhas), ""]
    return saida


def _versoes(m: Manifesto) -> list[str]:
    itens = [f"{nome} {valor}" for nome, valor in sorted(m.versoes.items())]
    itens.append(f"bateria {m.commit_bateria}")
    return ["---", "", "Versões: " + " · ".join(itens)]


def escrever_relatorio(
    m: Manifesto,
    registros: Sequence[Registro],
    decisao: Decisao,
    alvo: str,
    base: str | None,
    destino: Path,
) -> Path:
    baseline = f"`{base}`" if base is not None else "sem baseline"
    linhas = [
        f"# Veredito: {decisao.veredito.upper()}",
        "",
        f"Rodada `{alvo}` · baseline: {baseline} · criada em {m.criado_em}",
        "",
        *_bloqueios(decisao),
        *_lista("Inconclusivos", decisao.inconclusivos, "Nenhum."),
        *_lista("Pulados", decisao.pulados, "Nenhum."),
        *_dependentes_da_baseline(decisao, base),
        *_taxas(registros),
        *_lado_a_lado(m, registros),
        *_tempos(registros),
        *_mais_chamadas(registros),
        *avaliacao_ampla(registros),
        *_versoes(m),
    ]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")
    return destino
