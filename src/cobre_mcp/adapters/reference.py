"""Referência: JSON Schemas de entrada e páginas de documentação (offline).

Fontes:
- schemas: `COBRE_SCHEMAS_DIR`, ou exportados sob demanda via `cobre schema export`.
- docs: `COBRE_DOCS_DIR` (ex.: o clone `cobre-docs/src/content/docs`).
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


def list_docs(settings: Settings, section: str | None = None) -> dict:
    root = settings.docs_dir
    if not root or not Path(root).is_dir():
        return {"status": "error", "diagnostics": ["docs indisponiveis; defina COBRE_DOCS_DIR"]}
    base = Path(root)
    pages = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.suffix in (".md", ".mdx"):
            rel = str(p.relative_to(base).with_suffix(""))
            if section and not rel.startswith(section):
                continue
            pages.append(rel)
    return {"status": "ok", "count": len(pages), "pages": pages}


def read_doc(settings: Settings, page: str, max_chars: int) -> dict:
    root = settings.docs_dir
    if not root or not Path(root).is_dir():
        return {"status": "error", "diagnostics": ["docs indisponiveis; defina COBRE_DOCS_DIR"]}
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
