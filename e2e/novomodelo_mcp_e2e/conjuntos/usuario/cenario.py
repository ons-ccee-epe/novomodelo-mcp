"""Cenários do conjunto usuário: um arquivo TOML por cenário, com o caso por nome lógico."""

from __future__ import annotations

import fnmatch
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from novomodelo_mcp_e2e.config import Config
from novomodelo_mcp_e2e.executor.casos import CASOS_GRANDES, PUBLICOS

Persona = Literal["consultoria", "iniciante", "instalacao"]
PASTA_CENARIOS = Path(__file__).with_name("cenarios")
TIMEOUT_PADRAO = 900
_OBRIGATORIOS = ("id", "persona", "pedido", "tools_esperadas")


@dataclass(frozen=True)
class Cenario:
    id: str
    persona: Persona
    pedido: str
    tools_esperadas: tuple[str, ...]
    caso: str | None = None
    contorno: tuple[str, ...] = ()
    checagem: dict | None = None
    timeout_s: int = TIMEOUT_PADRAO
    inicio: Literal["limpa", "instalada"] = "instalada"
    somente_leitura: bool = False
    montar_em: str = "/estudos"
    nativas_esperadas: tuple[str, ...] = ()
    primeira_aceita: tuple[str, ...] = ()
    tools_alternativas: tuple[str, ...] = ()
    acerto_pela_resposta: bool = False
    sem_output: bool = False
    juiz_ve_tools: bool = False
    gabarito: str = ""


class CenarioInvalido(ValueError):
    """O arquivo do cenário não tem o formato esperado."""


def ler_cenario(arquivo: Path) -> Cenario:
    """Lê um cenário; o `caso` é sempre um nome lógico conhecido ou ausente.

    Raises:
        CenarioInvalido: falta um campo obrigatório ou o caso não é um nome lógico conhecido.
    """
    dados = tomllib.loads(arquivo.read_text(encoding="utf-8"))
    faltam = [c for c in _OBRIGATORIOS if c not in dados]
    if faltam:
        raise CenarioInvalido(f"{arquivo.name}: faltam os campos {', '.join(faltam)}")
    caso = dados.get("caso")
    if caso is not None and caso not in PUBLICOS | CASOS_GRANDES:
        raise CenarioInvalido(f"{arquivo.name}: caso {caso!r} não é um nome lógico conhecido")
    return Cenario(
        id=dados["id"],
        persona=dados["persona"],
        pedido=dados["pedido"].strip(),
        tools_esperadas=tuple(dados["tools_esperadas"]),
        caso=caso,
        contorno=tuple(dados.get("contorno", ())),
        checagem=dados.get("checagem"),
        timeout_s=int(dados.get("timeout_s", TIMEOUT_PADRAO)),
        inicio=dados.get("inicio", "instalada"),
        somente_leitura=bool(dados.get("somente_leitura", False)),
        montar_em=dados.get("montar_em", "/estudos"),
        nativas_esperadas=tuple(dados.get("nativas_esperadas", ())),
        primeira_aceita=tuple(dados.get("primeira_aceita", ())),
        tools_alternativas=tuple(dados.get("tools_alternativas", ())),
        acerto_pela_resposta=bool(dados.get("acerto_pela_resposta", False)),
        sem_output=bool(dados.get("sem_output", False)),
        juiz_ve_tools=bool(dados.get("juiz_ve_tools", False)),
        gabarito=dados.get("gabarito", "").strip(),
    )


def carregar_cenarios(pastas: Sequence[Path], filtro: str | None = None) -> list[Cenario]:
    """Os cenários de todas as pastas, ordenados por id; `filtro` aceita padrões com vírgula.

    Raises:
        CenarioInvalido: um cenário inválido ou o mesmo id em dois arquivos.
    """
    por_id: dict[str, Path] = {}
    cenarios = []
    for pasta in pastas:
        for arquivo in sorted(pasta.glob("*.toml")):
            c = ler_cenario(arquivo)
            if c.id in por_id:
                raise CenarioInvalido(f"id {c.id!r} repetido: {por_id[c.id].name} e {arquivo.name}")
            por_id[c.id] = arquivo
            cenarios.append(c)
    if filtro:
        padroes = [f.strip() for f in filtro.split(",") if f.strip()]
        cenarios = [c for c in cenarios if any(fnmatch.fnmatch(c.id, p) for p in padroes)]
    return sorted(cenarios, key=lambda c: c.id)


def cenarios_da_rodada(
    cfg: Config, filtro: str | None = None, repo: Path = PASTA_CENARIOS
) -> tuple[list[Cenario], int]:
    """Os cenários do repo e os da pasta externa, se configurada, e quantos vieram de fora."""
    pastas = [repo] if cfg.cenarios_extra is None else [repo, cfg.cenarios_extra]
    cenarios = carregar_cenarios(pastas, filtro)
    de_fora = (
        0
        if cfg.cenarios_extra is None
        else len({c.id for c in carregar_cenarios([cfg.cenarios_extra], filtro)})
    )
    return cenarios, de_fora
