#!/usr/bin/env python3
"""Um `cobre` FALSO para testes: imita o contrato `--json` da CLI real.

Alcançado via `COBRE_BIN` (ver `find_cobre`). O adaptador antepõe
`--color never`; o primeiro argumento após o subcomando pode sinalizar um
cenário de falha de transporte, para exercer os códigos estáveis sem binário
real:

- `--mode=error`  : ecoa envelope de erro e sai com código 3.
- `--mode=timeout`: dorme além de qualquer timeout de teste (prova o `-1`).
- `--mode=nonjson`: imprime texto não-JSON (prova o envelope com texto bruto).

Sem flag de modo, o `version` imprime o formato de TEXTO real da CLI (primeira
linha separada por espaço, demais `label: valor`) e sai com 0; os demais
subcomandos (ex.: `schema export`) ecoam um envelope `status=ok` com o argv
recebido (menos o `--color never`), para que o teste afirme o subcomando exato.
"""

import json
import sys
import time

# Texto real de `cobre version`: primeira linha separada por espaço, demais
# `label: valor`. A versão `v9.9.9` é um EXEMPLO de fixture, não um invariante.
VERSION_TEXT = (
    "cobre   v9.9.9\n"
    "solver: HiGHS 1.13.1\n"
    "comm:   local\n"
    "zstd:   enabled\n"
    "arch:   x86_64-linux\n"
    "build:  release (lto=thin)\n"
)

argv = sys.argv[1:]
if argv[:2] == ["--color", "never"]:
    argv = argv[2:]

mode = None
for a in argv:
    if a.startswith("--mode="):
        mode = a.split("=", 1)[1]

subargv = [a for a in argv if not a.startswith("--mode=")]

if mode == "timeout":
    time.sleep(30)
    sys.exit(0)

if mode == "nonjson":
    print("isto nao e json: falha simulada da CLI")
    sys.exit(1)

if mode == "error":
    print(json.dumps({"status": "error", "diagnostics": ["falha simulada"]}))
    sys.exit(3)

if subargv[:1] == ["version"]:
    sys.stdout.write(VERSION_TEXT)
    sys.exit(0)

print(
    json.dumps(
        {
            "status": "ok",
            "argv": subargv,
            "version": "9.9.9",
            "backend": "clarabel",
            "build": {"profile": "release", "target": "x86_64"},
        }
    )
)
sys.exit(0)
