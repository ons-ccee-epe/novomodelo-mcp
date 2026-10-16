"""`case_validate(output_dir)` chega à biblioteca (`output_dir=`) e ao CLI de reserva (`--output`)."""
import dataclasses
import sys
import types

import novomodelo_mcp.adapters.novomodelo as adapter
import novomodelo_mcp.tools.pre_run as pre_run
from novomodelo_mcp.config import load_settings


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


def _fake_library(monkeypatch):
    calls = []

    def validate(path, config_overrides=None, **kwargs):
        calls.append({"path": path, "config_overrides": config_overrides, **kwargs})
        return {"valid": True, "errors": [], "warnings": []}

    io = types.ModuleType("novomodelo.io")
    io.validate = validate
    pkg = types.ModuleType("novomodelo")
    pkg.io = io
    monkeypatch.setitem(sys.modules, "novomodelo", pkg)
    monkeypatch.setitem(sys.modules, "novomodelo.io", io)
    return calls


def test_biblioteca_recebe_output_dir_so_quando_informado(tmp_path, monkeypatch):
    calls = _fake_library(monkeypatch)
    adapter.validate_deck_binding(str(tmp_path), output_dir=str(tmp_path / "out"))
    adapter.validate_deck_binding(str(tmp_path))
    assert calls[0]["output_dir"] == str(tmp_path / "out")
    assert "output_dir" not in calls[1]
    assert all(c["config_overrides"] is None for c in calls)


def test_cli_de_reserva_recebe_output_so_quando_informado(tmp_path, monkeypatch):
    argvs = []

    class _Proc:
        returncode, stdout, stderr = 0, "0 errors, 0 warnings", ""

    monkeypatch.setattr(adapter.subprocess, "run",
                        lambda cmd, **kw: argvs.append(cmd) or _Proc())
    settings = dataclasses.replace(load_settings(), solver_bin="/bin/novomodelo-falso")
    adapter.validate_deck_cli(str(tmp_path), output_dir="/saida", settings=settings)
    adapter.validate_deck_cli(str(tmp_path), settings=settings)
    assert argvs[0][-3:] == [str(tmp_path), "--output", "/saida"]
    assert "--output" not in argvs[1]


def _case_validate(tmp_path, monkeypatch, workspace=None):
    calls = []
    monkeypatch.setattr(pre_run, "validate_deck_binding",
                        lambda case, *, output_dir=None, settings=None:
                        calls.append(output_dir) or {"status": "ok", "valid": True})
    settings = dataclasses.replace(load_settings(), workspace=workspace)
    mcp = _CaptureMCP()
    pre_run.register_pre_run(mcp, settings)
    return mcp.tools["case_validate"], calls


def test_tool_repassa_output_dir(tmp_path, monkeypatch):
    case_validate, calls = _case_validate(tmp_path, monkeypatch, workspace=str(tmp_path))
    env = case_validate(str(tmp_path), output_dir=str(tmp_path / "output"))
    assert env["status"] == "ok" and calls == [str(tmp_path / "output")]


def test_output_dir_fora_do_workspace_e_recusado_sem_validar(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    case_validate, calls = _case_validate(tmp_path, monkeypatch, workspace=str(ws))
    env = case_validate(str(ws), output_dir=str(tmp_path / "fora"))
    assert env["status"] == "error" and calls == []
