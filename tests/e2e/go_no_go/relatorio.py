"""Relatório de go/no-go em Markdown, determinístico e só com caminhos relativos."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

from tests.e2e.go_no_go.criterio import Decisao
from tests.e2e.go_no_go.estatistica import wilson
from tests.e2e.resultado.modelos import Manifesto, Registro

LIMITE_TOOLS = 10
SEM_DADO = "—"


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
    linhas = [
        [conjunto, agente, config, f"{sum(r.duracao_s for r in grupo) / len(grupo):.1f}"]
        for (conjunto, agente, config), grupo in _grupos(registros).items()
    ]
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
        *_versoes(m),
    ]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")
    return destino
