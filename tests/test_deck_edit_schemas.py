"""`deck_edit_json` valida com a mesma cascata de schemas do `run_apply`.

Sem `NOVOMODELO_MCP_SCHEMAS_DIR` e sem o executável, a cascata cai nos schemas
embutidos; a edição que viola o schema de `config.json` precisa ser recusada.
"""

import dataclasses
import json

from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.deck import register_deck

CONFIG = {
    "training": {
        "selection": {"method": "sampled", "forward_passes": 4},
        "stopping_rules": [{"type": "iteration_limit", "limit": 50}],
    }
}


class _CaptureMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _deck_edit_json(tmp_path, monkeypatch):
    for var in ("SCHEMAS_DIR", "WORKSPACE", "SOLVER_BIN"):
        monkeypatch.delenv(f"NOVOMODELO_MCP_{var}", raising=False)
    settings = dataclasses.replace(
        load_settings(), solver_bin=str(tmp_path / "novomodelo-inexistente")
    )
    mcp = _CaptureMCP()
    register_deck(mcp, settings)
    return mcp.tools["deck_edit_json"]


def _write_config(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(CONFIG), encoding="utf-8")
    return cfg


def test_valor_fora_do_schema_e_recusado_sem_variavel_de_schemas(tmp_path, monkeypatch):
    edit = _deck_edit_json(tmp_path, monkeypatch)
    cfg = _write_config(tmp_path)
    before = cfg.read_text(encoding="utf-8")
    out = edit(str(cfg), [{"path": "training.selection.forward_passes", "value": "abc"}])
    assert out["status"] == "error"
    assert cfg.read_text(encoding="utf-8") == before
    assert not (tmp_path / "config.json.bak").exists()


def test_valor_valido_grava_com_backup(tmp_path, monkeypatch):
    edit = _deck_edit_json(tmp_path, monkeypatch)
    cfg = _write_config(tmp_path)
    out = edit(str(cfg), [{"path": "training.selection.forward_passes", "value": 8}])
    assert out["status"] == "ok" and out["written"] is True
    assert (
        json.loads(cfg.read_text(encoding="utf-8"))["training"]["selection"]["forward_passes"] == 8
    )
    assert (tmp_path / "config.json.bak").exists()
