"""Caminhos derivados de parâmetros não escapam do workspace nem da raiz de schemas e docs."""
import dataclasses
import json

import pytest

import novomodelo_mcp.tools.deck as deck_tools
from novomodelo_mcp.adapters import reference as REF
from novomodelo_mcp.config import load_settings


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


# ── deck_edit_json(ensure_valid=True): a raiz do caso fica dentro do workspace ─

def _edit_with_validation(monkeypatch, workspace, path):
    validated = []
    monkeypatch.setattr(deck_tools, "validate_deck_binding",
                        lambda case, settings: validated.append(case) or {"status": "ok"})
    mcp = _CaptureMCP()
    deck_tools.register_deck(mcp, dataclasses.replace(load_settings(), workspace=workspace,
                                                      schemas_dir=None))
    env = mcp.tools["deck_edit_json"](str(path), [{"path": "a", "value": 2}], ensure_valid=True)
    return env, validated


def test_caso_acima_do_workspace_nao_e_validado(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text("{}")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "x.json").write_text(json.dumps({"a": 1}))
    env, validated = _edit_with_validation(monkeypatch, str(ws), ws / "x.json")
    assert validated == []
    assert env["case_validation"].startswith("pulada")


def test_caso_dentro_do_workspace_continua_validado(tmp_path, monkeypatch):
    case = tmp_path / "ws" / "caso"
    (case / "system").mkdir(parents=True)
    (case / "config.json").write_text("{}")
    (case / "system" / "x.json").write_text(json.dumps({"a": 1}))
    env, validated = _edit_with_validation(monkeypatch, str(tmp_path / "ws"),
                                           case / "system" / "x.json")
    assert validated == [str(case.resolve())] and env["case_validation"] == "ok"


# ── schema_get(tipo): só nome simples, e o arquivo dentro da raiz dos schemas ───

@pytest.fixture
def offline(monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_SCHEMAS_DIR", raising=False)
    monkeypatch.delenv("NOVOMODELO_MCP_DOCS_DIR", raising=False)
    return dataclasses.replace(load_settings(), solver_bin="/nao/existe/novomodelo")


@pytest.mark.parametrize("tipo", ["D:segredo", "a.b", "../x", "", "config "])
def test_tipo_de_schema_que_nao_e_nome_simples_e_recusado(offline, tmp_path, tipo):
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    for nome in ("D:segredo", "a.b", "config "):
        (schemas / f"{nome}.schema.json").write_text('{"conteudo_de_fora": true}')
    (tmp_path / "x.schema.json").write_text('{"conteudo_de_fora": true}')
    r = REF.read_schema(dataclasses.replace(offline, schemas_dir=str(schemas)), tipo)
    assert r["status"] == "error" and "conteudo_de_fora" not in json.dumps(r)


def test_schema_real_continua_lido(offline):
    r = REF.read_schema(offline, "config")
    assert r["status"] == "ok" and r["schema"]["type"] == "object"


# ── docs_read(page): fora da raiz, exista ou não, a resposta é a mesma ─────────

def test_fora_da_raiz_das_docs_nao_revela_se_o_arquivo_existe(offline, tmp_path):
    existe = tmp_path / "existe.md"
    existe.write_text("# segredo")
    a = REF.read_doc(offline, str(existe), 100)
    b = REF.read_doc(offline, str(tmp_path / "nao-existe.md"), 100)
    assert a["status"] == b["status"] == "error"
    assert a["diagnostics"] == [d.replace("nao-existe", "existe") for d in b["diagnostics"]]
    assert "segredo" not in json.dumps(a)


def test_pagina_real_das_docs_continua_lida(offline):
    r = REF.read_doc(offline, "reference/cli-reference", 200)
    assert r["status"] == "ok" and r["content"]
