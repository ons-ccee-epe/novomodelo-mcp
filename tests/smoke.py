#!/usr/bin/env python3
"""Smoke test offline: exercita o adaptador e o shaping sem dependências externas.

Roda com: python3 tests/smoke.py   (a partir da raiz do projeto)
Não importa `mcp`; valida a lógica compartilhada contra o cobre-bridge falso.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from cobre_mcp.adapters.bridge import run_bridge          # noqa: E402
from cobre_mcp.config import load_settings                # noqa: E402
from cobre_mcp.tools.shaping import cap_envelope          # noqa: E402
from _fakes import fake_bin                                # noqa: E402

FAKE = fake_bin("fake_cobre_bridge.py")


def _settings():
    os.environ["COBRE_BRIDGE_BIN"] = f"{sys.executable} {FAKE}".split()[0]
    # Executa o fake via interpretador atual, com caminho absoluto.
    return load_settings()


def test_ok_envelope():
    os.environ["COBRE_BRIDGE_BIN"] = FAKE  # é executável (shebang)
    env = run_bridge(["check", "newave", "/caminho/caso"], settings=load_settings())
    assert env["status"] == "ok", env
    assert env["exit_code"] == 0, env
    assert env["command"] == "check newave", env
    # logs em stderr não podem contaminar o parse do JSON em stdout
    assert env["summary"]["args"][0] == "check", env


def test_error_envelope():
    os.environ["COBRE_BRIDGE_BIN"] = FAKE
    env = run_bridge(["boom"], settings=load_settings())
    assert env["status"] == "error", env
    assert env["exit_code"] == 3, env


def test_missing_binary():
    os.environ["COBRE_BRIDGE_BIN"] = "/nao/existe/cobre-bridge-xyz"
    env = run_bridge(["check", "newave", "x"], settings=load_settings())
    assert env["status"] == "error", env
    assert env["exit_code"] in (126, 127), env


def test_cap_diagnostics():
    s = load_settings()
    big = {"diagnostics": [f"d{i}" for i in range(s.max_diagnostics + 10)]}
    out = cap_envelope(big, s)
    assert len(out["diagnostics"]) == s.max_diagnostics + 1, out
    assert "omitidos" in out["diagnostics"][-1], out


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passaram")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
