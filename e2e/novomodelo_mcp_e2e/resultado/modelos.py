"""Modelos do resultado da bateria e sua conversão de e para JSON."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSAO = 1

Estado = Literal["passou", "falhou", "pulado", "erro_infra"]
Conjunto = Literal["deterministica", "tools", "usuario"]


class VersaoDesconhecida(ValueError):
    """O arquivo declara uma versão de schema que este leitor não conhece."""


def _como_json(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: _como_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_como_json(v) for v in valor]
    return valor


@dataclass(frozen=True)
class ChamadaTool:
    nome: str
    ok: bool | None
    duracao_s: float | None


@dataclass(frozen=True)
class Metricas:
    """Métricas da pontuação de uma execução; `None` é métrica que o conjunto não calcula."""

    acerto_tool: bool | None = None
    contornos: int | None = None
    aprovacoes: int | None = None
    rigidez: int | None = None
    erros_envelope: int | None = None
    t_primeira_tool: float | None = None
    t_total: float | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    resposta_correta: bool | None = None
    interrupcoes: int | None = None
    t_primeira_interrupcao: float | None = None
    maior_trecho_sem_interrupcao: float | None = None
    indice_autonomia: float | None = None
    comandos_terminal: int | None = None
    nota_juiz: int | None = None


@dataclass(frozen=True)
class Avaliacao:
    """O que `avaliar` devolve ao executor: o veredito e as métricas que ele calcula."""

    estado: Estado
    motivo: str
    metricas: Metricas = Metricas()


@dataclass(frozen=True)
class Registro:
    rodada: str
    conjunto: Conjunto
    caso: str
    agente: str
    config: str
    repeticao: int
    estado: Estado
    motivo: str
    tools: tuple[ChamadaTool, ...]
    duracao_s: float
    metricas: Metricas = Metricas()
    schema_versao: int = SCHEMA_VERSAO

    def para_dict(self) -> dict[str, Any]:
        return _como_json(asdict(self))

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Registro:
        campos = {
            **dados,
            "tools": tuple(ChamadaTool(**t) for t in dados["tools"]),
            "metricas": Metricas(**dados["metricas"]),
        }
        return cls(**campos)


@dataclass(frozen=True)
class Manifesto:
    rodada: str
    criado_em: str
    configs: tuple[str, ...]
    conjuntos: tuple[Conjunto, ...]
    agentes: tuple[str, ...]
    repeticoes: int
    flags: dict[str, bool]
    versoes: dict[str, str]
    commit_bateria: str
    wheels: dict[str, dict[str, str]] = field(default_factory=dict)
    imagens: dict[str, dict[str, str]] = field(default_factory=dict)
    filtro: str | None = None
    schema_versao: int = SCHEMA_VERSAO

    def para_dict(self) -> dict[str, Any]:
        return _como_json(asdict(self))

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Manifesto:
        campos = dict(dados)
        for nome in ("configs", "conjuntos", "agentes"):
            campos[nome] = tuple(campos[nome])
        return cls(**campos)
