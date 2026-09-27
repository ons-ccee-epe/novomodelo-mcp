#!/usr/bin/env python3
"""Smoke test das tools de referência (schema/docs), stdlib puro.
Roda: python3 tests/smoke_reference.py"""
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


def test_discover_prefers_content_subpath():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        content = base / "cobre-docs" / "src" / "content" / "docs"
        content.mkdir(parents=True)
        (content / "intro.md").write_text("# intro")
        found = REF._search_docs_in([base])
        assert found is not None and Path(found) == content, found


def test_discover_accepts_repo_root_layout():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        root = base / "cobre-docs"
        root.mkdir()
        (root / "guide.mdx").write_text("# guide")
        found = REF._search_docs_in([base])
        assert found is not None and Path(found) == root, found


def test_discover_none_when_absent():
    with tempfile.TemporaryDirectory() as d:
        assert REF._search_docs_in([Path(d)]) is None


def test_docs_unavailable_messages_distinguish_and_hint():
    os.environ.pop("COBRE_DOCS_DIR", None)
    REF._DOCS_DISCOVER_CACHE.clear()
    with tempfile.TemporaryDirectory() as empty:
        # força bases vazias para a auto-descoberta não achar nada
        orig = REF._candidate_bases
        REF._candidate_bases = lambda: [Path(empty)]
        try:
            s = load_settings()
            und = REF.list_docs(s)
            assert und["status"] == "error", und
            assert "nao definido" in und["diagnostics"][0], und
            assert "cobre-docs" in und["diagnostics"][1], und
            os.environ["COBRE_DOCS_DIR"] = "/tmp/nao/existe/xyz"
            s2 = load_settings()
            bad = REF.read_doc(s2, "foo", 100)
            assert bad["status"] == "error" and "/tmp/nao/existe/xyz" in bad["diagnostics"][0], bad
        finally:
            REF._candidate_bases = orig
            os.environ.pop("COBRE_DOCS_DIR", None)
            REF._DOCS_DISCOVER_CACHE.clear()



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
