#!/usr/bin/env python3
"""Smoke test do manipulador de decks (stdlib puro; não usa polars/jsonschema).

Novomodelo: caminhos de campo (get/set), edição de JSON com backup + escrita atômica,
dry_run, resolução de schema e localização da raiz do caso.
Roda com: python3 tests/smoke_deck.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novomodelo_mcp.adapters import deck_io  # noqa: E402


def test_path_get_set():
    obj = {"training": {"stopping_rules": [{"type": "iteration_limit", "limit": 50}]}}
    assert deck_io.get_by_path(obj, "training.stopping_rules[0].limit") == 50
    deck_io.set_by_path(obj, "training.stopping_rules[0].limit", 80)
    assert obj["training"]["stopping_rules"][0]["limit"] == 80


def test_edit_json_dry_run_and_write():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "config.json"
        f.write_text(json.dumps({"training": {"limit": 50}}), encoding="utf-8")
        # dry_run: nada gravado
        r = deck_io.edit_json(str(f), [{"path": "training.limit", "value": 99}],
                              dry_run=True)
        assert r["status"] == "ok" and r["written"] is False, r
        assert json.loads(f.read_text(encoding="utf-8"))["training"]["limit"] == 50, "dry_run gravou!"
        # write real: grava + backup
        r = deck_io.edit_json(str(f), [{"path": "training.limit", "value": 99}])
        assert r["status"] == "ok" and r["written"] is True, r
        assert json.loads(f.read_text(encoding="utf-8"))["training"]["limit"] == 99, r
        assert Path(str(f) + ".bak").exists(), "backup não criado"
        assert json.loads(Path(str(f) + ".bak").read_text(encoding="utf-8"))["training"]["limit"] == 50
        # restaura do backup
        assert deck_io.restore_backup(str(f)) is True
        assert json.loads(f.read_text(encoding="utf-8"))["training"]["limit"] == 50, "restore falhou"


def test_edit_json_bad_path():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "config.json"
        f.write_text(json.dumps({"a": 1}), encoding="utf-8")
        r = deck_io.edit_json(str(f), [{"path": "a.b.c", "value": 1}])
        assert r["status"] == "error", r
        assert f.read_text(encoding="utf-8") == json.dumps({"a": 1}), "arquivo não deveria mudar"


def test_resolve_schema_and_case_dir():
    with tempfile.TemporaryDirectory() as d:
        schemas = Path(d) / "schemas"
        schemas.mkdir()
        (schemas / "config.schema.json").write_text("{}", encoding="utf-8")
        case = Path(d) / "caso"
        (case / "system").mkdir(parents=True)
        (case / "config.json").write_text("{}", encoding="utf-8")
        hydros = case / "system" / "hydros.json"
        hydros.write_text("{}", encoding="utf-8")
        assert deck_io.resolve_schema(str(case / "config.json"), str(schemas))
        assert deck_io.resolve_schema(str(hydros), str(schemas)) is None  # sem schema
        assert deck_io.find_case_dir(str(hydros)) == str(case.resolve())


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
