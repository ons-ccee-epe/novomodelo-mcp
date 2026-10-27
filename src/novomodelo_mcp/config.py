"""Configuração do servidor, lida do ambiente. Sem rede, sem estado global.

Todas as variáveis usam o prefixo `names.ENV_PREFIX` (`NOVOMODELO_MCP_`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .names import ENV_PREFIX


@dataclass(frozen=True)
class Settings:
    """Ajustes resolvidos uma vez no startup, todos vindos do ambiente."""

    bridge_bin: str | None  # NOVOMODELO_MCP_BRIDGE_BIN (senão: procura no PATH)
    solver_bin: str | None  # NOVOMODELO_MCP_SOLVER_BIN (senão: procura no PATH)
    schemas_dir: str | None  # NOVOMODELO_MCP_SCHEMAS_DIR (dir com *.schema.json)
    docs_dir: str | None  # NOVOMODELO_MCP_DOCS_DIR (pasta de páginas .md/.mdx)
    workspace: str | None  # NOVOMODELO_MCP_WORKSPACE (raiz(es) permitidas; os.pathsep)
    allow_force: bool  # NOVOMODELO_MCP_ALLOW_FORCE (habilita edições force=True)
    log_calls: bool  # NOVOMODELO_MCP_LOG (loga chamadas no stderr)
    default_timeout: float  # NOVOMODELO_MCP_TIMEOUT (segundos)
    max_diagnostics: int  # NOVOMODELO_MCP_MAX_DIAGNOSTICS
    max_summary_chars: int  # NOVOMODELO_MCP_MAX_SUMMARY_CHARS
    max_read_bytes: int  # NOVOMODELO_MCP_MAX_READ_BYTES (teto do que é carregado inteiro: JSON, describe e edit de parquet)
    max_response_kb: (
        int  # NOVOMODELO_MCP_MAX_RESPONSE_KB (teto de tamanho de uma resposta com linhas)
    )
    state_dir: str | None = None  # NOVOMODELO_MCP_STATE_DIR (jobs + calibração; padrão por SO)
    max_jobs: int = 1  # NOVOMODELO_MCP_MAX_JOBS (runs simultâneos permitidos)
    max_policy_bytes: int = 1024**3  # NOVOMODELO_MCP_MAX_POLICY_BYTES (teto do results_policy)


def env_name(suffix: str) -> str:
    """Nome completo de uma variável do MCP (ex.: `env_name("WORKSPACE")`)."""
    return ENV_PREFIX + suffix


def _env_str(suffix: str) -> str | None:
    return os.environ.get(env_name(suffix)) or None


def _env_float(suffix: str, default: float) -> float:
    raw = os.environ.get(env_name(suffix))
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _env_int(suffix: str, default: int) -> int:
    raw = os.environ.get(env_name(suffix))
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _env_bool(suffix: str, default: bool = False) -> bool:
    raw = os.environ.get(env_name(suffix))
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    return Settings(
        bridge_bin=_env_str("BRIDGE_BIN"),
        solver_bin=_env_str("SOLVER_BIN"),
        schemas_dir=_env_str("SCHEMAS_DIR"),
        docs_dir=_env_str("DOCS_DIR"),
        workspace=_env_str("WORKSPACE"),
        allow_force=_env_bool("ALLOW_FORCE", False),
        log_calls=_env_bool("LOG", False),
        default_timeout=_env_float("TIMEOUT", 900.0),
        max_diagnostics=_env_int("MAX_DIAGNOSTICS", 50),
        max_summary_chars=_env_int("MAX_SUMMARY_CHARS", 20000),
        max_read_bytes=_env_int("MAX_READ_BYTES", 5_000_000),
        max_response_kb=max(1, _env_int("MAX_RESPONSE_KB", 50)),
        state_dir=_env_str("STATE_DIR"),
        max_jobs=_env_int("MAX_JOBS", 1),
        max_policy_bytes=_env_int("MAX_POLICY_BYTES", 1024**3),
    )
