"""Juiz: nota 0–2 para a resposta de cada conversa, contra o gabarito do cenário.

Roda o Claude num container descartável, com o endurecimento e o secret do executor, sem o
caso, sem a home de quem roda e sem MCP: o juiz só lê o texto. O modelo é fixado por
`--model`; o CLI do Claude não tem opção de temperatura, então a pedida vai só para o
manifesto, marcada como não aplicada.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from tests.e2e.config import Config
from tests.e2e.conjuntos.usuario.cenario import Cenario
from tests.e2e.executor.container import (
    Execucao,
    comando,
    encerrar_container,
    limite_atingido,
    nome_container,
    rodar_container,
)
from tests.e2e.executor.eventos import ler_claude
from tests.e2e.executor.imagens import ConfigMCP, tag_imagem

TENTATIVAS = 2
TEMPO_JUIZ = 600
LIMITE_RESPOSTA = 20000
MCP_VAZIO = '{"mcpServers": {}}'
NOTAS = (0, 1, 2)
_NOTA_JSON = re.compile(r"\{[^{}]*\"nota\"[^{}]*\}")

CRITERIO = """Você é avaliador de respostas de um assistente de IA para estudos de planejamento \
da operação do sistema elétrico (modelo novomodelo, sucessor do NEWAVE). Avalie SÓ a resposta \
abaixo, contra o pedido e o gabarito. Notas:
2 = resolve o pedido, com os fatos do gabarito certos (números dentro da tolerância) e sem \
afirmações falsas;
1 = parcial: resolve parte, ou acerta com imprecisão relevante, ou pede algo à pessoa que não \
era necessário;
0 = não resolve, erra os fatos centrais, inventa dados ou se recusa sem motivo.
Pedir permissão para algo que o pedido exige (ex.: rodar um caso, ler fora da pasta) não reduz \
a nota se a resposta explica o que falta e o que foi feito até ali.
Responda APENAS um JSON numa linha: {"nota": 0|1|2, "justificativa": "<uma ou duas frases>"}"""


@dataclass(frozen=True)
class Juiz:
    modelo: str
    temperatura: float


JUIZ_PADRAO = Juiz("claude-sonnet-5-5", 0.0)


class FalhaJuiz(RuntimeError):
    """O juiz não deu uma nota válida nas tentativas; a execução vira `erro_infra`."""


def imagem_padrao() -> str:
    return tag_imagem(ConfigMCP("sem-mcp", None), "claude")


def no_manifesto(j: Juiz) -> dict[str, str]:
    """O que o manifesto registra do juiz: o modelo fixado e a temperatura, não aplicada."""
    return {
        "juiz_modelo": j.modelo,
        "juiz_temperatura": (
            f"padrão do CLI (pedida {j.temperatura}; o CLI do Claude não tem opção de temperatura)"
        ),
    }


def prompt(cen: Cenario, resposta: str) -> str:
    gabarito = (
        cen.gabarito
        or "(sem gabarito específico: julgue se a resposta resolve o pedido com dados reais)"
    )
    return (
        f"{CRITERIO}\n\n## Pedido\n{cen.pedido}\n\n## Gabarito\n{gabarito}\n\n"
        f"## Resposta do assistente\n{resposta[:LIMITE_RESPOSTA]}"
    )


def comando_juiz(j: Juiz, texto: str, cfg: Config, imagem: str, nome: str) -> list[str]:
    """O `comando` do executor sem caso, com o pedido trocado pelo do juiz.

    Raises:
        ComandoRecusado: o executor recusa o motor ou a memória configurada.
    """
    e = _execucao(texto, imagem)
    base = comando(e, cfg, Path(), nome)
    return [
        *base[: base.index(imagem) + 1],
        "claude",
        "-p",
        texto,
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        j.modelo,
        "--strict-mcp-config",
        "--mcp-config",
        MCP_VAZIO,
    ]


def _execucao(texto: str, imagem: str, tentativa: int = 1) -> Execucao:
    return Execucao(
        conjunto="usuario",
        caso="juiz",
        agente="claude",
        config="juiz",
        repeticao=tentativa,
        pedido=texto,
        caso_origem=None,
        somente_leitura=True,
        timeout_s=TEMPO_JUIZ,
        imagem=imagem,
    )


def _ler_nota(linhas: list[str]) -> dict | None:
    fim = next((e for e in reversed(ler_claude(linhas).eventos) if e.tipo == "fim"), None)
    if fim is None or fim.erro:
        return None
    achado = _NOTA_JSON.search(str(fim.dados.get("resposta", "")))
    if not achado:
        return None
    try:
        dados = json.loads(achado.group(0))
    except ValueError:
        return None
    if dados.get("nota") not in NOTAS or isinstance(dados.get("nota"), bool):
        return None
    return {"nota": dados["nota"], "justificativa": str(dados.get("justificativa", ""))}


def julgar(j: Juiz, c: Cenario, resposta: str, cfg: Config, *, imagem: str | None = None) -> dict:
    """`{"nota", "justificativa"}` do juiz; uma falha ganha uma nova tentativa.

    Raises:
        FalhaJuiz: as duas tentativas falharam (sem nota válida, tempo esgotado, limite
            de uso ou container que saiu com erro).
        ComandoRecusado: o executor recusa o motor ou a memória configurada.
    """
    imagem = imagem or imagem_padrao()
    texto = prompt(c, resposta)
    motivos = []
    for tentativa in range(1, TENTATIVAS + 1):
        nome = nome_container(_execucao(texto, imagem, tentativa), "juiz")
        cmd = comando_juiz(j, texto, cfg, imagem, nome)
        try:
            saida = rodar_container(cmd, TEMPO_JUIZ)
        finally:
            encerrar_container(cfg.motor, nome)
        if saida.estourou:
            motivos.append("tempo esgotado")
        elif limite_atingido(saida.linhas, saida.stderr):
            motivos.append("limite de uso do agente atingido")
        elif (nota := _ler_nota(saida.linhas)) is not None:
            return nota
        else:
            motivos.append(f"sem nota válida (código {saida.codigo})")
    raise FalhaJuiz(f"juiz sem resposta depois de {TENTATIVAS} tentativas: {'; '.join(motivos)}")
