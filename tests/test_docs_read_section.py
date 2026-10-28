"""`docs_read(page, secao)`: só a seção (por âncora ou título); `docs_list` com título e descrição."""

import dataclasses

import pytest

from novomodelo_mcp.adapters import reference as REF
from novomodelo_mcp.config import load_settings

PAGINA = """---
title: Hydro Production Models
description: How generation depends on head.
---

Intro.

## 2 Constant Productivity

Constant text.

### 2.1 Details

Detail text.

```bash
# isto é comentário de shell, não título
echo ok
```

## 3 FPHA

FPHA text.

## 3 FPHA

Second section with the same title.
"""


@pytest.fixture
def settings(tmp_path):
    (tmp_path / "math").mkdir()
    (tmp_path / "math" / "hydro.md").write_text(PAGINA, encoding="utf-8")
    (tmp_path / "math" / "outra.md").write_text(
        "---\ntitle: Outra\ndescription: Desc.\n---\n\n## A\n\nx\n", encoding="utf-8"
    )
    return dataclasses.replace(load_settings(), docs_dir=str(tmp_path), max_summary_chars=20000)


def test_secao_por_ancora_inclui_as_subsecoes_e_para_na_proxima_do_mesmo_nivel(settings):
    env = REF.read_doc(settings, "math/hydro", 20000, section="2-constant-productivity")
    assert env["status"] == "ok" and env["secao"] == "2-constant-productivity"
    assert "Constant text." in env["content"] and "Detail text." in env["content"]
    assert "echo ok" in env["content"] and "FPHA text." not in env["content"]


def test_secao_por_titulo_ignora_caixa_e_acento(settings):
    env = REF.read_doc(settings, "math/hydro", 20000, section="2.1 details")
    assert env["status"] == "ok" and "Detail text." in env["content"]
    assert "Constant text." not in env["content"]


def test_comentario_em_bloco_de_codigo_nao_e_titulo(settings):
    ancoras = [
        s["ancora"]
        for s in REF.read_doc(settings, "math/hydro", 20000, section="nao-existe")["secoes"]
    ]
    assert not any("comentario" in a for a in ancoras)


def test_titulo_repetido_ganha_sufixo_como_no_site(settings):
    env = REF.read_doc(settings, "math/hydro", 20000, section="3-fpha-1")
    assert "Second section" in env["content"] and "FPHA text." not in env["content"]


def test_secao_inexistente_lista_as_secoes(settings):
    env = REF.read_doc(settings, "math/hydro", 20000, section="nao-existe")
    assert env["status"] == "error" and env["exit_code"] == 2
    assert {"titulo": "3 FPHA", "ancora": "3-fpha"} in env["secoes"]


def test_ancora_do_docs_search_abre_a_mesma_secao(settings):
    for r in REF.search_docs(settings, "FPHA detail constant", k=10)["resultados"]:
        if not r["secao"]:
            continue
        env = REF.read_doc(settings, r["pagina"], 20000, section=r["secao"])
        assert env["status"] == "ok" and env["titulo"] == r["titulo"], r


def test_docs_list_traz_titulo_e_descricao(settings):
    env = REF.list_docs(settings)
    assert env["pages"] == ["math/hydro", "math/outra"]
    assert env["itens"] == [
        {
            "pagina": "math/hydro",
            "titulo": "Hydro Production Models",
            "descricao": "How generation depends on head.",
        },
        {"pagina": "math/outra", "titulo": "Outra", "descricao": "Desc."},
    ]


def test_docs_list_embutido_tem_titulo_em_todas_as_paginas(monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_DOCS_DIR", raising=False)
    env = REF.list_docs(dataclasses.replace(load_settings(), docs_dir=None))
    assert env["count"] > 0 and all(i["titulo"] for i in env["itens"])
