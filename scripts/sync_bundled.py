#!/usr/bin/env python3
"""Atualiza o snapshot embutido (docs + schemas) em src/cobre_mcp/_bundled/.

O snapshot é vendored no repositório para que as tools ``docs_*``/``schema_*``
funcionem offline no primeiro uso. Este script re-sincroniza esse snapshot a
partir de uma fonte local (um clone do repo do site cobre-docs, ou a pasta
``docs/`` do site), de forma consciente e revisável — o diff resultante mostra
exatamente o que mudou.

Uso:
    python scripts/sync_bundled.py --source <dir>

``<dir>`` é a raiz do site de documentação (o que hoje corresponde à pasta
``docs/``). O script procura:
  * docs:    <source>/src/content/docs/**/*.md,*.mdx
  * schemas: <source>/public/schemas/*.schema.json

Nada é baixado da rede: a fonte é sempre um diretório local.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_PKG_BUNDLED = Path(__file__).resolve().parents[1] / "src" / "cobre_mcp" / "_bundled"
_DOCS_SUBPATH = Path("src") / "content" / "docs"
_SCHEMAS_SUBPATH = Path("public") / "schemas"


def _copy_tree(src: Path, dst: Path, patterns: tuple[str, ...]) -> int:
    """Copia arquivos que casam com *patterns* de *src* para *dst* (recursivo).

    Limpa *dst* antes, preservando a árvore relativa. Retorna a contagem.
    """
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for pat in patterns:
        for f in src.rglob(pat):
            if not f.is_file():
                continue
            rel = f.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, type=Path,
                    help="Raiz do site de documentação (ex.: a pasta docs/).")
    args = ap.parse_args(argv)

    source: Path = args.source.expanduser().resolve()
    if not source.is_dir():
        print(f"erro: fonte inexistente ou não é diretório: {source}", file=sys.stderr)
        return 2

    docs_src = source / _DOCS_SUBPATH
    schemas_src = source / _SCHEMAS_SUBPATH
    if not docs_src.is_dir():
        print(f"erro: docs não encontrados em {docs_src}", file=sys.stderr)
        return 2
    if not schemas_src.is_dir():
        print(f"erro: schemas não encontrados em {schemas_src}", file=sys.stderr)
        return 2

    n_docs = _copy_tree(docs_src, _PKG_BUNDLED / "docs", ("*.md", "*.mdx"))
    n_schemas = _copy_tree(schemas_src, _PKG_BUNDLED / "schemas", ("*.schema.json",))

    print(f"snapshot atualizado: {n_docs} docs, {n_schemas} schemas -> {_PKG_BUNDLED}")
    if n_docs == 0 or n_schemas == 0:
        print("aviso: contagem zero em docs ou schemas — verifique a fonte.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
