"""`bridge_dashboard(output)`: o arquivo HTML vai em `--output` e volta em `artifacts.dashboard`."""

import dataclasses
from pathlib import Path

import novomodelo_mcp.tools.post_run as post_run
from novomodelo_mcp.config import load_settings


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _dashboard(monkeypatch, workspace=None):
    argvs = []
    monkeypatch.setattr(
        post_run,
        "run_bridge",
        lambda argv, **kw: (
            argvs.append(argv) or {"status": "ok", "exit_code": 0, "diagnostics": []}
        ),
    )
    mcp = _CaptureMCP()
    post_run.register_post_run(mcp, dataclasses.replace(load_settings(), workspace=workspace))
    return mcp.tools["bridge_dashboard"], argvs


def test_output_vai_para_o_bridge_e_volta_no_artefato(tmp_path, monkeypatch):
    dashboard, argvs = _dashboard(monkeypatch, workspace=str(tmp_path))
    out = str(tmp_path / "d1.html")
    env = dashboard(str(tmp_path), output=out)
    assert argvs[-1][-2:] == ["--output", out]
    assert env["artifacts"]["dashboard"] == out


def test_sem_output_o_artefato_e_o_padrao_do_bridge(tmp_path, monkeypatch):
    dashboard, argvs = _dashboard(monkeypatch, workspace=str(tmp_path))
    env = dashboard(str(tmp_path))
    assert "--output" not in argvs[-1]
    assert env["artifacts"]["dashboard"] == str(Path(tmp_path) / "dashboard.html")


def test_output_fora_do_workspace_e_recusado_sem_subprocesso(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    dashboard, argvs = _dashboard(monkeypatch, workspace=str(ws))
    env = dashboard(str(ws), output=str(tmp_path / "fora.html"))
    assert env["status"] == "error" and argvs == []
