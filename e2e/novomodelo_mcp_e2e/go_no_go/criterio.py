"""Critério de go/no-go: decide a rodada a partir dos registros, sem I/O."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from novomodelo_mcp_e2e.resultado.armazenamento import caminho_execucao
from novomodelo_mcp_e2e.resultado.modelos import Estado, Registro

Veredito = Literal["go", "no-go", "inconclusivo"]
Regra = Literal["deterministica", "regressao_tool", "regressao_maioria"]
Grupo = tuple[str, str, str]
CONJUNTOS = ("deterministica", "tools", "usuario")


@dataclass(frozen=True)
class Bloqueio:
    regra: Regra
    conjunto: str
    caso: str
    agente: str
    evidencia: tuple[str, ...]


@dataclass(frozen=True)
class Decisao:
    veredito: Veredito
    bloqueios: tuple[Bloqueio, ...]
    inconclusivos: tuple[str, ...]
    pulados: tuple[str, ...]
    sem_base: tuple[str, ...]
    ausentes: tuple[str, ...] = ()
    incompleto: tuple[str, ...] = ()


def _maioria(passou: int, falhou: int) -> bool:
    return 2 * passou > passou + falhou


def maioria_passou(estados: Sequence[Estado]) -> bool:
    return _maioria(estados.count("passou"), estados.count("falhou"))


def _agrupar(registros: Sequence[Registro]) -> dict[Grupo, list[Registro]]:
    grupos: dict[Grupo, list[Registro]] = defaultdict(list)
    for r in registros:
        grupos[(r.conjunto, r.caso, r.agente)].append(r)
    return grupos


def _evidencia(registros: Sequence[Registro]) -> tuple[str, ...]:
    return tuple(sorted(caminho_execucao(Path(), r).as_posix() for r in registros))


def _regra_do_grupo(
    conjunto: str, base: Sequence[Registro] | None
) -> tuple[Regra, Callable[[int, int], bool]] | None:
    if conjunto == "deterministica":
        return "deterministica", lambda passou, falhou: falhou > 0
    if base is None:
        return None
    base_passava = maioria_passou([r.estado for r in base])
    if conjunto == "tools":
        return (
            "regressao_tool",
            lambda passou, falhou: base_passava and not _maioria(passou, falhou),
        )
    return (
        "regressao_maioria",
        lambda passou, falhou: base_passava and _maioria(falhou, passou),
    )


def decidir(alvo: Sequence[Registro], base: Sequence[Registro] | None) -> Decisao:
    """Decide a rodada. Com `base=None` não há baseline: `sem_base` e `ausentes` ficam vazios."""
    for r in (*alvo, *(base or ())):
        if r.conjunto not in CONJUNTOS:
            raise ValueError(f"conjunto desconhecido: {r.conjunto!r}")
    grupos_base = _agrupar(base) if base is not None else {}
    bloqueios: list[Bloqueio] = []
    inconclusivos: list[str] = []
    pulados: list[str] = []
    sem_base: list[str] = []

    for grupo, registros in sorted(_agrupar(alvo).items()):
        conjunto, caso, agente = grupo
        identificador = "/".join(grupo)
        estados = [r.estado for r in registros]
        if all(e == "pulado" for e in estados):
            pulados.append(identificador)
            continue
        registros_base = grupos_base.get(grupo)
        if conjunto != "deterministica" and base is not None and registros_base is None:
            sem_base.append(identificador)
            continue
        regra = _regra_do_grupo(conjunto, registros_base)
        if regra is None:
            continue
        nome, bloqueia = regra
        passou = estados.count("passou")
        falhou = estados.count("falhou")
        infra = estados.count("erro_infra")
        if bloqueia(passou + infra, falhou):
            bloqueios.append(Bloqueio(nome, conjunto, caso, agente, _evidencia(registros)))
        elif bloqueia(passou, falhou + infra):
            inconclusivos.append(identificador)

    grupos_alvo = _agrupar(alvo)
    ausentes = sorted(
        "/".join(grupo)
        for grupo, registros in grupos_base.items()
        if grupo[0] in ("tools", "usuario")
        and grupo not in grupos_alvo
        and maioria_passou([r.estado for r in registros])
    )

    if bloqueios:
        veredito: Veredito = "no-go"
    elif inconclusivos or ausentes:
        veredito = "inconclusivo"
    else:
        veredito = "go"
    return Decisao(
        veredito=veredito,
        bloqueios=tuple(bloqueios),
        inconclusivos=tuple(inconclusivos),
        pulados=tuple(pulados),
        sem_base=tuple(sem_base),
        ausentes=tuple(ausentes),
    )


def com_incompleto(decisao: Decisao, incompleto: Sequence[str]) -> Decisao:
    """Registra o que falta na rodada; com falta, um `go` vira `inconclusivo`.

    Um `no-go` fica: a falha que bloqueou foi observada, e a falta de outras execuções não a
    desfaz (a determinística que falha para a rodada antes dos agentes).
    """
    if not incompleto:
        return decisao
    veredito: Veredito = "no-go" if decisao.veredito == "no-go" else "inconclusivo"
    return replace(decisao, veredito=veredito, incompleto=tuple(incompleto))
