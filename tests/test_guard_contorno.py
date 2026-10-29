"""Toda tool que recebe caminho diz ao agente para não contornar a pasta de trabalho."""

import inspect

from novomodelo_mcp.adapters.paths import AVISO_NA_TOOL, NAO_CONTORNE, PATH_PARAMS
from novomodelo_mcp.server import SERVER_INSTRUCTIONS, build_server


def _tools():
    return {t.name: t for t in build_server()._tool_manager.list_tools()}


def test_instructions_proibem_o_contorno():
    assert NAO_CONTORNE in SERVER_INSTRUCTIONS


def test_toda_tool_com_parametro_de_caminho_traz_o_aviso():
    tools = _tools()
    com_caminho = {
        n for n, t in tools.items() if set(inspect.signature(t.fn).parameters) & PATH_PARAMS
    }
    assert {
        "deck_read_json",
        "bridge_convert_newave",
        "bridge_convert_decomp",
        "bridge_compare_newave",
        "bridge_compare_decomp",
        "run_start",
    } <= com_caminho
    sem_aviso = sorted(
        n for n in com_caminho | {"deck_sql"} if AVISO_NA_TOOL not in tools[n].description
    )
    assert sem_aviso == []


def test_tool_sem_caminho_nao_leva_o_aviso():
    tools = _tools()
    assert AVISO_NA_TOOL not in tools["docs_search"].description
    assert AVISO_NA_TOOL not in tools["instalar_novomodelo"].description


def test_incluir_pastas_sempre_pede_aprovacao():
    from novomodelo_mcp import client_config as C

    tool = _tools()["incluir_pastas"]
    assert tool.annotations.readOnlyHint is False
    assert "incluir_pastas" not in C.read_only_tools()


def test_incluir_pastas_pelo_servidor_vale_na_hora(tmp_path, monkeypatch):
    ws, estudos, outra = tmp_path / "ws", tmp_path / "estudos", tmp_path / "outra"
    for p in (ws, estudos, outra):
        p.mkdir()
    monkeypatch.setenv("NOVOMODELO_MCP_WORKSPACE", str(ws))
    monkeypatch.setenv("NOVOMODELO_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "casa"))
    monkeypatch.setenv("HOME", str(tmp_path / "casa"))
    tools = _tools()
    assert tools["deck_list"].fn(case_dir=str(estudos))["suggested_folder"] == str(
        estudos.resolve()
    )
    out = tools["incluir_pastas"].fn(pastas=[str(estudos), str(outra)])
    assert out["included"] == [str(estudos.resolve()), str(outra.resolve())]
    assert tools["deck_list"].fn(case_dir=str(estudos))["status"] == "ok"
    assert str(estudos.resolve()) in tools["server_info"].fn()["included_folders"]
