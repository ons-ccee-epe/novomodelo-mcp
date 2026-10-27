"""Manipulador de decks: caminhos de campo (get/set), edição de JSON com backup e
escrita atômica, dry_run, resolução de schema e localização da raiz do caso."""

import json
import tempfile
from pathlib import Path


from novomodelo_mcp.adapters import deck_io


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
        r = deck_io.edit_json(str(f), [{"path": "training.limit", "value": 99}], dry_run=True)
        assert r["status"] == "ok" and r["written"] is False, r
        assert json.loads(f.read_text(encoding="utf-8"))["training"]["limit"] == 50, (
            "dry_run gravou!"
        )
        # write real: grava + backup
        r = deck_io.edit_json(str(f), [{"path": "training.limit", "value": 99}])
        assert r["status"] == "ok" and r["written"] is True, r
        assert json.loads(f.read_text(encoding="utf-8"))["training"]["limit"] == 99, r
        assert Path(str(f) + ".bak").exists(), "backup não criado"
        assert (
            json.loads(Path(str(f) + ".bak").read_text(encoding="utf-8"))["training"]["limit"] == 50
        )
        # restaura do backup
        assert deck_io.restore_backup(str(f)) is True
        assert json.loads(f.read_text(encoding="utf-8"))["training"]["limit"] == 50, (
            "restore falhou"
        )


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
