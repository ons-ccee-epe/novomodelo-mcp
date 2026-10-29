"""Linha de comando da bateria: `python -m tests.e2e <subcomando>`."""

from __future__ import annotations

import argparse
import json
import os
import sys

from novomodelo_mcp.adapters.versions import expected_version
from tests.e2e import rodada
from tests.e2e.config import avisos, carregar_config, verificar
from tests.e2e.executor.casos import CASOS_GRANDES, pasta_preparados, preparar_publicos, resolver
from tests.e2e.executor.container import SEGREDO_CLAUDE
from tests.e2e.executor.imagens import (
    CLIENTES,
    ConfigMCP,
    FalhaPreparo,
    aviso_do_bridge,
    construir,
    criar_segredo,
    ler_config_mcp,
    tag_imagem,
)

ITENS_DO_AGENTE = {"claude": "token_claude", "kiro": "volume_kiro"}


def _config_mcp(valor: str) -> ConfigMCP:
    try:
        return ler_config_mcp(valor)
    except ValueError as erro:
        raise argparse.ArgumentTypeError(str(erro)) from None


def _agentes(valor: str) -> list[str]:
    nomes = [n.strip() for n in valor.split(",") if n.strip()]
    desconhecidos = [n for n in nomes if n not in CLIENTES]
    if not nomes or desconhecidos:
        raise argparse.ArgumentTypeError(
            f"agentes válidos: {', '.join(CLIENTES)}; recebido: {valor!r}"
        )
    return list(dict.fromkeys(nomes))


def _conjuntos(valor: str) -> list[str]:
    nomes = [n.strip() for n in valor.split(",") if n.strip()]
    desconhecidos = [n for n in nomes if n not in rodada.CONJUNTOS_COM_AGENTE]
    if not nomes or desconhecidos:
        raise argparse.ArgumentTypeError(
            f"conjuntos válidos: {', '.join(rodada.CONJUNTOS_COM_AGENTE)}; recebido: {valor!r}"
        )
    return list(dict.fromkeys(nomes))


def _nao_negativo(valor: str) -> int:
    try:
        numero = int(valor)
    except ValueError:
        numero = -1
    if numero < 0:
        raise argparse.ArgumentTypeError(f"inteiro >= 0 esperado: {valor!r}")
    return numero


def _positivo(valor: str) -> int:
    numero = _nao_negativo(valor)
    if numero == 0:
        raise argparse.ArgumentTypeError(f"inteiro >= 1 esperado: {valor!r}")
    return numero


def _origem(valor: str) -> tuple[str, str]:
    nome, sep, texto = valor.partition("=")
    if not sep or not nome.strip() or not texto.strip():
        raise argparse.ArgumentTypeError(f"formato <config>=<texto>: {valor!r}")
    return nome.strip(), texto.strip()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m tests.e2e", description=__doc__)
    sub = p.add_subparsers(dest="subcomando", required=True)
    sub.add_parser("verificar", help="confere motor, pastas, token e volume do Kiro")
    prep = sub.add_parser("preparar", help="constrói as imagens e cria o secret do token")
    prep.add_argument(
        "--mcp",
        nargs="+",
        required=True,
        type=_config_mcp,
        metavar="sem|WHEEL",
        help="'sem' ou o caminho de uma wheel do novomodelo-mcp; repita para várias",
    )
    prep.add_argument("--agentes", type=_agentes, default=list(CLIENTES), help="claude,kiro")
    rod = sub.add_parser(
        "rodar",
        help="determinística e conjuntos com agente; retomável",
        description=(
            "Saída: 0 completa; 1 determinística com falha ou imagem não pronta; "
            "2 argumentos ou retomada recusada; 3 segredo na pasta da rodada; "
            "4 limite de uso; 5 orçamento estourado."
        ),
    )
    rod.add_argument("--rodada", metavar="ID", help="cria ou retoma esta rodada")
    rod.add_argument(
        "--mcp",
        nargs="+",
        required=True,
        type=_config_mcp,
        metavar="sem|WHEEL",
        help="'sem' ou o caminho de uma wheel do novomodelo-mcp; repita para várias",
    )
    rod.add_argument(
        "--origem-mcp",
        action="append",
        type=_origem,
        default=[],
        metavar="CONFIG=TEXTO",
        help="de onde veio a wheel da configuração (release, commit); repetível",
    )
    rod.add_argument(
        "--conjuntos",
        type=_conjuntos,
        default=list(rodada.CONJUNTOS_COM_AGENTE),
        help="tools,usuario",
    )
    rod.add_argument("--filtro", metavar="PADRÕES", help="ids de caso ou cenário, com vírgula")
    rod.add_argument("--agentes", type=_agentes, default=list(CLIENTES), help="claude,kiro")
    rod.add_argument("--repeticoes", type=_positivo, default=3)
    rod.add_argument("--completa", action="store_true", help="acrescenta a configuração sem MCP")
    rod.add_argument(
        "--max-execucoes",
        type=_nao_negativo,
        default=rodada.ORCAMENTO_PADRAO.max_execucoes,
        help="0 é sem limite",
    )
    rod.add_argument(
        "--max-minutos",
        type=_nao_negativo,
        default=rodada.ORCAMENTO_PADRAO.max_minutos,
        help="0 é sem limite",
    )
    rod.add_argument(
        "--esperar-limite",
        type=_positivo,
        metavar="MINUTOS",
        help="no limite de uso, espera e retoma sozinha em vez de sair com 4",
    )
    rod.add_argument("--paralelo-por-agente", type=_positivo, default=3)
    return p


def _verificar(cfg) -> int:
    problemas = verificar(cfg)
    for problema in problemas:
        print(f"problema [{problema.item}]: {problema.mensagem}")
    for aviso in avisos(cfg):
        print(f"aviso: {aviso}")
    if not problemas:
        print("ambiente pronto")
    return 1 if problemas else 0


def _preparar(cfg, configs: list[ConfigMCP], agentes: list[str]) -> int:
    relevantes = {"motor", "cache", *(ITENS_DO_AGENTE[a] for a in agentes)}
    problemas = [p for p in verificar(cfg) if p.item in relevantes]
    for problema in problemas:
        print(f"problema [{problema.item}]: {problema.mensagem}")
    if problemas:
        return 1
    versao = expected_version()
    if versao is None:
        print(
            "erro: pin do novomodelo-bridge ausente nos metadados do novomodelo-mcp",
            file=sys.stderr,
        )
        return 1
    try:
        if "claude" in agentes:
            criar_segredo(cfg)
            print(f"secret {SEGREDO_CLAUDE} criado a partir do arquivo de token", flush=True)
        for c in configs:
            if aviso := aviso_do_bridge(c):
                print(f"aviso: {aviso}", flush=True)
            for agente in agentes:
                versoes = construir(c, agente, cfg)
                linha = {"imagem": tag_imagem(c, agente), "versoes": versoes}
                print(json.dumps(linha, ensure_ascii=False), flush=True)
        primeira = tag_imagem(configs[0], agentes[0])
        preparados = preparar_publicos(versao, primeira, cfg)
        print(json.dumps({"casos_publicos": preparados}, ensure_ascii=False), flush=True)
        grandes = {
            nome: "disponivel" if resolver(nome, cfg, pasta_preparados(cfg)) else "ausente"
            for nome in sorted(CASOS_GRANDES)
        }
        print(json.dumps({"casos_grandes": grandes}, ensure_ascii=False), flush=True)
    except FalhaPreparo as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    return 0


def _configs_da_rodada(args) -> list[ConfigMCP]:
    configs = list(args.mcp)
    if args.completa:
        configs.append(ler_config_mcp("sem"))
    return list({c.nome: c for c in configs}.values())


def _rodar(cfg, args, parser: argparse.ArgumentParser) -> int:
    configs = _configs_da_rodada(args)
    com_wheel = {c.nome for c in configs if c.wheel is not None}
    origens = dict(args.origem_mcp)
    if desconhecidas := sorted(set(origens) - com_wheel):
        parser.error(f"--origem-mcp sem wheel correspondente: {', '.join(desconhecidas)}")
    relevantes = {
        "motor",
        "cache",
        "resultados",
        "casos",
        "cenarios_extra",
        *(ITENS_DO_AGENTE[a] for a in args.agentes),
    }
    if "usuario" in args.conjuntos:
        relevantes.add(ITENS_DO_AGENTE["claude"])
    problemas = [p for p in verificar(cfg) if p.item in relevantes]
    for problema in problemas:
        print(f"problema [{problema.item}]: {problema.mensagem}")
    if problemas:
        return 1
    try:
        pasta = rodada.rodar(
            args.rodada,
            configs,
            args.conjuntos,
            args.agentes,
            args.repeticoes,
            cfg,
            rodada.Orcamento(args.max_execucoes, args.max_minutos),
            args.paralelo_por_agente,
            filtro=args.filtro,
            completa=args.completa,
            origens=origens,
            esperar_limite_min=args.esperar_limite,
        )
    except rodada.RodadaInterrompida as erro:
        if erro.pasta is not None:
            print(f"rodada: {erro.pasta}", flush=True)
        print(f"erro: {erro}", file=sys.stderr)
        return erro.codigo
    print(f"rodada: {pasta}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    cfg = carregar_config(os.environ)
    if args.subcomando == "verificar":
        return _verificar(cfg)
    if args.subcomando == "rodar":
        return _rodar(cfg, args, parser)
    return _preparar(cfg, args.mcp, args.agentes)


if __name__ == "__main__":
    sys.exit(main())
