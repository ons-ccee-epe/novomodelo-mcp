"""Configuração do servidor, lida do ambiente. Sem rede, sem estado global."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Ajustes resolvidos uma vez no startup, todos vindos do ambiente."""

    bridge_bin: str | None          # COBRE_BRIDGE_BIN (senão: procura no PATH)
    cobre_bin: str | None           # COBRE_BIN        (senão: procura no PATH)
    schemas_dir: str | None         # COBRE_SCHEMAS_DIR (dir com *.schema.json)
    docs_dir: str | None            # COBRE_DOCS_DIR (mirror local do cobre-docs)
    workspace: str | None           # COBRE_MCP_WORKSPACE (raiz(es) permitidas; os.pathsep)
    allow_force: bool               # COBRE_MCP_ALLOW_FORCE (habilita edições force=True)
    log_calls: bool                 # COBRE_MCP_LOG (loga chamadas no stderr)
    default_timeout: float          # COBRE_MCP_TIMEOUT (segundos)
    max_diagnostics: int            # COBRE_MCP_MAX_DIAGNOSTICS
    max_summary_chars: int          # COBRE_MCP_MAX_SUMMARY_CHARS
    max_inline_rows: int            # COBRE_MCP_MAX_INLINE_ROWS (parquet head)
    max_read_bytes: int             # COBRE_MCP_MAX_READ_BYTES (teto de leitura de JSON)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    return Settings(
        bridge_bin=os.environ.get("COBRE_BRIDGE_BIN") or None,
        cobre_bin=os.environ.get("COBRE_BIN") or None,
        schemas_dir=os.environ.get("COBRE_SCHEMAS_DIR") or None,
        docs_dir=os.environ.get("COBRE_DOCS_DIR") or None,
        workspace=os.environ.get("COBRE_MCP_WORKSPACE") or None,
        allow_force=_env_bool("COBRE_MCP_ALLOW_FORCE", False),
        log_calls=_env_bool("COBRE_MCP_LOG", False),
        default_timeout=_env_float("COBRE_MCP_TIMEOUT", 900.0),
        max_diagnostics=_env_int("COBRE_MCP_MAX_DIAGNOSTICS", 50),
        max_summary_chars=_env_int("COBRE_MCP_MAX_SUMMARY_CHARS", 20000),
        max_inline_rows=_env_int("COBRE_MCP_MAX_INLINE_ROWS", 50),
        max_read_bytes=_env_int("COBRE_MCP_MAX_READ_BYTES", 5_000_000),
    )
