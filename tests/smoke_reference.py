#!/usr/bin/env python3
"""Smoke test das tools de referência (schema/docs), stdlib puro.
Roda: python3 tests/smoke_reference.py"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cobre_mcp.adapters import reference as REF   # noqa: E402
from cobre_mcp.config import load_settings         # noqa: E402


def test_schema_list_and_get():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "hydros.schema.json").write_text('{"type":"object"}')
        (Path(d) / "config.schema.json").write_text('{"type":"object"}')
        os.environ["COBRE_SCHEMAS_DIR"] = d
        s = load_settings()
        assert REF.list_schema_types(s) == ["config", "hydros"]
        r = REF.read_schema(s, "hydros")
        assert r["status"] == "ok" and r["schema"] == {"type": "object"}, r
        assert REF.read_schema(s, "../secret")["status"] == "error"
    os.environ.pop("COBRE_SCHEMAS_DIR", None)


def test_docs_list_and_read():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "reference").mkdir()
        (Path(d) / "reference" / "cli-reference.md").write_text("# CLI\nconteudo")
        os.environ["COBRE_DOCS_DIR"] = d
        s = load_settings()
        lst = REF.list_docs(s)
        assert "reference/cli-reference" in lst["pages"], lst
        doc = REF.read_doc(s, "reference/cli-reference", 10000)
        assert doc["status"] == "ok" and "conteudo" in doc["content"], doc
        # traversal deve falhar
        assert REF.read_doc(s, "../../etc/passwd", 10000)["status"] == "error"
    os.environ.pop("COBRE_DOCS_DIR", None)


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passaram")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
