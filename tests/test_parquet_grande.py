"""Parquet grande ou pasta de resultados não é carregado inteiro na memória: o describe
e o edit recusam sem ler e apontam o deck_sql (SUMMARIZE), que lê sob demanda."""

import dataclasses

import pytest

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.deck import register_deck

pl = pytest.importorskip("polars")


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def ws(tmp_path, monkeypatch):
    res = tmp_path / "estudo d'água" / "output" / "simulation" / "hydros"
    for cen in range(3):
        (res / f"scenario_id={cen}").mkdir(parents=True)
        pl.DataFrame({"x": [1.0] * 10}).write_parquet(res / f"scenario_id={cen}" / "d.parquet")
    deck = tmp_path / "caso" / "system"
    deck.mkdir(parents=True)
    pl.DataFrame({"hydro_id": [0, 1], "v": [1.0, 2.0]}).write_parquet(deck / "h.parquet")
    mcp = _CaptureMCP()
    settings = dataclasses.replace(load_settings(), workspace=str(tmp_path))
    register_deck(mcp, settings)
    return mcp.tools, res, deck / "h.parquet", settings


def _sem_leitura_inteira(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("leu o parquet inteiro na memória")

    monkeypatch.setattr(pl, "read_parquet", proibido)


def test_describe_de_pasta_recusa_sem_ler_e_aponta_o_summarize(ws, monkeypatch):
    tools, res, _, _ = ws
    _sem_leitura_inteira(monkeypatch)
    r = tools["deck_describe_parquet"](str(res))
    assert r["status"] == "error" and "SUMMARIZE" in r["next"], r
    assert "/**/*.parquet" in r["next"] and "d''água" in r["next"], r


def test_describe_de_arquivo_acima_do_teto_recusa_sem_ler(ws, monkeypatch):
    tools, _, h, settings = ws
    mcp = _CaptureMCP()
    register_deck(mcp, dataclasses.replace(settings, max_read_bytes=10))
    _sem_leitura_inteira(monkeypatch)
    r = mcp.tools["deck_describe_parquet"](str(h))
    assert r["status"] == "error" and "NOVOMODELO_MCP_MAX_READ_BYTES" in str(r), r


def test_describe_de_arquivo_do_deck_continua_igual(ws):
    tools, _, h, _ = ws
    r = tools["deck_describe_parquet"](str(h))
    assert r["status"] == "ok" and r["nrows"] == 2 and r["describe"], r


def test_edit_de_parquet_acima_do_teto_recusa_sem_ler(ws, monkeypatch):
    tools, res, _, _ = ws
    _sem_leitura_inteira(monkeypatch)
    r = tools["deck_edit_parquet"](str(res), where={"x": 1.0}, set_values={"x": 2.0}, dry_run=True)
    assert r["status"] == "error", r
