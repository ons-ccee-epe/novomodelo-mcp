"""Docs sempre as embutidas; `NOVOMODELO_MCP_DOCS_DIR` só para desenvolvimento, com aviso."""

import dataclasses
import urllib.error

import pytest

from novomodelo_mcp.adapters import reference as REF
from novomodelo_mcp.adapters import versions as V
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.server import build_server


@pytest.fixture(autouse=True)
def _sem_rede_e_caches(monkeypatch):
    V.reset_caches()
    monkeypatch.setattr(
        V,
        "_open",
        lambda req, **k: (_ for _ in ()).throw(urllib.error.URLError("sem rede no teste")),
    )
    yield
    V.reset_caches()


def _settings(**kw):
    return dataclasses.replace(load_settings(), **kw)


def test_clone_ao_lado_sem_variavel_usa_as_embutidas(tmp_path, monkeypatch):
    clone = tmp_path / "novomodelo-docs" / "src" / "content" / "docs"
    clone.mkdir(parents=True)
    (clone / "pagina-do-clone.md").write_text("# outra versão", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    lst = REF.list_docs(_settings(docs_dir=None))
    assert lst["status"] == "ok" and "pagina-do-clone" not in lst["pages"]
    assert lst["docs_dir"].endswith(str(REF.Path("_bundled") / "docs"))
    assert REF.docs_origin(_settings(docs_dir=None))["origin"] == "embutidas"


def test_pasta_de_desenvolvimento_e_usada_e_avisada(tmp_path):
    dev = tmp_path / "docs-dev"
    (dev / "math" / "_impl").mkdir(parents=True)
    (dev / "math" / "pagina.mdx").write_text("# P", encoding="utf-8")
    (dev / "math" / "_impl" / "_trecho.mdx").write_text("trecho", encoding="utf-8")
    settings = _settings(docs_dir=str(dev))
    lst = REF.list_docs(settings)
    assert lst["pages"] == ["math/pagina"]
    origem = REF.docs_origin(settings)
    assert origem == {"origin": "pasta_de_desenvolvimento", "path": str(dev)}
    assert any("pasta de desenvolvimento" in a for a in V.version_warnings(settings))


def test_server_info_mostra_a_origem_das_docs(monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_DOCS_DIR", raising=False)
    info = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}["server_info"]()
    assert info["docs"]["origin"] == "embutidas" and info["docs"]["version"]


def test_descoberta_de_clone_nao_existe_mais():
    for nome in ("_discover_docs_dir", "_candidate_bases", "_CLONE_HINT", "_search_docs_in"):
        assert not hasattr(REF, nome), nome
