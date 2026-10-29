"""Linha de comando da bateria: `python -m tests.e2e <subcomando>`."""

from __future__ import annotations

import argparse
import json
import os
import sys

from tests.e2e.config import avisos, carregar_config, verificar
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
    relevantes = {"motor", *(ITENS_DO_AGENTE[a] for a in agentes)}
    problemas = [p for p in verificar(cfg) if p.item in relevantes]
    for problema in problemas:
        print(f"problema [{problema.item}]: {problema.mensagem}")
    if problemas:
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
    except FalhaPreparo as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cfg = carregar_config(os.environ)
    if args.subcomando == "verificar":
        return _verificar(cfg)
    return _preparar(cfg, args.mcp, args.agentes)


if __name__ == "__main__":
    sys.exit(main())
