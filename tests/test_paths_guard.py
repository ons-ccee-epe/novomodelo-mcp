"""Guard de workspace: o caminho dentro é aceito e o de fora é recusado."""

import os
from pathlib import Path

from novomodelo_mcp.adapters.paths import ensure_in_workspace
from novomodelo_mcp.config import load_settings


def test_unrestricted(monkeypatch):
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    assert ensure_in_workspace("/etc/passwd", settings=load_settings()) is None


def test_within_root(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVOMODELO_MCP_WORKSPACE", str(tmp_path))
    inside = str(tmp_path / "deck" / "config.json")
    assert ensure_in_workspace(inside, settings=load_settings()) is None


def test_outside_root_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVOMODELO_MCP_WORKSPACE", str(tmp_path))
    err = ensure_in_workspace("/etc/passwd", settings=load_settings())
    assert err is not None and err["status"] == "error", err


def test_traversal_blocked(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("NOVOMODELO_MCP_WORKSPACE", str(ws))
    escape = str(ws / ".." / "secret.txt")
    err = ensure_in_workspace(escape, settings=load_settings())
    assert err is not None and err["status"] == "error", err


def _ambiente(monkeypatch, roots, base: Path):
    """Workspace, state dir e HOME temporários."""
    casa = base / "casa"
    monkeypatch.setenv("NOVOMODELO_MCP_WORKSPACE", os.pathsep.join(str(r) for r in roots))
    monkeypatch.setenv("NOVOMODELO_MCP_STATE_DIR", str(base / "state"))
    monkeypatch.setenv("USERPROFILE", str(casa))
    monkeypatch.setenv("HOME", str(casa))
    (casa / ".ssh").mkdir(parents=True, exist_ok=True)
    return load_settings()


def test_refusal_tells_agent_not_to_bypass_and_suggests_the_folder(tmp_path, monkeypatch):
    from novomodelo_mcp.adapters.paths import NAO_CONTORNE

    ws, fora = tmp_path / "ws", tmp_path / "Meus Estudos"
    ws.mkdir()
    fora.mkdir()
    st = _ambiente(monkeypatch, [ws], tmp_path)
    err = ensure_in_workspace(str(fora), settings=st)
    assert err["status"] == "error" and err["exit_code"] == 13, err
    assert NAO_CONTORNE in err["diagnostics"], err
    assert err["suggested_folder"] == str(fora.resolve()), err
    assert "configurar" not in " ".join(err["diagnostics"]), err


def test_refusal_of_a_file_suggests_its_folder(tmp_path, monkeypatch):
    ws, fora = tmp_path / "ws", tmp_path / "fora"
    ws.mkdir()
    fora.mkdir()
    (fora / "config.json").write_text("{}", encoding="utf-8")
    st = _ambiente(monkeypatch, [ws], tmp_path)
    err = ensure_in_workspace(str(fora / "config.json"), settings=st)
    assert err["suggested_folder"] == str(fora.resolve()), err


def test_refusal_suggests_the_resolved_folder_not_the_dotdot_text(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    st = _ambiente(monkeypatch, [ws], tmp_path)
    err = ensure_in_workspace(str(ws / ".." / "ws2"), settings=st)
    assert ".." not in err["suggested_folder"], err


def test_included_folders_are_accepted_at_once_and_others_still_refused(tmp_path, monkeypatch):
    from novomodelo_mcp.adapters.paths import include_folders

    ws, a, b, c = (tmp_path / n for n in ("ws", "a", "b", "c"))
    for p in (ws, a, b, c):
        p.mkdir()
    st = _ambiente(monkeypatch, [ws], tmp_path)
    assert ensure_in_workspace(str(a), settings=st)["exit_code"] == 13
    out = include_folders([str(a), str(b)], settings=st)
    assert out["status"] == "ok" and out["included"] == [
        str(a.resolve()),
        str(b.resolve()),
    ], out
    assert ensure_in_workspace(str(a / "caso"), str(b), settings=st) is None
    assert ensure_in_workspace(str(ws), settings=st) is None
    assert ensure_in_workspace(str(c), settings=st)["exit_code"] == 13
    again = include_folders([str(a)], settings=st)
    assert again["already_included"] == [str(a.resolve())] and again["included"] == [], again


def test_include_refuses_home_root_config_and_missing_folders(tmp_path, monkeypatch):
    from novomodelo_mcp.adapters.paths import include_folders

    ws = tmp_path / "ws"
    ws.mkdir()
    st = _ambiente(monkeypatch, [ws], tmp_path)
    casa = Path(os.environ["HOME"])
    perigosas = [
        str(casa),
        str(casa / ".ssh"),
        str(tmp_path),
        tmp_path.anchor,
        str(tmp_path / "nao-existe"),
        str(tmp_path / "state"),
    ]
    out = include_folders(perigosas, settings=st)
    assert out["status"] == "error" and out["exit_code"] == 22, out
    assert len(out["refused"]) == len(perigosas), out
    assert ensure_in_workspace(str(casa / ".ssh"), settings=st)["exit_code"] == 13


def test_unreadable_included_file_grants_nothing(tmp_path, monkeypatch):
    ws, fora = tmp_path / "ws", tmp_path / "fora"
    ws.mkdir()
    fora.mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "pastas.json").write_text("{ quebrado", encoding="utf-8")
    st = _ambiente(monkeypatch, [ws], tmp_path)
    assert ensure_in_workspace(str(fora), settings=st)["exit_code"] == 13


def test_results_query_entity_traversal_blocked(tmp_path, monkeypatch):
    from novomodelo_mcp.adapters.results import simulation_query

    ws = tmp_path / "ws"
    (ws / "output" / "simulation").mkdir(parents=True)
    monkeypatch.setenv("NOVOMODELO_MCP_WORKSPACE", str(ws))
    err = simulation_query(str(ws / "output"), "../x", settings=load_settings())
    assert err["status"] == "error" and err["exit_code"] == 13, err


def test_find_case_dir_stops_at_workspace_root(tmp_path, monkeypatch):
    from novomodelo_mcp.adapters.deck_io import find_case_dir
    from novomodelo_mcp.adapters.paths import allowed_roots

    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "x.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("NOVOMODELO_MCP_WORKSPACE", str(ws))
    roots = allowed_roots(load_settings())
    assert find_case_dir(str(ws / "x.json"), stop_at=roots) is None


def test_schema_tipo_must_be_a_plain_name():
    from novomodelo_mcp.adapters.reference import read_schema

    for tipo in ("D:segredo", "../config", "a.b"):
        assert read_schema(load_settings(), tipo)["status"] == "error", tipo
