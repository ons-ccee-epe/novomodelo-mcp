"""Referência: JSON Schemas de entrada e páginas de documentação (sem rede).

Fontes:
- schemas: `NOVOMODELO_MCP_SCHEMAS_DIR`, ou exportados sob demanda via `novomodelo schema export`.
- docs: as EMBUTIDAS no pacote (as da versão do MCP). `NOVOMODELO_MCP_DOCS_DIR` só serve
  para desenvolvimento das docs, e o `server_info` avisa quando ela está em uso.
Leitura confinada à raiz; conteúdo com teto. Sem regra de negócio.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import tempfile
import unicodedata
from importlib import resources
from pathlib import Path

from ..config import Settings
from .discovery import find_novomodelo
from .envelope import error
from .subproc import NO_WINDOW

_SCHEMA_EXPORT_CACHE: dict[str, str] = {}
_SUFFIX = ".schema.json"

#: `tipo` é o NOME de um schema, nunca um caminho: "D:x" passaria por uma checagem de
#: `/`, `\` e `..`, e no Windows a junção com a raiz iria para outro disco.
_SCHEMA_NAME = re.compile(r"^[A-Za-z0-9_]+$")

#: Subpacote que carrega o snapshot embutido (docs + schemas) no wheel.
_BUNDLED_PKG = "novomodelo_mcp._bundled"


def _bundled_dir(name: str) -> str | None:
    """Caminho absoluto de uma subpasta embutida (``docs`` | ``schemas``).

    Usa ``importlib.resources`` para localizar o conteudo empacotado, de modo a
    funcionar tanto num checkout quanto num wheel instalado. Retorna ``None`` se
    o snapshot embutido nao estiver presente.
    """
    try:
        root = resources.files(_BUNDLED_PKG) / name
    except (ModuleNotFoundError, TypeError):
        return None
    try:
        if root.is_dir():
            return str(root)
    except (OSError, AttributeError):
        return None
    return None


def _export_schemas(settings: Settings) -> str | None:
    """Exporta os schemas via `novomodelo schema export` para um cache temporário."""
    novomodelo = find_novomodelo(settings)
    if not novomodelo:
        return None
    cached = _SCHEMA_EXPORT_CACHE.get(novomodelo)
    if cached and Path(cached).is_dir():
        return cached
    out = Path(tempfile.gettempdir()) / "novomodelo_mcp_schemas"
    out.mkdir(parents=True, exist_ok=True)
    try:
        # argv fixa, sem shell: nada vem do agente.
        proc = (
            subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                [novomodelo, "--color", "never", "schema", "export", "--output-dir", str(out)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                **NO_WINDOW,
            )
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    _SCHEMA_EXPORT_CACHE[novomodelo] = str(out)
    return str(out)


def schemas_root(settings: Settings) -> str | None:
    """Raiz efetiva dos schemas (cascata; primeiro que existir vence).

    ``NOVOMODELO_MCP_SCHEMAS_DIR`` -> ``novomodelo schema export`` -> schemas EMBUTIDOS
    (``_bundled/schemas``). O embutido garante o caminho feliz offline.
    """
    return settings.schemas_dir or _export_schemas(settings) or _bundled_dir("schemas")


def list_schema_types(settings: Settings) -> list[str]:
    root = schemas_root(settings)
    if not root or not Path(root).is_dir():
        return []
    return sorted(p.name[: -len(_SUFFIX)] for p in Path(root).glob(f"*{_SUFFIX}"))


def read_schema(settings: Settings, tipo: str) -> dict:
    if not _SCHEMA_NAME.match(tipo or ""):
        return error(22, f"tipo invalido: {tipo!r}")
    root = schemas_root(settings)
    if not root:
        return error(
            2,
            "schemas indisponiveis; defina NOVOMODELO_MCP_SCHEMAS_DIR ou NOVOMODELO_MCP_SOLVER_BIN",
        )
    f = (Path(root) / f"{tipo}{_SUFFIX}").resolve()
    if not _within(f, Path(root).resolve()):
        return error(22, f"tipo invalido: {tipo!r}")
    if not f.exists():
        return error(
            2, f"schema inexistente: {tipo}", f"disponiveis: {list_schema_types(settings)}"
        )
    return {"status": "ok", "type": tipo, "schema": json.loads(f.read_text(encoding="utf-8"))}


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- docs


def _dev_docs_dir(settings: Settings) -> str | None:
    docs_dir = getattr(settings, "docs_dir", None)
    return docs_dir if docs_dir and Path(docs_dir).is_dir() else None


def docs_root(settings: Settings) -> str | None:
    """Raiz das docs: a pasta de desenvolvimento, se definida, senão as embutidas.

    Nunca um clone achado por perto: um clone de outra versão passaria na frente das
    docs da versão instalada sem ninguém perceber.
    """
    return _dev_docs_dir(settings) or _bundled_dir("docs")


def docs_origin(settings: Settings) -> dict:
    """De onde vêm as docs: `embutidas` (versão e commit) ou `pasta_de_desenvolvimento`."""
    if dev := _dev_docs_dir(settings):
        return {"origin": "pasta_de_desenvolvimento", "path": dev}
    manifest = bundled_manifest() or {}
    return {
        "origin": "embutidas",
        "version": manifest.get("docs_versao"),
        "commit": manifest.get("docs_commit"),
    }


def _docs_unavailable(settings: Settings) -> dict:
    if settings.docs_dir:
        return error(
            2,
            "docs indisponiveis: NOVOMODELO_MCP_DOCS_DIR aponta para caminho "
            f"inexistente ou que nao e diretorio ({settings.docs_dir}), e o pacote "
            "nao tem as docs embutidas",
        )
    return error(
        2, "docs indisponiveis: o pacote do MCP nao tem as docs embutidas; reinstale o MCP"
    )


def list_docs(settings: Settings, prefix: str | None = None) -> dict:
    root = docs_root(settings)
    if root is None:
        return _docs_unavailable(settings)
    base = Path(root)
    items = []
    for rel, path in iter_doc_pages(base):
        if prefix and not rel.startswith(prefix):
            continue
        fields = frontmatter_fields(path.read_text(encoding="utf-8", errors="replace"))
        items.append({"page": rel, "title": fields["title"], "description": fields["description"]})
    return {
        "status": "ok",
        "docs_dir": str(base),
        "count": len(items),
        "pages": [i["page"] for i in items],
        "items": items,
    }


def read_doc(settings: Settings, page: str, max_chars: int, section: str | None = None) -> dict:
    root = docs_root(settings)
    if root is None:
        return _docs_unavailable(settings)
    base = Path(root).resolve()
    # conter antes de testar a existência: a ordem inversa revela se um arquivo
    # existe fora da raiz (respostas diferentes para "fora" e "inexistente").
    candidates = [c.resolve() for c in (base / page, base / f"{page}.md", base / f"{page}.mdx")]
    if not all(_within(c, base) for c in candidates):
        return error(13, f"pagina fora do docs root: {page}")
    tr = next((c for c in candidates if c.is_file()), None)
    if tr is None:
        return error(2, f"pagina inexistente: {page}")
    text = resolve_mdx(tr)
    extra = {}
    if section:
        found = find_section(text, section)
        if found is None:
            return error(
                2,
                f"seção inexistente em {page}: {section!r}",
                "use uma das `sections` (âncora ou título)",
                sections=section_list(text)[:200],
            )
        text, extra = found["text"], {"section": found["anchor"], "title": found["title"]}
    truncated = len(text) > max_chars
    return {
        "status": "ok",
        "page": page,
        **extra,
        "path": str(tr),
        "truncated": truncated,
        "content": text[:max_chars] + ("\n... [truncado]" if truncated else ""),
    }


# ------------------------------------------------- preparação das docs (dono único)
# O `scripts/sync_bundled.py` e o modo de desenvolvimento usam estas funções: o índice
# embutido e o montado em memória saem da mesma quebra em seções e das mesmas âncoras.

MANIFEST_FILE = "manifest.json"
INDEX_FILE = "docs_index.sqlite"

_IMPORT_IMPL = re.compile(
    r"""^import\s*\{\s*Content\s+as\s+(\w+)\s*\}\s*from\s*['"]([^'"]*_impl/[^'"]+)['"];?\s*$"""
)
_IMPORT_MDX = re.compile(r"""^import\s.+\sfrom\s+['"][^'"]+['"];?\s*$""")
_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MDX_COMMENT = re.compile(r"\{/\*.*?\*/\}", re.S)
_TAB_LABEL = re.compile(r"<TabItem\s+label=\"([^\"]+)\"\s*>")
_TAB_TAGS = re.compile(r"</?Tabs\b[^>]*>|</TabItem>|</?CardGrid\b[^>]*>")
_LINK_CARD = re.compile(r"<LinkCard\b(.*?)/>", re.S)
_SELF_CLOSING = re.compile(r"<[A-Z]\w*\b[^<>]*/>")


def split_frontmatter(text: str) -> tuple[str, str]:
    """(bloco `---…---` com os delimitadores, corpo); sem frontmatter, ("", texto)."""
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            cut = end + len("\n---")
            return text[:cut] + "\n", text[cut:].lstrip("\n")
    return "", text


def frontmatter_fields(text: str) -> dict[str, str | None]:
    block, _ = split_frontmatter(text)
    fields: dict[str, str | None] = {}
    for key in ("title", "description"):
        m = re.search(rf"^{key}:\s*(.+)$", block, re.M)
        fields[key] = m.group(1).strip().strip("'\"") if m else None
    return fields


def _blocks(text: str) -> list[tuple[bool, str]]:
    """Trechos `(é_código, texto)`: o que está entre cercas ``` não é MDX."""
    out: list[tuple[bool, list[str]]] = []
    in_code = False
    for line in text.split("\n"):
        fence = bool(_FENCE.match(line))
        if fence and not in_code:
            in_code = True
            out.append((True, [line]))
            continue
        if not out or out[-1][0] != in_code:
            out.append((in_code, []))
        out[-1][1].append(line)
        if fence and in_code:
            in_code = False
    return [(code, "\n".join(lines)) for code, lines in out]


def _link_card(m: re.Match) -> str:
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    link = f"[{attrs.get('title', '')}]({attrs.get('href', '')})"
    return f"- {link}: {attrs['description']}" if attrs.get("description") else f"- {link}"


def _clean_mdx(text: str) -> str:
    text = _MDX_COMMENT.sub("", text)
    text = _TAB_LABEL.sub(lambda m: f"\n**{m.group(1)}**\n", text)
    text = _TAB_TAGS.sub("", text)
    text = _LINK_CARD.sub(_link_card, text)
    text = _SELF_CLOSING.sub("", text)
    return re.sub(r"^[ \t]+$", "", text, flags=re.M)


def resolve_mdx(path: Path) -> str:
    """A página com os trechos `_impl` no lugar dos componentes e sem marcação MDX.

    Idempotente: resolver uma página já resolvida devolve o mesmo texto.
    """
    front, body = split_frontmatter(path.read_text(encoding="utf-8"))
    blocks = _blocks(body)
    components = {
        m.group(1): (path.parent / m.group(2)).resolve()
        for code, chunk in blocks
        if not code
        for line in chunk.split("\n")
        if (m := _IMPORT_IMPL.match(line))
    }
    impls = {
        name: split_frontmatter(target.read_text(encoding="utf-8"))[1].strip()
        for name, target in components.items()
    }
    parts = []
    for code, chunk in blocks:
        if code:
            parts.append(chunk)
            continue
        chunk = "\n".join(line for line in chunk.split("\n") if not _IMPORT_MDX.match(line))
        for name, impl in impls.items():
            chunk = re.sub(rf"<{name}\s*/>", lambda _m, t=impl: f"\n{t}\n", chunk)
        parts.append(_clean_mdx(chunk))
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(parts)).strip("\n") + "\n"
    return front + "\n" + body if front else body


def iter_doc_pages(docs_dir: Path) -> list[tuple[str, Path]]:
    """`(id, arquivo)` das páginas: sem os trechos `_impl` e sem a pasta `pt-br`."""
    pages = []
    for p in sorted(docs_dir.rglob("*")):
        rel = p.relative_to(docs_dir)
        if (
            p.is_file()
            and p.suffix in (".md", ".mdx")
            and "_impl" not in rel.parts
            and rel.parts[0] != "pt-br"
        ):
            pages.append((rel.with_suffix("").as_posix(), p))
    return pages


def slugify(title: str) -> str:
    """Âncora no formato do site (github-slugger): `3.2 Backward Pass` → `32-backward-pass`."""
    text = re.sub(r"[^\w\s-]", "", title.strip().lower(), flags=re.U)
    return re.sub(r"\s", "-", text)


def _headings(lines: list[str]) -> list[tuple[int, int, str, str]]:
    """`(linha, nível, título, âncora)` dos títulos fora de blocos de código.

    Âncora repetida ganha `-1`, `-2`… como no site; é a mesma no índice e no docs_read.
    """
    found, seen, in_code = [], {}, False
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            in_code = not in_code
            continue
        if in_code or not (m := _HEADING.match(line)):
            continue
        anchor = slugify(m.group(2))
        n = seen.get(anchor, 0)
        seen[anchor] = n + 1
        found.append(
            (i, len(m.group(1)), m.group(2).strip(), anchor if n == 0 else f"{anchor}-{n}")
        )
    return found


def split_sections(page: str, text: str) -> list[dict[str, str]]:
    """Uma entrada por seção: do título até o próximo (de qualquer nível).

    O trecho antes do primeiro título leva o título da página e a âncora vazia.
    """
    _, body = split_frontmatter(text)
    lines = body.split("\n")
    heads = _headings(lines)
    title = frontmatter_fields(text)["title"] or page
    bounds = [(0, title, "")] + [(i + 1, t, a) for i, _, t, a in heads]
    ends = [i for i, *_ in heads] + [len(lines)]
    sections = []
    for (start, sec_title, anchor), stop in zip(bounds, ends, strict=True):
        body_text = "\n".join(lines[start:stop]).strip()
        if body_text:
            sections.append(
                {"pagina": page, "titulo": sec_title, "ancora": anchor, "texto": body_text}
            )
    return sections


def find_section(text: str, wanted: str) -> dict | None:
    """A seção cuja âncora (ou título, sem caixa nem acento) é `wanted`, com as subseções:
    do título até o próximo de mesmo nível ou acima. None se não houver."""
    _, body = split_frontmatter(text)
    lines = body.split("\n")
    heads = _headings(lines)
    key = normalize_text(wanted.strip())
    for pos, (i, level, title, anchor) in enumerate(heads):
        if anchor == wanted.strip() or normalize_text(title.replace("`", "")) == key:
            stop = next((j for j, lv, *_ in heads[pos + 1 :] if lv <= level), len(lines))
            return {"title": title, "anchor": anchor, "text": "\n".join(lines[i:stop]).strip()}
    return None


def section_list(text: str) -> list[dict[str, str]]:
    _, body = split_frontmatter(text)
    return [{"title": t, "anchor": a} for _, _, t, a in _headings(body.split("\n"))]


def normalize_text(text: str) -> str:
    """Minúsculas e sem acento (a mesma normalização da consulta e do glossário)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def glossary_pairs(text: str) -> list[tuple[str, str]]:
    """Pares `(português normalizado, termo em inglês)` das tabelas do glossário das docs."""
    pairs = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("", "English") or set(cells[0]) <= set("-: "):
            continue
        english = re.sub(r"\s*\(.*?\)", "", cells[0]).strip()
        portuguese = cells[1]
        if portuguese in ("", "-"):
            continue
        alternatives = re.split(r"\s*/\s*", re.sub(r"\(.*?\)", "", portuguese))
        alternatives += re.findall(r"\(([^)]+)\)", portuguese)
        for alt in alternatives:
            if alt.strip():
                pairs.append((normalize_text(alt.strip()), english))
    return pairs


CHANGELOG_PREFIX = "changelog/"


def build_docs_index(docs_dir: Path, db_path: str | Path) -> sqlite3.Connection:
    """Índice FTS5 das seções (+ títulos das páginas e glossário) em `db_path`.

    Os changelogs ficam numa tabela à parte: o texto denso deles não muda a ordem da
    busca de metodologia, e só entram quando a consulta é sobre versões.
    """
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE VIRTUAL TABLE secoes USING fts5(
            pagina, titulo, ancora UNINDEXED, texto,
            tokenize = 'porter unicode61 remove_diacritics 2');
        CREATE VIRTUAL TABLE changelog USING fts5(
            pagina, titulo, ancora UNINDEXED, texto,
            tokenize = 'porter unicode61 remove_diacritics 2');
        CREATE TABLE paginas (pagina TEXT PRIMARY KEY, titulo TEXT, descricao TEXT);
        CREATE TABLE glossario (pt TEXT, en TEXT);
    """)
    for page, path in iter_doc_pages(Path(docs_dir)):
        text = resolve_mdx(path)
        fields = frontmatter_fields(text)
        con.execute(
            "INSERT INTO paginas VALUES (?, ?, ?)", (page, fields["title"], fields["description"])
        )
        table = "changelog" if page.startswith(CHANGELOG_PREFIX) else "secoes"
        con.executemany(
            f"INSERT INTO {table} VALUES (?, ?, ?, ?)",
            [
                (s["pagina"], s["titulo"], s["ancora"], s["texto"])
                for s in split_sections(page, text)
            ],
        )
    glossary = Path(docs_dir) / "reference" / "glossary.md"
    if glossary.is_file():
        con.executemany(
            "INSERT INTO glossario VALUES (?, ?)",
            glossary_pairs(glossary.read_text(encoding="utf-8")),
        )
    con.commit()
    return con


def bundled_manifest() -> dict | None:
    """O manifesto das docs embutidas, ou None se o pacote não o tiver."""
    root = _bundled_dir("docs")
    if root is None:
        return None
    try:
        return json.loads((Path(root).parent / MANIFEST_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- busca

_SEARCH_MAX_K = 20
_VERSION_INTENT = re.compile(
    r"\d+\.\d+|\b(changelog|release|releases|version|versions|versao|"
    r"versoes|mudou|mudancas|novidades|breaking)\b"
)
_SNIPPET_CHARS = 300
#: Palavras de consulta em português que não ajudam a achar nada nas docs (em inglês).
_PT_STOPWORDS = frozenset(
    "o a os as que e é de do da dos das em no na um uma como qual quais por para com se "
    "ao à sobre isso este esta".split()
)
_MEMORY_INDEX: dict[str, sqlite3.Connection] = {}


def _index_connection(settings: Settings) -> sqlite3.Connection | None:
    """O índice embutido (só leitura) ou, com a pasta de desenvolvimento, um em memória."""
    if dev := _dev_docs_dir(settings):
        if dev not in _MEMORY_INDEX:
            _MEMORY_INDEX[dev] = build_docs_index(Path(dev), ":memory:")
        return _MEMORY_INDEX[dev]
    root = _bundled_dir("docs")
    index = Path(root).parent / INDEX_FILE if root else None
    if index is None or not index.is_file():
        return None
    return sqlite3.connect(f"{index.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)


def _glossary_terms(con: sqlite3.Connection, normalized: str) -> list[str]:
    found: list[str] = []
    for pt, en in con.execute("SELECT pt, en FROM glossario ORDER BY length(pt) DESC"):
        if re.search(rf"(?<!\w){re.escape(pt)}(?!\w)", normalized) and en not in found:
            found.append(en)
    return found


#: Uma consulta por tabela, escrita por inteiro: o SQLite não parametriza nome de tabela.
_SEARCH_SQL = {
    "secoes": (
        "SELECT pagina, titulo, ancora, snippet(secoes, 3, '', '', '…', 48), "
        "bm25(secoes, 0.0, 5.0, 0.0, 1.0) AS r FROM secoes WHERE secoes MATCH ? "
        "ORDER BY r LIMIT ?"
    ),
    "changelog": (
        "SELECT pagina, titulo, ancora, snippet(changelog, 3, '', '', '…', 48), "
        "bm25(changelog, 0.0, 5.0, 0.0, 1.0) AS r FROM changelog WHERE changelog MATCH ? "
        "ORDER BY r LIMIT ?"
    ),
}


def search_docs(settings: Settings, query: str, k: int = 5) -> dict:
    """Seções mais relevantes para `query` (BM25, título com peso maior).

    Os termos em português do glossário das docs ganham o equivalente em inglês; os
    termos entram entre aspas e unidos por OR, o que neutraliza a sintaxe do FTS5.
    """
    con = _index_connection(settings)
    if con is None:
        return _docs_unavailable(settings)
    normalized = normalize_text(query or "")
    glossary = _glossary_terms(con, normalized)
    words = [w for w in re.findall(r"\w+", normalized) if w not in _PT_STOPWORDS]
    words += [w for term in glossary for w in re.findall(r"\w+", normalize_text(term))]
    terms = list(dict.fromkeys(words))
    if not terms:
        return error(
            22, "consulta vazia: informe termos da documentação (de preferência em inglês)"
        )
    match = " OR ".join(f'"{t}"' for t in terms)
    limit = max(1, min(int(k), _SEARCH_MAX_K))
    try:
        rows = []
        if (
            _VERSION_INTENT.search(normalized)
            and con.execute("SELECT 1 FROM sqlite_master WHERE name = 'changelog'").fetchone()
        ):
            # Os escores das duas tabelas não se comparam: o changelog vem na frente,
            # com até metade das vagas, quando a consulta é sobre versões.
            rows = con.execute(_SEARCH_SQL["changelog"], (match, (limit + 1) // 2)).fetchall()
        rows += con.execute(_SEARCH_SQL["secoes"], (match, limit - len(rows))).fetchall()
    except sqlite3.Error as exc:
        return error(2, "falha na busca do índice de docs", str(exc))
    return {
        "status": "ok",
        "query_used": match,
        "glossary_terms": glossary,
        "results": [
            {
                "page": p,
                "section": a,
                "title": t,
                "snippet": (snip or "")[:_SNIPPET_CHARS],
                "score": round(-r, 3),
            }
            for p, t, a, snip, r in rows
        ],
    }
