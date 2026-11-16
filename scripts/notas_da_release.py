#!/usr/bin/env python3
"""Notas do release do GitHub: a linha de instalação e a seção `## [X.Y.Z]` do CHANGELOG.md.

A seção vai sem o título da versão, que já é o título do release. Sem a seção, ou com
ela vazia, sai com 1 e não escreve nada: o release.yml para antes de publicar.

Uso (a partir do repositório):
    python3 scripts/notas_da_release.py X.Y.Z [--changelog CHANGELOG.md] > notas.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sync_bundled import version_section

_ROOT = Path(__file__).resolve().parents[1]


def release_notes(versao: str, secao: str) -> str:
    return (
        f"MCP do novomodelo {versao}. Instale com `uv tool install novomodelo-mcp=={versao}`, "
        f"ou o wheel deste release, e confira os arquivos com o SHA256SUMS.\n\n{secao}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Notas do release do GitHub, tiradas do CHANGELOG.md."
    )
    parser.add_argument("versao", help="a versão do release, sem o v (ex.: 0.21.0)")
    parser.add_argument("--changelog", type=Path, default=_ROOT / "CHANGELOG.md")
    args = parser.parse_args(argv)
    try:
        texto = args.changelog.read_text(encoding="utf-8")
    except OSError as err:
        print(f"não foi possível ler {args.changelog}: {err}", file=sys.stderr)
        return 1
    secao = version_section(texto, args.versao)
    if not secao:
        print(
            f"{args.changelog} não tem a seção `## [{args.versao}]`, ou ela está vazia",
            file=sys.stderr,
        )
        return 1
    sys.stdout.write(release_notes(args.versao, secao))
    return 0


if __name__ == "__main__":
    sys.exit(main())
