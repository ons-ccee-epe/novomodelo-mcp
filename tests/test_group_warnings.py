"""Avisos repetidos do `case_validate` viram grupos com contagem; nenhum some da conta."""

import dataclasses

import novomodelo_mcp.tools.pre_run as pre_run
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.shaping import group_diagnostics


def _repetidos():
    hidro = [
        {
            "kind": "hydro",
            "message": f"usina {i} sem curva de 'jusante_{i}'",
            "file": "system/hydros.json",
            "entity": f"hydro {i}",
        }
        for i in range(490)
    ]
    outro = [
        {
            "kind": "stage",
            "message": f"estágio {i} com duração 0.5 h",
            "file": "stages.json",
            "entity": f"stage {i}",
        }
        for i in range(6)
    ]
    return hidro + outro


def test_mensagens_que_so_diferem_nos_numeros_formam_um_grupo():
    out = group_diagnostics(_repetidos(), max_groups=50)
    assert [(g["kind"], g["count"]) for g in out["grupos"]] == [("hydro", 490), ("stage", 6)]
    assert out["total"] == 496 and out["grupos_total"] == 2
    assert out["grupos_truncados"] is False
    hidro = out["grupos"][0]
    assert hidro["mensagem_modelo"] == "usina … sem curva de …"
    assert len(hidro["exemplos"]) == 3
    assert hidro["exemplos"][0]["entity"] == "hydro 0"


def test_mesmo_texto_com_kind_diferente_fica_em_grupos_separados():
    items = [{"kind": "a", "message": "x 1"}, {"kind": "b", "message": "x 2"}]
    assert group_diagnostics(items, max_groups=10)["grupos_total"] == 2


def test_teto_de_grupos_preserva_a_contagem():
    items = [{"kind": f"k{i}", "message": "m"} for i in range(7)] + ["texto solto 3"] * 5
    out = group_diagnostics(items, max_groups=3)
    assert len(out["grupos"]) == 3
    assert out["grupos_truncados"] is True and out["grupos_total"] == 8
    assert out["grupos"][0]["count"] == 5
    assert out["grupos"][0]["mensagem_modelo"] == "texto solto …"
    assert out["total"] == len(items)


def test_soma_das_contagens_e_o_total():
    out = group_diagnostics(_repetidos(), max_groups=1000)
    assert sum(g["count"] for g in out["grupos"]) == out["total"] == 496


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def test_case_validate_agrupa_avisos_e_mantem_erros_um_a_um(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    settings = dataclasses.replace(load_settings(), max_diagnostics=50)
    erros = [{"kind": "hydro", "message": f"erro {i}"} for i in range(60)]
    monkeypatch.setattr(
        pre_run,
        "validate_deck_binding",
        lambda case, settings, output_dir=None: {
            "status": "error",
            "exit_code": 1,
            "diagnostics": [],
            "valid": False,
            "errors": erros,
            "warnings": _repetidos(),
        },
    )
    mcp = _CaptureMCP()
    pre_run.register_pre_run(mcp, settings)
    env = mcp.tools["case_validate"](str(tmp_path))
    assert env["warnings_agrupados"] is True
    assert env["warnings_total"] == 496 and env["warnings_grupos_total"] == 2
    assert [g["count"] for g in env["warnings"]] == [490, 6]
    assert len(env["errors"]) == 50 and env["errors_total"] == 60
    assert env["errors_truncated"] is True
