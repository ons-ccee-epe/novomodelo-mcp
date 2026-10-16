"""Permite `python -m novomodelo_mcp`.

Arranque robusto: com o `src/` no PYTHONPATH, o servidor sobe sem depender do
editable install do pacote (que se mostrou frágil no layout src/ + Python 3.14).
"""
from __future__ import annotations

from .server import main

if __name__ == "__main__":
    main()
