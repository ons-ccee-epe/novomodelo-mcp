"""As tabelas dos diagnósticos do bridge (uma linha por usina ou registro) cabem em
NOVOMODELO_MCP_MAX_RESPONSE_KB: a maior tabela perde linhas primeiro, e todo diagnóstico
continua na resposta, nas tools dos dois trilhos."""

import copy
import dataclasses

import pytest

import novomodelo_mcp.tools.post_run as POST
import novomodelo_mcp.tools.pre_run as PRE
from novomodelo_mcp.adapters import budget
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.shaping import response_bytes


def _s(kb=10, **kw):
    return dataclasses.replace(load_settings(), max_response_kb=kb, **kw)


def _diag(code, n_rows):
    table = None
    if n_rows is not None:
        table = {
            "columns": ["usina", "valor", "nota"],
            "rows": [[f"usina {i}", i * 1.5, "fora da faixa"] for i in range(n_rows)],
            "justify": None,
            "caption": None,
        }
    return {
        "code": code,
        "severity": "warning",
        "category": "input",
        "title": code,
        "summary": "registros fora da faixa",
        "table": table,
        "notes": [],
        "remediation": "confira o deck",
    }


def _envelope(*diags):
    return {
        "schema_version": "2",
        "command": "check newave",
        "status": "warning",
        "summary": {},
        "diagnostics": list(diags),
        "exit_code": 1,
    }


def test_a_maior_tabela_encolhe_e_todo_diagnostico_fica():
    env = _envelope(_diag("grande", 2000), _diag("pequena", 5), _diag("sem-tabela", None))
    original = copy.deepcopy(env)
    out = budget.shrink_tables_to_budget(env, _s())
    assert response_bytes(out) <= 10 * 1024
    assert [d["code"] for d in out["diagnostics"]] == ["grande", "pequena", "sem-tabela"]
    grande = out["diagnostics"][0]["table"]
    assert grande["truncated"] is True and grande["rows_total"] == 2000
    assert 0 < len(grande["rows"]) < 2000
    assert grande["rows"] == original["diagnostics"][0]["table"]["rows"][: len(grande["rows"])]
    assert out["diagnostics"][1]["table"] == original["diagnostics"][1]["table"]
    assert out["size_truncation"] == {"limit_kb": 10}
    assert env == original


def test_resposta_que_cabe_fica_igual():
    env = _envelope(_diag("pequena", 5))
    out = budget.shrink_tables_to_budget(copy.deepcopy(env), _s())
    assert out == env


def test_sem_tabela_que_baste_corta_a_lista_de_diagnosticos():
    diags = [{**_diag(f"d{i}", None), "notes": ["x" * 200]} for i in range(200)]
    out = budget.shrink_tables_to_budget(_envelope(*diags), _s())
    assert response_bytes(out) <= 10 * 1024
    assert 0 < len(out["diagnostics"]) < 200 and out["truncated"] is True


class _Cap:
    def __init__(self):
        self.tools = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("bridge_check_newave", {"src": "nw"}),
        ("bridge_convert_newave", {"src": "nw", "dst": "deck"}),
        ("bridge_check_decomp", {"src": "dc"}),
        ("bridge_convert_decomp", {"src": "dc", "dst": "deck"}),
        ("bridge_compare_newave", {"newave_dir": "nw", "output_dir": "out"}),
        ("bridge_compare_decomp", {"decomp_dir": "dc", "output_dir": "out"}),
        ("bridge_dashboard", {"case_dir": "deck"}),
    ],
)
def test_toda_tool_do_bridge_cabe_no_teto(tmp_path, monkeypatch, tool, args):
    env = _envelope(_diag("grande", 2000), _diag("pequena", 5))
    for mod in (PRE, POST):
        monkeypatch.setattr(mod, "run_bridge", lambda argv, settings: copy.deepcopy(env))
    settings = _s(workspace=str(tmp_path))
    cap = _Cap()
    PRE.register_pre_run(cap, settings)
    POST.register_post_run(cap, settings)
    out = cap.tools[tool](**{k: str(tmp_path / v) for k, v in args.items()})
    assert response_bytes(out) <= 10 * 1024
    assert out["diagnostics"][0]["table"]["truncated"] is True
    assert out["diagnostics"][1]["table"] == env["diagnostics"][1]["table"]
