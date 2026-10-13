"""Referência: JSON Schemas de entrada e páginas de documentação (offline).

Fontes:
- schemas: `NOVOMODELO_MCP_SCHEMAS_DIR`, ou exportados sob demanda via `novomodelo schema export`.
- docs: `NOVOMODELO_MCP_DOCS_DIR`; se ausente/inválido, AUTO-DESCOBERTA de um clone
  `novomodelo-docs` em locais previsíveis (ao lado do repo do MCP ou do diretório de
  trabalho — ex.: .../codigo/<repositório anterior> + .../codigo/novomodelo-docs). Sem env var e
  sem caminho pessoal fixo: a mesma heurística vale para qualquer checkout.
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

_SCHEMA_EXPORT_CACHE: dict[str, str] = {}
_DOCS_DISCOVER_CACHE: dict[str, str] = {}
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
        proc = subprocess.run(
            [novomodelo, "--color", "never", "schema", "export", "--output-dir", str(out)],
            capture_output=True, text=True, timeout=60)
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
    return (
        settings.schemas_dir
        or _export_schemas(settings)
        or _bundled_dir("schemas")
    )


def list_schema_types(settings: Settings) -> list[str]:
    root = schemas_root(settings)
    if not root or not Path(root).is_dir():
        return []
    return sorted(p.name[: -len(_SUFFIX)] for p in Path(root).glob(f"*{_SUFFIX}"))


def read_schema(settings: Settings, tipo: str) -> dict:
    if not _SCHEMA_NAME.match(tipo or ""):
        return {"status": "error", "diagnostics": [f"tipo invalido: {tipo!r}"]}
    root = schemas_root(settings)
    if not root:
        return {"status": "error",
                "diagnostics": ["schemas indisponiveis; defina NOVOMODELO_MCP_SCHEMAS_DIR ou NOVOMODELO_MCP_SOLVER_BIN"]}
    f = (Path(root) / f"{tipo}{_SUFFIX}").resolve()
    if not _within(f, Path(root).resolve()):
        return {"status": "error", "diagnostics": [f"tipo invalido: {tipo!r}"]}
    if not f.exists():
        return {"status": "error",
                "diagnostics": [f"schema inexistente: {tipo}",
                                f"disponiveis: {list_schema_types(settings)}"]}
    return {"status": "ok", "tipo": tipo, "schema": json.loads(f.read_text(encoding="utf-8"))}


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- docs

_CLONE_HINT = (
    "clone https://github.com/ons-ccee-epe/novomodelo-docs e defina NOVOMODELO_MCP_DOCS_DIR para a "
    "pasta de paginas .md/.mdx (no layout padrao do repo, src/content/docs), ou "
    "deixe o clone ao lado do repo do novomodelo/<repositório anterior> para a descoberta automatica "
    "encontra-lo"
)


def _has_docs(d: Path) -> bool:
    """True se o diretório contém ao menos um .md/.mdx (para no primeiro achado)."""
    try:
        for p in d.rglob("*"):
            if p.suffix in (".md", ".mdx"):
                return True
    except OSError:
        return False
    return False


def _search_docs_in(bases: list[Path]) -> str | None:
    """Procura, na ordem dada, um clone `novomodelo-docs` com conteúdo dentro das bases.

    Puro e testável: recebe as bases já resolvidas. Prefere a subpasta de conteúdo
    do layout padrão (`novomodelo-docs/src/content/docs`); aceita também a raiz do clone,
    caso o repo seja reorganizado.
    """
    for base in bases:
        for cand in (base / "novomodelo-docs" / "src" / "content" / "docs",
                     base / "novomodelo-docs"):
            if cand.is_dir() and _has_docs(cand):
                return str(cand)
    return None


def _candidate_bases() -> list[Path]:
    """Bases previsíveis onde um clone `novomodelo-docs` costuma ficar (sem env var).

    Ancestrais do próprio pacote do MCP e do diretório de trabalho — novomodelo o
    layout usual de checkouts lado a lado, sem depender de caminho pessoal.
    """
    bases: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            rp = p.resolve()
        except OSError:
            return
        key = str(rp)
        if key not in seen:
            seen.add(key)
            bases.append(rp)

    for anc in list(Path(__file__).resolve().parents)[:6]:
        add(anc)
    try:
        cwd = Path.cwd()
    except OSError:
        cwd = None
    if cwd is not None:
        add(cwd)
        for anc in list(cwd.resolve().parents)[:4]:
            add(anc)
    return bases


def _discover_docs_dir() -> str | None:
    """Auto-descoberta de um clone `novomodelo-docs` (com cache do acerto)."""
    cached = _DOCS_DISCOVER_CACHE.get("root")
    if cached and Path(cached).is_dir():
        return cached
    found = _search_docs_in(_candidate_bases())
    if found:
        _DOCS_DISCOVER_CACHE["root"] = found
    return found


def docs_root(settings: Settings) -> str | None:
    """Raiz efetiva das docs (cascata; primeiro que existir vence).

    ``NOVOMODELO_MCP_DOCS_DIR`` (valido) -> auto-descoberta de um clone ``novomodelo-docs``
    -> docs EMBUTIDOS (``_bundled/docs``). O embutido garante o caminho feliz
    offline, sem clone nem env var.
    """
    if settings.docs_dir and Path(settings.docs_dir).is_dir():
        return settings.docs_dir
    return _discover_docs_dir() or _bundled_dir("docs")


def _docs_unavailable(settings: Settings) -> dict:
    """Erro quando não há docs: env var ausente/quebrada E nada descoberto."""
    configured = settings.docs_dir
    if not configured:
        msg = ("docs indisponiveis: NOVOMODELO_MCP_DOCS_DIR nao definido e nenhum clone "
               "novomodelo-docs encontrado automaticamente")
    else:
        msg = ("docs indisponiveis: NOVOMODELO_MCP_DOCS_DIR aponta para caminho inexistente "
               f"ou que nao e diretorio ({configured}) e nenhum clone novomodelo-docs "
               "encontrado automaticamente")
    return {"status": "error", "diagnostics": [msg, _CLONE_HINT]}


def list_docs(settings: Settings, section: str | None = None) -> dict:
    root = docs_root(settings)
    if root is None:
        return _docs_unavailable(settings)
    base = Path(root)
    pages = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.suffix in (".md", ".mdx"):
            rel = p.relative_to(base).with_suffix("").as_posix()  # id estável em qualquer SO
            if section and not rel.startswith(section):
                continue
            pages.append(rel)
    return {"status": "ok", "docs_dir": str(base), "count": len(pages), "pages": pages}


def read_doc(settings: Settings, page: str, max_chars: int) -> dict:
    root = docs_root(settings)
    if root is None:
        return _docs_unavailable(settings)
    base = Path(root).resolve()
    # conter antes de testar a existência: a ordem inversa revela se um arquivo
    # existe fora da raiz (respostas diferentes para "fora" e "inexistente").
    candidates = [c.resolve() for c in (base / page, base / f"{page}.md", base / f"{page}.mdx")]
    if not all(_within(c, base) for c in candidates):
        return {"status": "error", "diagnostics": [f"pagina fora do docs root: {page}"]}
    tr = next((c for c in candidates if c.is_file()), None)
    if tr is None:
        return {"status": "error", "diagnostics": [f"pagina inexistente: {page}"]}
    text = tr.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    return {"status": "ok", "page": page, "path": str(tr), "truncated": truncated,
            "content": text[:max_chars] + ("\n... [truncado]" if truncated else "")}


# ------------------------------------------------- preparação das docs (dono único)
# O `scripts/sync_bundled.py` e o modo de desenvolvimento usam estas funções: o índice
# embutido e o montado em memória saem da mesma quebra em seções e das mesmas âncoras.

MANIFEST_FILE = "manifest.json"
INDEX_FILE = "docs_index.sqlite"

_IMPORT_IMPL = re.compile(
    r"""^import\s*\{\s*Content\s+as\s+(\w+)\s*\}\s*from\s*['"]([^'"]*_impl/[^'"]+)['"];?\s*$""")
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
    components = {m.group(1): (path.parent / m.group(2)).resolve()
                  for code, chunk in blocks if not code
                  for line in chunk.split("\n") if (m := _IMPORT_IMPL.match(line))}
    impls = {name: split_frontmatter(target.read_text(encoding="utf-8"))[1].strip()
             for name, target in components.items()}
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
        if p.is_file() and p.suffix in (".md", ".mdx") and "_impl" not in rel.parts \
                and rel.parts[0] != "pt-br":
            pages.append((rel.with_suffix("").as_posix(), p))
    return pages


def slugify(title: str) -> str:
    """Âncora no formato do site (github-slugger): `3.2 Backward Pass` → `32-backward-pass`."""
    text = re.sub(r"[^\w\s-]", "", title.strip().lower(), flags=re.U)
    return re.sub(r"\s", "-", text)


def split_sections(page: str, text: str) -> list[dict[str, str]]:
    """Uma entrada por seção: do título até o próximo, fora de blocos de código.

    O trecho antes do primeiro título leva o título da página e a âncora vazia.
    """
    _, body = split_frontmatter(text)
    title = frontmatter_fields(text)["title"] or page
    sections, seen = [], {}
    current = {"pagina": page, "titulo": title, "ancora": "", "linhas": []}
    for code, chunk in _blocks(body):
        for line in chunk.split("\n"):
            m = None if code else _HEADING.match(line)
            if not m:
                current["linhas"].append(line)
                continue
            if "\n".join(current["linhas"]).strip():
                sections.append(current)
            anchor = slugify(m.group(2))
            n = seen.get(anchor, 0)
            seen[anchor] = n + 1
            current = {"pagina": page, "titulo": m.group(2).strip(),
                       "ancora": anchor if n == 0 else f"{anchor}-{n}", "linhas": []}
    if "\n".join(current["linhas"]).strip():
        sections.append(current)
    return [{"pagina": s["pagina"], "titulo": s["titulo"], "ancora": s["ancora"],
             "texto": "\n".join(s["linhas"]).strip()} for s in sections]


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


def build_docs_index(docs_dir: Path, db_path: str | Path) -> sqlite3.Connection:
    """Índice FTS5 das seções (+ títulos das páginas e glossário) em `db_path`."""
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE VIRTUAL TABLE secoes USING fts5(
            pagina, titulo, ancora UNINDEXED, texto,
            tokenize = 'porter unicode61 remove_diacritics 2');
        CREATE TABLE paginas (pagina TEXT PRIMARY KEY, titulo TEXT, descricao TEXT);
        CREATE TABLE glossario (pt TEXT, en TEXT);
    """)
    for page, path in iter_doc_pages(Path(docs_dir)):
        text = resolve_mdx(path)
        fields = frontmatter_fields(text)
        con.execute("INSERT INTO paginas VALUES (?, ?, ?)",
                    (page, fields["title"], fields["description"]))
        con.executemany("INSERT INTO secoes VALUES (?, ?, ?, ?)",
                        [(s["pagina"], s["titulo"], s["ancora"], s["texto"])
                         for s in split_sections(page, text)])
    glossary = Path(docs_dir) / "reference" / "glossary.md"
    if glossary.is_file():
        con.executemany("INSERT INTO glossario VALUES (?, ?)",
                        glossary_pairs(glossary.read_text(encoding="utf-8")))
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

