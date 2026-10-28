"""`docs_search`: busca por palavra (FTS5) nas seções, com os termos do glossário traduzidos."""

import dataclasses
import json

import pytest

from novomodelo_mcp.adapters import reference as REF
from novomodelo_mcp.config import load_settings

PAGINAS = {
    "math/risk-measures.md": """---
title: Risk Measures
---

## 2 Conditional Value-at-Risk (CVaR)

CVaR averages the worst outcomes of the cost distribution.

## 3 Convex Combination

A blend of expectation and CVaR.
""",
    "math/inflow-nonnegativity.md": """---
title: Inflow Non-Negativity
---

## 1 Motivation

Sampled inflows can be negative; the model truncates or penalises them.
""",
    "running/performance.md": """---
title: Performance
---

## Threads

Use more threads for the backward pass.
""",
    "reference/glossary.md": """---
title: Glossary
---

| English | Portuguese | Definition |
| ------- | ---------- | ---------- |
| Inflow  | Afluência / Vazão natural | Water. |
""",
}


@pytest.fixture
def settings(tmp_path):
    for rel, text in PAGINAS.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return dataclasses.replace(load_settings(), docs_dir=str(tmp_path), max_summary_chars=2000)


def _top(env):
    return [f"{r['pagina']}#{r['secao']}" for r in env["resultados"]]


def test_acha_a_secao_certa_no_top_3(settings):
    env = REF.search_docs(settings, "CVaR", k=5)
    assert env["status"] == "ok"
    assert "math/risk-measures#2-conditional-value-at-risk-cvar" in _top(env)[:3]
    assert {"pagina", "secao", "titulo", "trecho", "score"} <= set(env["resultados"][0])


def test_acento_e_caixa_nao_importam(settings):
    assert _top(REF.search_docs(settings, "cvar", k=5)) == _top(
        REF.search_docs(settings, "CVAR", k=5)
    )
    assert any(
        t.startswith("math/inflow-nonnegativity")
        for t in _top(REF.search_docs(settings, "Inflows", k=5))[:3]
    )


def test_termo_do_glossario_e_traduzido(settings):
    env = REF.search_docs(settings, "afluência negativa", k=5)
    assert env["termos_do_glossario"] == ["Inflow"]
    assert any(t.startswith("math/inflow-nonnegativity") for t in _top(env)[:3])


@pytest.mark.parametrize(
    "consulta",
    ['"CVaR', "CVaR*", "-inflow", "NEAR(a b)", "a AND OR NOT", "inflow:x", "(", "^", "''"],
)
def test_caracteres_do_fts5_nao_quebram(settings, consulta):
    env = REF.search_docs(settings, consulta, k=5)
    assert env["status"] == "ok" or env.get("exit_code") == 22, env


def test_consulta_vazia_e_erro_22(settings):
    env = REF.search_docs(settings, "   o que é ?", k=5)
    assert env["status"] == "error" and env["exit_code"] == 22


def test_resposta_dentro_do_teto(settings):
    env = REF.search_docs(settings, "CVaR inflow threads", k=20)
    assert len(json.dumps(env, ensure_ascii=False)) <= settings.max_summary_chars
    assert all(len(r["trecho"]) <= 300 for r in env["resultados"])


def test_k_limitado(settings):
    assert len(REF.search_docs(settings, "the", k=999)["resultados"]) <= 20


def test_indice_embutido_real_responde(monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_DOCS_DIR", raising=False)
    env = REF.search_docs(dataclasses.replace(load_settings(), docs_dir=None), "FPHA", k=5)
    assert env["status"] == "ok" and env["resultados"]
    assert any(r["pagina"] == "math/hydro-production-models" for r in env["resultados"])
