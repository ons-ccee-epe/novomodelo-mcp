"""O primeiro uso não paga trabalho evitável: boot sem processo nem rede, e o
`server_info` sem lançar o bridge só para saber a versão."""

import subprocess
import urllib.error
from importlib import metadata

import pytest

import novomodelo_mcp.server as S
from novomodelo_mcp.adapters import discovery, versions
from novomodelo_mcp.names import BRIDGE_CLI


@pytest.fixture
def sem_processo_nem_rede(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError(f"trabalho no boot: {a[:1]}")

    monkeypatch.setattr(subprocess, "Popen", proibido)
    monkeypatch.setattr(versions, "fetch_bytes", proibido)


def test_build_server_nao_lanca_processo_nem_usa_rede(sem_processo_nem_rede):
    nomes = {t.name for t in S.build_server()._tool_manager.list_tools()}
    assert "server_info" in nomes


def test_server_info_nao_lanca_o_bridge_do_pacote(monkeypatch, tmp_path):
    bridge = str(tmp_path / BRIDGE_CLI)
    monkeypatch.setattr(S, "bridge_origin", lambda settings: (bridge, "pacote"))
    monkeypatch.setattr(versions, "update_check", lambda settings: {})
    lancados = []
    real = discovery.subprocess.run
    monkeypatch.setattr(
        discovery.subprocess,
        "run",
        lambda cmd, *a, **k: (lancados.append(cmd[0]), real(cmd, *a, **k))[1],
    )
    tools = {t.name: t.fn for t in S.build_server()._tool_manager.list_tools()}
    info = tools["server_info"]()
    assert bridge not in lancados
    assert info["bridge"]["version"] == f"{BRIDGE_CLI} {metadata.version(BRIDGE_CLI)}"


def test_primeira_tool_sem_rede_responde(monkeypatch):
    def sem_dns(*a, **k):
        raise urllib.error.URLError("sem DNS")

    monkeypatch.setattr(versions, "_open", sem_dns)
    versions._UPDATE.clear()
    tools = {t.name: t.fn for t in S.build_server()._tool_manager.list_tools()}
    assert tools["docs_list"]()["status"] == "ok"
    assert "new_version" in tools["server_info"]()
