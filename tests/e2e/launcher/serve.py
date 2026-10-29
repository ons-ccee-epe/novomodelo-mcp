"""Entry-point do launcher de dev.

Sobe o FastAPI com uvicorn, SEMPRE em 127.0.0.1 (nunca exposto na rede).

Uso:
    python -m tests.e2e.launcher.serve            # porta 5175
    python -m tests.e2e.launcher.serve --port 9000

Variaveis de ambiente relevantes:
    QUERY_TIMEOUT_S  -> força um timeout unico; sem ele, cada caso usa o
                        timeout_s do cases.yaml (por caso/grupo)
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
            "uvicorn nao instalado. Rode: pip install -r tests/e2e/launcher/requirements.txt",
            file=sys.stderr,
        )
        return 1

    # Bind FIXO em loopback — o launcher nunca escuta na rede.
    uvicorn.run(
        "tests.e2e.launcher.app:app",
        host="127.0.0.1",
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
