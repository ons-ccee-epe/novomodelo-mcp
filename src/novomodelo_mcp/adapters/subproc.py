"""Argumentos comuns a todo subprocesso que o servidor lança."""
from __future__ import annotations

import subprocess
import sys
from typing import Any

# Todo subprocess.run/Popen do servidor passa CREATE_NO_WINDOW no Windows (via `**NO_WINDOW`):
# sob um cliente MCP gráfico o servidor não tem console, e cada CLI de console lançado sem a
# flag abre uma janela. `test_subprocess_sem_janela` cobra isso em toda chamada.
NO_WINDOW: dict[str, Any] = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}  # type: ignore[attr-defined]  # só existe no Windows
    if sys.platform == "win32" else {}
)
