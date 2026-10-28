"""Caminho nunca é URL: o guard recusa esquema remoto, com ou sem workspace, porque a
única saída de rede do MCP é a checagem de versões."""

import dataclasses
from pathlib import Path

import pytest

from novomodelo_mcp.adapters.paths import ensure_in_workspace
from novomodelo_mcp.config import load_settings

URLS = [
    "http://127.0.0.1:9/exfil?dado=x",
    "https://exemplo.org/a.parquet",
    "s3://bucket/k.parquet",
    "hf://datasets/x/y.parquet",
]


@pytest.mark.parametrize("workspace", [None, "ws"])
@pytest.mark.parametrize("url", URLS)
def test_guard_recusa_url(tmp_path, workspace, url):
    settings = dataclasses.replace(load_settings(), workspace=str(tmp_path) if workspace else None)
    err = ensure_in_workspace(url, settings=settings)
    assert err and err["status"] == "error" and err["exit_code"] == 22


@pytest.mark.parametrize("caminho", ["C:\\Users\\a\\caso", "C:/Users/a/caso"])
def test_letra_de_unidade_nao_e_url(caminho):
    settings = dataclasses.replace(load_settings(), workspace=None)
    assert ensure_in_workspace(caminho, settings=settings) is None


def test_nul_no_caminho_vira_envelope(tmp_path):
    settings = dataclasses.replace(load_settings(), workspace=str(tmp_path))
    err = ensure_in_workspace(str(tmp_path / "a\0b"), settings=settings)
    assert err and err["exit_code"] == 22


def test_nul_no_caminho_vira_envelope_quando_resolve_nao_levanta(tmp_path, monkeypatch):
    # O `resolve()` do Windows no Python 3.13+ devolve o caminho com NUL sem levantar.
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: self)
    settings = dataclasses.replace(load_settings(), workspace=str(tmp_path))
    err = ensure_in_workspace(str(tmp_path / "a\0b"), settings=settings)
    assert err and err["exit_code"] == 22


def test_deck_read_parquet_com_url_nao_sai_para_a_rede(tmp_path, monkeypatch):
    import http.server
    import threading

    from novomodelo_mcp.tools.deck import register_deck

    hits = []

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    class _Cap:
        tools = {}

        def tool(self, *a, **k):
            def deco(fn):
                self.tools[fn.__name__] = fn
                return fn

            return deco

    monkeypatch.chdir(tmp_path)
    cap = _Cap()
    register_deck(cap, dataclasses.replace(load_settings(), workspace=str(tmp_path)))
    url = f"http://127.0.0.1:{srv.server_port}/exfil?dado=x"
    try:
        for nome in ("deck_read_parquet", "deck_describe_parquet"):
            assert cap.tools[nome](url)["status"] == "error"
    finally:
        srv.shutdown()
    assert hits == []
