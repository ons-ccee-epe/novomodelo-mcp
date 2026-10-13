#!/usr/bin/env python3
"""Smoke test das tools de referência (schema/docs), stdlib puro.
Roda: python3 tests/smoke_reference.py"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novomodelo_mcp.adapters import reference as REF   # noqa: E402
from novomodelo_mcp.config import load_settings         # noqa: E402


def test_schema_list_and_get():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "hydros.schema.json").write_text('{"type":"object"}')
        (Path(d) / "config.schema.json").write_text('{"type":"object"}')
        os.environ["NOVOMODELO_MCP_SCHEMAS_DIR"] = d
        s = load_settings()
        assert REF.list_schema_types(s) == ["config", "hydros"]
        r = REF.read_schema(s, "hydros")
        assert r["status"] == "ok" and r["schema"] == {"type": "object"}, r
        assert REF.read_schema(s, "../secret")["status"] == "error"
    os.environ.pop("NOVOMODELO_MCP_SCHEMAS_DIR", None)


def test_docs_list_and_read():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "reference").mkdir()
        (Path(d) / "reference" / "cli-reference.md").write_text("# CLI\nconteudo")
        os.environ["NOVOMODELO_MCP_DOCS_DIR"] = d
        s = load_settings()
        lst = REF.list_docs(s)
        assert "reference/cli-reference" in lst["pages"], lst
        doc = REF.read_doc(s, "reference/cli-reference", 10000)
        assert doc["status"] == "ok" and "conteudo" in doc["content"], doc
        # traversal deve falhar
        assert REF.read_doc(s, "../../etc/passwd", 10000)["status"] == "error"
    os.environ.pop("NOVOMODELO_MCP_DOCS_DIR", None)


def test_clone_nearby_is_ignored_without_env():
    """Sem NOVOMODELO_MCP_DOCS_DIR, as docs são sempre as EMBUTIDAS, mesmo com um clone ao lado."""
    os.environ.pop("NOVOMODELO_MCP_DOCS_DIR", None)
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        clone = Path(d) / "novomodelo-docs" / "src" / "content" / "docs"
        clone.mkdir(parents=True)
        (clone / "pagina-do-clone.md").write_text("# outra versao")
        os.chdir(d)
        try:
            lst = REF.list_docs(load_settings())
            assert lst["status"] == "ok" and lst["count"] > 0, lst
            assert "pagina-do-clone" not in lst["pages"], lst
            assert str(Path("_bundled") / "docs") in lst["docs_dir"], lst
        finally:
            os.chdir(old_cwd)


def test_docs_unavailable_messages_when_bundled_missing():
    """Sem as embutidas (build quebrado), a mensagem manda reinstalar o MCP, não clonar nada;
    com NOVOMODELO_MCP_DOCS_DIR inválido, o caminho aparece na mensagem."""
    os.environ.pop("NOVOMODELO_MCP_DOCS_DIR", None)
    orig_bundled = REF._bundled_dir
    REF._bundled_dir = lambda name: None
    try:
        und = REF.list_docs(load_settings())
        assert und["status"] == "error" and "reinstale o MCP" in und["diagnostics"][0], und
        assert "clone" not in " ".join(und["diagnostics"]), und
        os.environ["NOVOMODELO_MCP_DOCS_DIR"] = "/tmp/nao/existe/xyz"
        bad = REF.read_doc(load_settings(), "foo", 100)
        assert bad["status"] == "error" and "/tmp/nao/existe/xyz" in bad["diagnostics"][0], bad
    finally:
        REF._bundled_dir = orig_bundled
        os.environ.pop("NOVOMODELO_MCP_DOCS_DIR", None)


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
