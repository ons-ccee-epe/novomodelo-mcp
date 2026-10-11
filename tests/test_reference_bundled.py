"""Testes do fallback EMBUTIDO de docs/schemas (funciona offline, sem clone/env var).

Requisito de produto: as tools ``docs_*`` e ``schema_*`` devem funcionar assim
que o MCP e conectado, sem ``NOVOMODELO_MCP_DOCS_DIR``/``NOVOMODELO_MCP_SCHEMAS_DIR``, sem clone
``novomodelo-docs`` e sem o binario ``novomodelo``. Estes testes forcam esse cenario e
verificam que o conteudo vem do snapshot embutido em ``novomodelo_mcp/_bundled``.
"""
import pytest

from novomodelo_mcp.adapters import reference as R
from novomodelo_mcp.config import load_settings


@pytest.fixture
def offline_settings(monkeypatch):
    """Settings sem env vars e SEM auto-descoberta (forca o fallback embutido)."""
    monkeypatch.delenv("NOVOMODELO_MCP_DOCS_DIR", raising=False)
    monkeypatch.delenv("NOVOMODELO_MCP_SCHEMAS_DIR", raising=False)
    monkeypatch.delenv("NOVOMODELO_MCP_SOLVER_BIN", raising=False)
    # Neutraliza a auto-descoberta de clone novomodelo-docs e o cache, para o teste
    # exercitar deterministicamente o fallback embutido.
    monkeypatch.setattr(R, "_discover_docs_dir", lambda: None)
    R._DOCS_DISCOVER_CACHE.clear()
    R._SCHEMA_EXPORT_CACHE.clear()
    return load_settings()


# --- o snapshot embutido existe e e localizavel --------------------------- #

def test_bundled_dirs_present():
    assert R._bundled_dir("docs") is not None, "snapshot de docs ausente no pacote"
    assert R._bundled_dir("schemas") is not None, "snapshot de schemas ausente no pacote"


# --- schemas: funcionam offline ------------------------------------------- #

def test_schema_list_offline_uses_bundled(offline_settings):
    types = R.list_schema_types(offline_settings)
    assert len(types) > 0, "schema_list deveria listar os schemas embutidos offline"
    # tipos-chave que o deck Novomodelo exige
    for expected in ("hydros", "config", "penalties", "stages"):
        assert expected in types, f"schema '{expected}' ausente no embutido"


def test_schema_get_offline_returns_valid_json(offline_settings):
    r = R.read_schema(offline_settings, "hydros")
    assert r["status"] == "ok"
    assert r["tipo"] == "hydros"
    assert isinstance(r["schema"], dict) and r["schema"], "schema vazio/invalido"


# --- docs: funcionam offline ---------------------------------------------- #

def test_docs_list_offline_uses_bundled(offline_settings):
    d = R.list_docs(offline_settings)
    assert d["status"] == "ok"
    assert d["count"] > 0, "docs_list deveria listar as paginas embutidas offline"
    # paginas de referencia esperadas
    assert any(p.replace("\\", "/").startswith("reference/") for p in d["pages"])


def test_docs_read_offline_returns_content(offline_settings):
    r = R.read_doc(offline_settings, "reference/cli-reference", 5000)
    assert r["status"] == "ok"
    assert r["page"] == "reference/cli-reference"
    assert r["content"], "conteudo da pagina veio vazio"


def test_docs_read_rejects_path_escape(offline_settings):
    # tentativa de escapar da raiz de docs deve ser recusada
    r = R.read_doc(offline_settings, "../../../../etc/passwd", 100)
    assert r["status"] == "error"
