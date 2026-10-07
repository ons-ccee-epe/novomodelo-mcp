#!/usr/bin/env python3
"""Um `cobre` FALSO para testes: imita `init` e `run` sem resolver nada.

- `init --list`              -> lista de templates no stdout
- `init --template T DIR`    -> cria DIR/config.json (recusa se existir, salvo --force)
- `run CASE --output OUT ...`-> dorme FAKE_COBRE_SLEEP s, cria OUT/training/_SUCCESS
                                (+ metadata.json = FAKE_COBRE_META, se definido)
                                e sai com FAKE_COBRE_RC (default 0)
"""
import json
import os
import sys
import time
from pathlib import Path

argv = sys.argv[1:]
if argv[:2] == ["--color", "never"]:
    argv = argv[2:]

if argv[:1] == ["init"]:
    if "--list" in argv:
        print("1dtoy             Single-bus hydrothermal toy (fake)")
        sys.exit(0)
    rest = [a for a in argv[1:] if a != "--force"]
    template = rest[rest.index("--template") + 1]
    target = Path(rest[-1])
    if (target / "config.json").exists() and "--force" not in argv:
        print("error: target not empty (use --force)", file=sys.stderr)
        sys.exit(1)
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.json").write_text(json.dumps({"template": template}))
    print(f"Created {target} case directory from template '{template}'", file=sys.stderr)
    sys.exit(0)

if argv[:1] == ["run"]:
    out = Path(argv[argv.index("--output") + 1])
    print("fake run: start", flush=True)
    time.sleep(float(os.environ.get("FAKE_COBRE_SLEEP", "0")))
    rc = int(os.environ.get("FAKE_COBRE_RC", "0"))
    if rc == 0:
        (out / "training").mkdir(parents=True, exist_ok=True)
        (out / "training" / "_SUCCESS").write_text("")
        if os.environ.get("FAKE_COBRE_META"):
            (out / "training" / "metadata.json").write_text(os.environ["FAKE_COBRE_META"])
        print("fake run: done", flush=True)
    else:
        print("fake run: solver falhou", file=sys.stderr, flush=True)
    sys.exit(rc)

print(f"fake cobre: comando desconhecido {argv}", file=sys.stderr)
sys.exit(2)
