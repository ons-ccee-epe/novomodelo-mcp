"""Tools de referência (schema/docs): pastas configuradas, embutidas e ausentes."""

from pathlib import Path

from novomodelo_mcp.adapters import reference as REF
from novomodelo_mcp.config import load_settings


def test_schema_list_and_get(tmp_path, monkeypatch):
    (tmp_path / "hydros.schema.json").write_text('{"type":"object"}', encoding="utf-8")
    (tmp_path / "config.schema.json").write_text('{"type":"object"}', encoding="utf-8")
    monkeypatch.setenv("NOVOMODELO_MCP_SCHEMAS_DIR", str(tmp_path))
    s = load_settings()
    assert REF.list_schema_types(s) == ["config", "hydros"]
    r = REF.read_schema(s, "hydros")
    assert r["status"] == "ok" and r["schema"] == {"type": "object"}, r
    assert REF.read_schema(s, "../secret")["status"] == "error"


def test_docs_list_and_read(tmp_path, monkeypatch):
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "cli-reference.md").write_text("# CLI\nconteudo", encoding="utf-8")
    monkeypatch.setenv("NOVOMODELO_MCP_DOCS_DIR", str(tmp_path))
    s = load_settings()
    lst = REF.list_docs(s)
    assert "reference/cli-reference" in lst["pages"], lst
    doc = REF.read_doc(s, "reference/cli-reference", 10000)
    assert doc["status"] == "ok" and "conteudo" in doc["content"], doc
    assert REF.read_doc(s, "../../etc/passwd", 10000)["status"] == "error"


def test_clone_nearby_is_ignored_without_env(tmp_path, monkeypatch):
    """Sem NOVOMODELO_MCP_DOCS_DIR, as docs são sempre as EMBUTIDAS, mesmo com um clone ao lado."""
    monkeypatch.delenv("NOVOMODELO_MCP_DOCS_DIR", raising=False)
    clone = tmp_path / "novomodelo-docs" / "src" / "content" / "docs"
    clone.mkdir(parents=True)
    (clone / "pagina-do-clone.md").write_text("# outra versao", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    lst = REF.list_docs(load_settings())
    assert lst["status"] == "ok" and lst["count"] > 0, lst
    assert "pagina-do-clone" not in lst["pages"], lst
    assert str(Path("_bundled") / "docs") in lst["docs_dir"], lst


def test_docs_unavailable_messages_when_bundled_missing(monkeypatch):
    """Sem as embutidas (build quebrado), a mensagem manda reinstalar o MCP, não clonar nada;
    com NOVOMODELO_MCP_DOCS_DIR inválido, o caminho aparece na mensagem."""
    monkeypatch.delenv("NOVOMODELO_MCP_DOCS_DIR", raising=False)
    monkeypatch.setattr(REF, "_bundled_dir", lambda name: None)
    und = REF.list_docs(load_settings())
    assert und["status"] == "error" and "reinstale o MCP" in und["diagnostics"][0], und
    assert "clone" not in " ".join(und["diagnostics"]), und
    monkeypatch.setenv("NOVOMODELO_MCP_DOCS_DIR", "/tmp/nao/existe/xyz")
    bad = REF.read_doc(load_settings(), "foo", 100)
    assert bad["status"] == "error" and "/tmp/nao/existe/xyz" in bad["diagnostics"][0], bad
