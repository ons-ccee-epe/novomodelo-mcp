"""`run_apply` checa só o tipo dos knobs; a faixa de valores é do schema."""
import dataclasses
import json

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.run import register_run

CONFIG = {"training": {"selection": {"method": "sampled", "forward_passes": 4},
                       "stopping_rules": [{"type": "iteration_limit", "limit": 50}]}}


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


def _run_apply(tmp_path, monkeypatch):
    for var in ("SCHEMAS_DIR", "WORKSPACE", "SOLVER_BIN", "STATE_DIR"):
        monkeypatch.delenv(f"NOVOMODELO_MCP_{var}", raising=False)
    settings = dataclasses.replace(load_settings(),
                                   solver_bin=str(tmp_path / "novomodelo-inexistente"),
                                   state_dir=str(tmp_path / "state"))
    mcp = _CaptureMCP()
    register_run(mcp, settings)
    (tmp_path / "config.json").write_text(json.dumps(CONFIG))
    return mcp.tools["run_apply"]


def test_texto_no_lugar_de_inteiro_e_recusado_pelo_tipo(tmp_path, monkeypatch):
    out = _run_apply(tmp_path, monkeypatch)(str(tmp_path), {"forward_passes": "3"})
    assert out["status"] == "error" and out["exit_code"] == 22
    assert "deve ser inteiro" in " ".join(out["diagnostics"])


def test_negativo_e_recusado_pelo_schema_e_nao_pelo_mcp(tmp_path, monkeypatch):
    out = _run_apply(tmp_path, monkeypatch)(str(tmp_path), {"forward_passes": -5},
                                            dry_run=True)
    assert out["status"] == "error" and out["written"] is False
    assert out["schema_errors"] and "forward_passes" in out["schema_errors"][0]
    assert "deve ser inteiro" not in json.dumps(out, ensure_ascii=False)


def test_inteiro_valido_continua_gravando(tmp_path, monkeypatch):
    out = _run_apply(tmp_path, monkeypatch)(str(tmp_path), {"forward_passes": 2})
    assert out["status"] == "ok" and out["written"] is True
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["training"]["selection"]["forward_passes"] == 2
