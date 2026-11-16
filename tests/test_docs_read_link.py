"""`docs_read(page)` aceita o caminho de um link copiado de uma página das docs."""

import dataclasses

import pytest

from novomodelo_mcp.adapters import reference as REF
from novomodelo_mcp.config import load_settings

PAGINA = """---
title: Hydro Production Models
description: How generation depends on head.
---

## 2 Constant Productivity

Constant text.

## 3 FPHA

FPHA text.
"""


@pytest.fixture
def settings(tmp_path):
    (tmp_path / "math").mkdir()
    (tmp_path / "math" / "hydro.md").write_text(PAGINA, encoding="utf-8")
    (tmp_path / "energy").mkdir()
    (tmp_path / "energy" / "balance.md").write_text(
        "---\ntitle: Balance\ndescription: Desc.\n---\n\nBalance text.\n", encoding="utf-8"
    )
    return dataclasses.replace(load_settings(), docs_dir=str(tmp_path), max_summary_chars=20000)


@pytest.mark.parametrize(
    "link",
    [
        "/math/hydro",
        "/math/hydro/",
        "/en/math/hydro",
        "en/math/hydro/",
        "/docs/en/math/hydro/",
        "docs/math/hydro",
    ],
)
def test_link_copiado_abre_a_pagina_pelo_id(settings, link):
    env = REF.read_doc(settings, link, 20000)
    assert env["status"] == "ok", env
    assert env["page"] == "math/hydro"
    assert "FPHA text." in env["content"]


def test_pagina_que_comeca_com_en_sem_barra_nao_perde_o_prefixo(settings):
    env = REF.read_doc(settings, "energy/balance", 20000)
    assert env["status"] == "ok", env
    assert env["page"] == "energy/balance"


def test_ancora_do_link_vira_a_secao(settings):
    env = REF.read_doc(settings, "/en/math/hydro/#3-fpha", 20000)
    assert env["status"] == "ok", env
    assert env["page"] == "math/hydro" and env["secao"] == "3-fpha"
    assert "FPHA text." in env["content"] and "Constant text." not in env["content"]


def test_secao_explicita_vence_a_ancora_do_link(settings):
    env = REF.read_doc(settings, "/en/math/hydro#3-fpha", 20000, section="2-constant-productivity")
    assert env["status"] == "ok", env
    assert env["secao"] == "2-constant-productivity"
    assert "Constant text." in env["content"] and "FPHA text." not in env["content"]


@pytest.mark.parametrize("link", ["/en/../../../../etc/hosts", "docs/en/../../../x/#a"])
def test_link_com_prefixo_continua_preso_a_raiz_das_docs(settings, link):
    env = REF.read_doc(settings, link, 20000)
    assert env["status"] == "error"
    assert "fora do docs root" in env["diagnostics"][0]
