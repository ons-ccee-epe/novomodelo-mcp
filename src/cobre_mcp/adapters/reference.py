"""Referência: JSON Schemas de entrada e páginas de documentação (offline).

Fontes:
- schemas: `COBRE_SCHEMAS_DIR`, ou exportados sob demanda via `cobre schema export`.
- docs: `COBRE_DOCS_DIR`; se ausente/inválido, AUTO-DESCOBERTA de um clone
  `cobre-docs` em locais previsíveis (ao lado do repo do MCP ou do diretório de
  trabalho — ex.: .../codigo/<repositório anterior> + .../codigo/cobre-docs). Sem env var e
  sem caminho pessoal fixo: a mesma heurística vale para qualquer checkout.
Leitura confinada à raiz; conteúdo com teto. Sem regra de negócio.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from ..config import Settings
from .discovery import find_cobre

_SCHEMA_EXPORT_CACHE: dict[str, str] = {}
_DOCS_DISCOVER_CACHE: dict[str, str] = {}
_SUFFIX = ".schema.json"


def _export_schemas(settings: Settings) -> str | None:
    """Exporta os schemas via `cobre schema export` para um cache temporário."""
    cobre = find_cobre(settings)
    if not cobre:
        return None
    cached = _SCHEMA_EXPORT_CACHE.get(cobre)
    if cached and Path(cached).is_dir():
        return cached
    out = Path(tempfile.gettempdir()) / "cobre_mcp_schemas"
    out.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [cobre, "--color", "never", "schema", "export", "--output-dir", str(out)],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    _SCHEMA_EXPORT_CACHE[cobre] = str(out)
    return str(out)


def schemas_root(settings: Settings) -> str | None:
    return settings.schemas_dir or _export_schemas(settings)


def list_schema_types(settings: Settings) -> list[str]:
    root = schemas_root(settings)
    if not root or not Path(root).is_dir():
        return []
    return sorted(p.name[: -len(_SUFFIX)] for p in Path(root).glob(f"*{_SUFFIX}"))


def read_schema(settings: Settings, tipo: str) -> dict:
    if "/" in tipo or ".." in tipo or "\\" in tipo:
        return {"status": "error", "diagnostics": [f"tipo invalido: {tipo}"]}
    root = schemas_root(settings)
    if not root:
        return {"status": "error",
                "diagnostics": ["schemas indisponiveis; defina COBRE_SCHEMAS_DIR ou COBRE_BIN"]}
    f = Path(root) / f"{tipo}{_SUFFIX}"
    if not f.exists():
        return {"status": "error",
                "diagnostics": [f"schema inexistente: {tipo}",
                                f"disponiveis: {list_schema_types(settings)}"]}
    return {"status": "ok", "tipo": tipo, "schema": json.loads(f.read_text())}


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- docs

_CLONE_HINT = (
    "clone https://github.com/cobre-rs/cobre-docs e defina COBRE_DOCS_DIR para a "
    "pasta de paginas .md/.mdx (no layout padrao do repo, src/content/docs), ou "
    "deixe o clone ao lado do repo do cobre/<repositório anterior> para a descoberta automatica "
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
    """Procura, na ordem dada, um clone `cobre-docs` com conteúdo dentro das bases.

    Puro e testável: recebe as bases já resolvidas. Prefere a subpasta de conteúdo
    do layout padrão (`cobre-docs/src/content/docs`); aceita também a raiz do clone,
    caso o repo seja reorganizado.
    """
    for base in bases:
        for cand in (base / "cobre-docs" / "src" / "content" / "docs",
                     base / "cobre-docs"):
            if cand.is_dir() and _has_docs(cand):
                return str(cand)
    return None


def _candidate_bases() -> list[Path]:
    """Bases previsíveis onde um clone `cobre-docs` costuma ficar (sem env var).

    Ancestrais do próprio pacote do MCP e do diretório de trabalho — cobre o
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
    """Auto-descoberta de um clone `cobre-docs` (com cache do acerto)."""
    cached = _DOCS_DISCOVER_CACHE.get("root")
    if cached and Path(cached).is_dir():
        return cached
    found = _search_docs_in(_candidate_bases())
    if found:
        _DOCS_DISCOVER_CACHE["root"] = found
    return found


def docs_root(settings: Settings) -> str | None:
    """Raiz efetiva das docs: `COBRE_DOCS_DIR` válido vence; senão, auto-descoberta."""
    if settings.docs_dir and Path(settings.docs_dir).is_dir():
        return settings.docs_dir
    return _discover_docs_dir()


def _docs_unavailable(settings: Settings) -> dict:
    """Erro quando não há docs: env var ausente/quebrada E nada descoberto."""
    configured = settings.docs_dir
    if not configured:
        msg = ("docs indisponiveis: COBRE_DOCS_DIR nao definido e nenhum clone "
               "cobre-docs encontrado automaticamente")
    else:
        msg = ("docs indisponiveis: COBRE_DOCS_DIR aponta para caminho inexistente "
               f"ou que nao e diretorio ({configured}) e nenhum clone cobre-docs "
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
            rel = str(p.relative_to(base).with_suffix(""))
            if section and not rel.startswith(section):
                continue
            pages.append(rel)
    return {"status": "ok", "docs_dir": str(base), "count": len(pages), "pages": pages}


def read_doc(settings: Settings, page: str, max_chars: int) -> dict:
    root = docs_root(settings)
    if root is None:
        return _docs_unavailable(settings)
    base = Path(root).resolve()
    candidates = [base / page, base / f"{page}.md", base / f"{page}.mdx"]
    target = next((c for c in candidates if c.exists() and c.is_file()), None)
    if target is None:
        return {"status": "error", "diagnostics": [f"pagina inexistente: {page}"]}
    tr = target.resolve()
    if not _within(tr, base):
        return {"status": "error", "diagnostics": [f"pagina fora do docs root: {page}"]}
    text = tr.read_text(errors="replace")
    truncated = len(text) > max_chars
    return {"status": "ok", "page": page, "path": str(tr), "truncated": truncated,
            "content": text[:max_chars] + ("\n... [truncado]" if truncated else "")}
