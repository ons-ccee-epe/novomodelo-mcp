#!/usr/bin/env python3
"""Um `novomodelo` FALSO para testes: imita o contrato da CLI real.

Alcançado via `NOVOMODELO_MCP_SOLVER_BIN` (ver `find_novomodelo`; no Windows via o lançador de
`_fakes.fake_bin`). O adaptador antepõe `--color never`; o primeiro argumento
após o subcomando pode sinalizar um cenário de falha de transporte, para exercer
os códigos estáveis sem binário real:

- `--mode=error`  : ecoa envelope de erro e sai com código 3.
- `--mode=timeout`: dorme além de qualquer timeout de teste (prova o `-1`).
- `--mode=nonjson`: imprime texto não-JSON (prova o envelope com texto bruto).

Subcomandos com comportamento próprio:

- `version`                 : formato de TEXTO real (primeira linha separada por
                              espaço, demais `label: valor`), sai com 0.
- `init --list`             : lista de templates no stdout (texto).
- `init --template T DIR`   : cria DIR/config.json (recusa se existir, salvo --force).
- `run CASE --output OUT …` : dorme FAKE_NOVOMODELO_SLEEP s, cria OUT/training/_SUCCESS
                              (+ metadata.json = FAKE_NOVOMODELO_META, se definido) e sai
                              com FAKE_NOVOMODELO_RC (default 0).

Os demais (ex.: `schema export`) ecoam um envelope `status=ok` com o argv
recebido (menos o `--color never`), para que o teste afirme o subcomando exato.
"""

import json
import os
import sys
import time
from pathlib import Path

# Texto real de `novomodelo version`: primeira linha separada por espaço, demais
# `label: valor`. A versão `v9.9.9` é um EXEMPLO de fixture, não um invariante.
VERSION_TEXT = (
    "novomodelo   v9.9.9\n"
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

if subargv[:1] == ["init"]:
    if "--list" in subargv:
        print("1dtoy             Single-bus hydrothermal toy (fake)")
        sys.exit(0)
    rest = [a for a in subargv[1:] if a != "--force"]
    template = rest[rest.index("--template") + 1]
    target = Path(rest[-1])
    if (target / "config.json").exists() and "--force" not in subargv:
        print("error: target not empty (use --force)", file=sys.stderr)
        sys.exit(1)
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.json").write_text(json.dumps({"template": template}))
    print(f"Created {target} case directory from template '{template}'", file=sys.stderr)
    sys.exit(0)

if subargv[:1] == ["run"]:
    out = Path(subargv[subargv.index("--output") + 1])
    print("fake run: start", flush=True)
    time.sleep(float(os.environ.get("FAKE_NOVOMODELO_SLEEP", "0")))
    rc = int(os.environ.get("FAKE_NOVOMODELO_RC", "0"))
    if rc == 0:
        (out / "training").mkdir(parents=True, exist_ok=True)
        (out / "training" / "_SUCCESS").write_text("")
        if os.environ.get("FAKE_NOVOMODELO_META"):
            (out / "training" / "metadata.json").write_text(os.environ["FAKE_NOVOMODELO_META"])
        print("fake run: done", flush=True)
    else:
        print("fake run: solver falhou", file=sys.stderr, flush=True)
    sys.exit(rc)

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
