"""Logging opcional por chamada, no STDERR (nunca stdout — stdout é o canal MCP).

Ligado por NOVOMODELO_MCP_LOG=1. Serve para ver, na fase de teste, o que o servidor
de fato executou e o que voltou (visível via `--debug` ou nos logs do app).
"""

from __future__ import annotations

import sys
from typing import Any

from ..config import Settings


def log(settings: Settings, event: str, **fields: Any) -> None:
    if not settings.log_calls:
        return
    parts = []
    for key, value in fields.items():
        text = repr(value)
        if len(text) > 300:
            text = text[:300] + "…"
        parts.append(f"{key}={text}")
    line = f"[novomodelo-mcp] {event}" + (" " + " ".join(parts) if parts else "")
    print(line, file=sys.stderr, flush=True)
