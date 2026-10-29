"""Entry-point do launcher de dev.

Sobe o FastAPI com uvicorn, SEMPRE em 127.0.0.1 (nunca exposto na rede).

Uso:
    python -m novomodelo_mcp_e2e.launcher.serve            # porta 5175
    python -m novomodelo_mcp_e2e.launcher.serve --port 9000

Variaveis de ambiente relevantes:
    NOVOMODELO_LAUNCHER_PASTA_WHEELS -> pasta das wheels do MCP que o disparo aceita
                        em ``mcp``; sem ela, so ``sem`` e aceito
    NOVOMODELO_BATERIA_*             -> configuracao da bateria (``novomodelo_mcp_e2e.config``):
                        pasta de resultados, motor, token
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="launcher.serve",
        description="Sobe o launcher de dev (FastAPI) em 127.0.0.1.",
    )
    parser.add_argument("--port", type=int, default=5175, help="Porta (default: 5175)")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Autoreload do uvicorn (dev). Requer watchfiles.",
    )
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn nao instalado. Rode: uv sync --package novomodelo-mcp-e2e",
            file=sys.stderr,
        )
        return 1

    # Bind FIXO em loopback — o launcher nunca escuta na rede.
    uvicorn.run(
        "novomodelo_mcp_e2e.launcher.app:app",
        host="127.0.0.1",
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
