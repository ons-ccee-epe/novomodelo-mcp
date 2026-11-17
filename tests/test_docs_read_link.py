"""`docs_read` aceita a página como as próprias docs a citam: link, endereço do site ou pt-BR."""

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


def test_identificador_da_pagina_nao_ganha_nota(settings):
    env = REF.read_doc(settings, "math/hydro", 20000)
    assert env["status"] == "ok" and env["page"] == "math/hydro"
    assert "note" not in env


@pytest.mark.parametrize(
    "pagina",
    [
        "/en/math/hydro/",
        "en/math/hydro",
        "/math/hydro/",
        "/docs/en/math/hydro/",
        "https://docs.exemplo.org/docs/en/math/hydro/",
    ],
)
def test_link_ou_endereco_le_a_pagina(settings, pagina):
    env = REF.read_doc(settings, pagina, 20000)
    assert env["status"] == "ok", env
    assert env["page"] == "math/hydro"
    assert "math/hydro" in env["note"]


@pytest.mark.parametrize("pagina", ["pt-br/math/hydro", "/docs/math/hydro/", "/pt-br/math/hydro/"])
def test_pagina_em_portugues_le_a_fonte_em_ingles(settings, pagina):
    env = REF.read_doc(settings, pagina, 20000)
    assert env["status"] == "ok", env
    assert env["page"] == "math/hydro"
    assert "inglês" in env["note"]


def test_pagina_que_comeca_com_en_sem_barra_nao_perde_o_prefixo(settings):
    env = REF.read_doc(settings, "energy/balance", 20000)
    assert env["status"] == "ok" and env["page"] == "energy/balance", env
    assert "note" not in env


def test_ancora_do_link_vira_a_secao(settings):
    env = REF.read_doc(settings, "/en/math/hydro/#2-constant-productivity", 20000)
    assert env["status"] == "ok" and env["section"] == "2-constant-productivity"
    assert "Constant text." in env["content"] and "FPHA text." not in env["content"]


def test_secao_informada_vale_mais_que_a_ancora(settings):
    env = REF.read_doc(settings, "/en/math/hydro/#2-constant-productivity", 20000, section="3 FPHA")
    assert env["status"] == "ok" and "FPHA text." in env["content"]


@pytest.mark.parametrize(
    "pagina", ["../../etc/passwd", "/en/../../etc/passwd", "en/../../x", "docs/en/../../../x/#a"]
)
def test_continua_recusando_o_que_sai_da_raiz(settings, pagina):
    env = REF.read_doc(settings, pagina, 20000)
    assert env["status"] == "error" and env["exit_code"] == 13
    assert "content" not in env


def test_caminho_absoluto_do_sistema_nao_le_fora_da_raiz(settings):
    env = REF.read_doc(settings, "/etc/passwd", 20000)
    assert env["status"] == "error" and "content" not in env
