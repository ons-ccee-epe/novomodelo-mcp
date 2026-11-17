#!/usr/bin/env python3
"""Atualiza o snapshot embutido (docs + schemas + manifesto + índice) em _bundled/.

A fonte é um clone local do `novomodelo-docs`. As páginas saem resolvidas (trechos
`_impl` incluídos, marcação MDX retirada), e o diff mostra exatamente o que mudou.
A preparação das páginas é a de `novomodelo_mcp.adapters.reference`, a mesma que o
servidor usa no modo de desenvolvimento.

Os changelogs do novomodelo e do bridge (`--changelog <produto>=<clone>`) viram uma
página cada, `changelog/<produto>`, com uma seção `## <versão>` por versão a partir de
`CHANGELOG_DESDE`, para o agente ler só a versão que interessa.

Uso (a partir do repositório):
    uv run python scripts/sync_bundled.py --source <clone do novomodelo-docs> \
        --changelog novomodelo=<clone> --changelog novomodelo-bridge=<clone>
    uv run python scripts/sync_bundled.py --source <clone> ... --check   # CI: sai 1 se divergir

Nada é baixado da rede: a fonte é sempre um diretório local.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from novomodelo_mcp.adapters.reference import (  # noqa: E402
    INDEX_FILE,
    MANIFEST_FILE,
    build_docs_index,
    iter_doc_pages,
    resolve_mdx,
)

_PKG_BUNDLED = _ROOT / "src" / "novomodelo_mcp" / "_bundled"
_DOCS_SUBPATH = Path("src") / "content" / "docs"
_SCHEMAS_SUBPATH = Path("public") / "schemas"
CHANGELOG_PRODUTOS = ("novomodelo", "novomodelo-bridge")
CHANGELOG_DESDE = "0.18.0"
_VERSAO = re.compile(r"^## \[(?P<versao>\d+\.\d+\.\d+[^\]\s]*)\](?:\s*-\s*(?P<data>\S+))?\s*$")


def _chave(versao: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", versao)[:3])


def _secoes_de_versao(texto: str, desde: str) -> list[tuple[str, str | None, list[str]]]:
    secoes: list[tuple[str, str | None, list[str]]] = []
    atual: list[str] | None = None
    for linha in texto.splitlines():
        if linha.startswith("# ") and secoes:
            break
        if linha.startswith("## "):
            m = _VERSAO.match(linha)
            atual = None
            if m and _chave(m["versao"]) >= _chave(desde):
                atual = []
                secoes.append((m["versao"], m["data"], atual))
            continue
        if atual is not None:
            atual.append(linha)
    return secoes


def changelog_page(produto: str, texto: str, desde: str = CHANGELOG_DESDE) -> str:
    """A página `changelog/<produto>`: uma seção `## <versão>` por versão >= `desde`."""
    partes = [
        f"---\ntitle: {produto} changelog\ndescription: What changed in each {produto} "
        f"release, from {desde} on.\n---\n"
    ]
    for versao, data, corpo in _secoes_de_versao(texto, desde):
        cabeca = f"## {versao}\n\nReleased {data}." if data else f"## {versao}"
        partes.append(f"{cabeca}\n\n" + "\n".join(corpo).strip() + "\n")
    return "\n".join(partes)


def changelog_versions(texto: str, desde: str = CHANGELOG_DESDE) -> list[str]:
    return [versao for versao, _, _ in _secoes_de_versao(texto, desde)]


def version_section(texto: str, versao: str) -> str | None:
    """O corpo da seção `## [versao]`, sem o título; None sem a seção ou com ela vazia."""
    for v, _, corpo in _secoes_de_versao(texto, versao):
        if v == versao:
            return "\n".join(corpo).strip() or None
    return None


def _docs_version(source: Path) -> str | None:
    try:
        latest = json.loads((source / "versions.json").read_text(encoding="utf-8"))["latest"]
        return str(latest["novomodelo"]).lstrip("vV")
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _git_commit(source: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def generate(source: Path, dest: Path, changelogs: dict[str, Path] | None = None) -> dict:
    """Grava docs resolvidas, changelogs, schemas, índice e manifesto em `dest`; devolve o
    manifesto."""
    docs_src, schemas_src = source / _DOCS_SUBPATH, source / _SCHEMAS_SUBPATH
    for sub in ("docs", "schemas"):
        if (dest / sub).exists():
            shutil.rmtree(dest / sub)
    pages = iter_doc_pages(docs_src)
    for _page, path in pages:
        target = dest / "docs" / path.relative_to(docs_src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(resolve_mdx(path), encoding="utf-8")
    origens = {}
    for produto, clone in sorted((changelogs or {}).items()):
        texto = (clone / "CHANGELOG.md").read_text(encoding="utf-8")
        target = dest / "docs" / "changelog" / f"{produto}.mdx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(changelog_page(produto, texto), encoding="utf-8")
        origens[produto] = {"commit": _git_commit(clone), "versoes": changelog_versions(texto)}
    (dest / "schemas").mkdir(parents=True, exist_ok=True)
    for f in sorted(schemas_src.glob("*.schema.json")):
        shutil.copy2(f, dest / "schemas" / f.name)
    index = dest / INDEX_FILE
    index.unlink(missing_ok=True)
    con = build_docs_index(dest / "docs", index)
    sections = con.execute(
        "SELECT (SELECT count(*) FROM secoes) + (SELECT count(*) FROM changelog)"
    ).fetchone()[0]
    con.execute("INSERT INTO secoes(secoes) VALUES('optimize')")
    con.execute("INSERT INTO changelog(changelog) VALUES('optimize')")
    con.commit()
    con.execute("VACUUM")
    con.close()
    manifest = {
        "docs_versao": _docs_version(source),
        "docs_commit": _git_commit(source),
        "gerado_em": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "paginas": len(pages) + len(origens),
        "secoes": sections,
    }
    if origens:
        manifest["changelogs"] = origens
    (dest / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def _files(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for sub in ("docs", "schemas")
        if (root / sub).is_dir()
        for p in sorted((root / sub).rglob("*"))
        if p.is_file()
    }


def _index_rows(path: Path) -> list:
    if not path.is_file():
        return []
    con = sqlite3.connect(str(path))
    try:
        return [
            con.execute(q).fetchall()
            for q in (
                "SELECT pagina, titulo, ancora, texto FROM secoes ORDER BY pagina, rowid",
                "SELECT pagina, titulo, ancora, texto FROM changelog ORDER BY pagina, rowid",
                "SELECT * FROM paginas ORDER BY pagina",
                "SELECT * FROM glossario ORDER BY pt, en",
            )
        ]
    finally:
        con.close()


def differences(expected: Path, current: Path) -> list[str]:
    """O que difere entre o que o sync geraria (`expected`) e o embutido (`current`)."""
    want, have = _files(expected), _files(current)
    diffs = [f"diferente: {k}" for k in sorted(want.keys() & have.keys()) if want[k] != have[k]]
    diffs += [f"falta no embutido: {k}" for k in sorted(want.keys() - have.keys())]
    diffs += [f"sobra no embutido: {k}" for k in sorted(have.keys() - want.keys())]
    if _index_rows(expected / INDEX_FILE) != _index_rows(current / INDEX_FILE):
        diffs.append(f"diferente: {INDEX_FILE}")

    def _manifest(root):
        try:
            data = json.loads((root / MANIFEST_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        data.pop("gerado_em", None)
        return data

    if _manifest(expected) != _manifest(current):
        diffs.append(f"diferente: {MANIFEST_FILE}")
    return diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", required=True, type=Path, help="Raiz do clone do novomodelo-docs.")
    ap.add_argument(
        "--dest",
        type=Path,
        default=_PKG_BUNDLED,
        help="Pasta de destino (padrão: src/novomodelo_mcp/_bundled).",
    )
    ap.add_argument(
        "--changelog",
        action="append",
        default=[],
        metavar="PRODUTO=CLONE",
        help=f"Clone com o CHANGELOG.md de um produto ({', '.join(CHANGELOG_PRODUTOS)}).",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Não grava: sai 1 se o destino divergir do que seria gerado.",
    )
    args = ap.parse_args(argv)
    changelogs: dict[str, Path] = {}
    for item in args.changelog:
        produto, _, clone = item.partition("=")
        path = Path(clone).expanduser().resolve()
        if produto not in CHANGELOG_PRODUTOS or not (path / "CHANGELOG.md").is_file():
            print(
                f"erro: --changelog {item}: produto em {CHANGELOG_PRODUTOS} e clone com "
                "CHANGELOG.md",
                file=sys.stderr,
            )
            return 2
        changelogs[produto] = path

    source: Path = args.source.expanduser().resolve()
    for sub in (_DOCS_SUBPATH, _SCHEMAS_SUBPATH):
        if not (source / sub).is_dir():
            print(f"erro: {source / sub} não existe", file=sys.stderr)
            return 2
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            generate(source, Path(tmp), changelogs)
            diffs = differences(Path(tmp), args.dest.resolve())
        for d in diffs:
            print(d)
        print("embutido igual à fonte" if not diffs else f"{len(diffs)} diferença(s)")
        return 1 if diffs else 0
    manifest = generate(source, args.dest.resolve(), changelogs)
    print(
        f"snapshot atualizado: {manifest['paginas']} páginas, {manifest['secoes']} seções, "
        f"docs {manifest['docs_versao']} @ {manifest['docs_commit']} -> {args.dest}"
    )
    return 0 if manifest["paginas"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
