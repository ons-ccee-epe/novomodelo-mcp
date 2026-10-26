"""Binários falsos executáveis em qualquer SO.

No POSIX o próprio script (shebang + bit de execução) serve. No Windows um `.py`
não é executável por CreateProcess: geramos um lançador `.cmd` que chama o
interpretador atual com o script.
"""

import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def fake_bin(script: str) -> str:
    """Caminho executável para `tests/<script>` (ex.: 'fake_novomodelo.py')."""
    path = _HERE / script
    if os.name != "nt":
        return str(path)
    launcher = Path(tempfile.gettempdir()) / f"novomodelo-mcp-{path.stem}.cmd"
    launcher.write_text(f'@echo off\r\n"{sys.executable}" "{path}" %*\r\n', encoding="utf-8")
    return str(launcher)
