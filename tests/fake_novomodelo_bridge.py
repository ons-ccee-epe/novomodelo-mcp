#!/usr/bin/env python3
"""Um novomodelo-bridge FALSO para testes: imita o contrato --json do bridge real.

Ecoa um envelope {schema_version, command, status, summary, diagnostics} e sai
com código 0 (ou 3 se o primeiro arg for 'boom'). Não faz nada de verdade.
"""

import json
import sys

argv = sys.argv[1:]
if argv[:1] == ["boom"]:
    print(
        json.dumps(
            {
                "schema_version": "1",
                "command": "boom",
                "status": "error",
                "summary": {},
                "diagnostics": ["falha simulada"],
            }
        )
    )
    sys.exit(3)

# ignora as flags --json/--no-color e monta um comando legível
parts = [a for a in argv if not a.startswith("--")]
print("log: iniciando (esta linha nao e JSON)", file=sys.stderr)
print(
    json.dumps(
        {
            "schema_version": "1",
            "command": " ".join(parts[:2]),
            "status": "ok",
            "summary": {"args": parts},
            "diagnostics": [],
        }
    )
)
sys.exit(0)
