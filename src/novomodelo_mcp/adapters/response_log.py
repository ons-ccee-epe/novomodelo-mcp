"""Logging estruturado de chamadas MCP para validação E2E.

Ligado por NOVOMODELO_MCP_RESPONSE_LOG=<caminho>. Grava um arquivo JSONL com:
- timestamp ISO
- tool_name
- arguments (request)
- result (response)
- duration_ms

Este log permite que testes E2E validem não só que a tool foi chamada,
mas também o que ela retornou.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Lock para escrita thread-safe
_write_lock = threading.Lock()


def get_response_log_path() -> Path | None:
    """Retorna o caminho do arquivo de log de respostas, se configurado."""
    path = os.environ.get("NOVOMODELO_MCP_RESPONSE_LOG")
    if not path:
        return None
    return Path(path)


def log_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    result: Any,
    duration_ms: float,
) -> None:
    """Grava uma entrada de chamada de tool no log JSONL.

    Args:
        tool_name: Nome da tool MCP chamada
        arguments: Argumentos passados para a tool
        result: Resultado retornado pela tool
        duration_ms: Duração da chamada em milissegundos
    """
    log_path = get_response_log_path()
    if not log_path:
        return

    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tool": tool_name,
        "arguments": _safe_serialize(arguments),
        "result": _safe_serialize(result),
        "duration_ms": round(duration_ms, 2),
    }

    try:
        # Garante que o diretório existe
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Escrita atômica com lock
        with _write_lock:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 - logging nunca deve derrubar a tool
        pass


def _safe_serialize(obj: Any, max_depth: int = 10, max_str_len: int = 10000) -> Any:
    """Serializa objeto de forma segura, truncando strings muito longas."""
    if max_depth <= 0:
        return "<<max depth reached>>"

    if obj is None:
        return None
    if isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        if len(obj) > max_str_len:
            return obj[:max_str_len] + f"... <<truncated, total {len(obj)} chars>>"
        return obj
    if isinstance(obj, bytes):
        return f"<<bytes: {len(obj)} bytes>>"
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v, max_depth - 1, max_str_len) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item, max_depth - 1, max_str_len) for item in obj]

    # Fallback para outros tipos
    try:
        return str(obj)
    except Exception:
        return f"<<unserializable: {type(obj).__name__}>>"


def clear_log() -> None:
    """Limpa o arquivo de log (útil para testes)."""
    log_path = get_response_log_path()
    if log_path and log_path.exists():
        log_path.unlink()


def read_log() -> list[dict[str, Any]]:
    """Lê todas as entradas do log (útil para testes)."""
    log_path = get_response_log_path()
    if not log_path or not log_path.exists():
        return []

    entries = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries
