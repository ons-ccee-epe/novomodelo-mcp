#!/usr/bin/env python3
"""Smoke test do guard de workspace (stdlib puro). Roda: python3 tests/smoke_paths.py"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novomodelo_mcp.config import load_settings              # noqa: E402
from novomodelo_mcp.adapters.paths import ensure_in_workspace  # noqa: E402


def test_unrestricted():
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)
    assert ensure_in_workspace("/etc/passwd", settings=load_settings()) is None


def test_within_root():
    with tempfile.TemporaryDirectory() as d:
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = d
        inside = str(Path(d) / "deck" / "config.json")
        assert ensure_in_workspace(inside, settings=load_settings()) is None
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


def test_outside_root_blocked():
    with tempfile.TemporaryDirectory() as d:
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = d
        err = ensure_in_workspace("/etc/passwd", settings=load_settings())
        assert err is not None and err["status"] == "error", err
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


def test_traversal_blocked():
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d) / "ws"
        ws.mkdir()
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = str(ws)
        escape = str(ws / ".." / "secret.txt")
        err = ensure_in_workspace(escape, settings=load_settings())
        assert err is not None and err["status"] == "error", err
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


_VARS = ("NOVOMODELO_MCP_WORKSPACE", "NOVOMODELO_MCP_STATE_DIR", "USERPROFILE", "HOME")


class _Ambiente:
    """Workspace, state dir e HOME temporários; restaura o ambiente na saída."""

    def __init__(self, roots, base):
        self.vals = {"NOVOMODELO_MCP_WORKSPACE": os.pathsep.join(str(r) for r in roots),
                     "NOVOMODELO_MCP_STATE_DIR": str(Path(base) / "state"),
                     "USERPROFILE": str(Path(base) / "casa"), "HOME": str(Path(base) / "casa")}

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in _VARS}
        os.environ.update(self.vals)
        (Path(self.vals["HOME"]) / ".ssh").mkdir(parents=True, exist_ok=True)
        return load_settings()

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_refusal_tells_agent_not_to_bypass_and_suggests_the_folder():
    from novomodelo_mcp.adapters.paths import NAO_CONTORNE
    with tempfile.TemporaryDirectory() as d:
        ws, fora = Path(d) / "ws", Path(d) / "Meus Estudos"
        ws.mkdir()
        fora.mkdir()
        with _Ambiente([ws], d) as st:
            err = ensure_in_workspace(str(fora), settings=st)
        assert err["status"] == "error" and err["exit_code"] == 13, err
        assert NAO_CONTORNE in err["diagnostics"], err
        assert err["pasta_sugerida"] == str(fora.resolve()), err
        assert "configurar" not in " ".join(err["diagnostics"]), err


def test_refusal_of_a_file_suggests_its_folder():
    with tempfile.TemporaryDirectory() as d:
        ws, fora = Path(d) / "ws", Path(d) / "fora"
        ws.mkdir()
        fora.mkdir()
        (fora / "config.json").write_text("{}", encoding="utf-8")
        with _Ambiente([ws], d) as st:
            err = ensure_in_workspace(str(fora / "config.json"), settings=st)
        assert err["pasta_sugerida"] == str(fora.resolve()), err


def test_refusal_suggests_the_resolved_folder_not_the_dotdot_text():
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d) / "ws"
        ws.mkdir()
        with _Ambiente([ws], d) as st:
            err = ensure_in_workspace(str(ws / ".." / "ws2"), settings=st)
        assert ".." not in err["pasta_sugerida"], err


def test_included_folders_are_accepted_at_once_and_others_still_refused():
    from novomodelo_mcp.adapters.paths import include_folders
    with tempfile.TemporaryDirectory() as d:
        ws, a, b, c = (Path(d) / n for n in ("ws", "a", "b", "c"))
        for p in (ws, a, b, c):
            p.mkdir()
        with _Ambiente([ws], d) as st:
            assert ensure_in_workspace(str(a), settings=st)["exit_code"] == 13
            out = include_folders([str(a), str(b)], settings=st)
            assert out["status"] == "ok" and out["incluidas"] == [str(a.resolve()), str(b.resolve())], out
            assert ensure_in_workspace(str(a / "caso"), str(b), settings=st) is None
            assert ensure_in_workspace(str(ws), settings=st) is None
            assert ensure_in_workspace(str(c), settings=st)["exit_code"] == 13
            again = include_folders([str(a)], settings=st)
            assert again["ja_incluidas"] == [str(a.resolve())] and again["incluidas"] == [], again


def test_include_refuses_home_root_config_and_missing_folders():
    from novomodelo_mcp.adapters.paths import include_folders
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d) / "ws"
        ws.mkdir()
        with _Ambiente([ws], d) as st:
            casa = Path(os.environ["HOME"])
            perigosas = [str(casa), str(casa / ".ssh"), str(Path(d)), Path(d).anchor,
                         str(Path(d) / "nao-existe"), str(Path(d) / "state")]
            out = include_folders(perigosas, settings=st)
            assert out["status"] == "error" and out["exit_code"] == 22, out
            assert len(out["recusadas"]) == len(perigosas), out
            assert ensure_in_workspace(str(casa / ".ssh"), settings=st)["exit_code"] == 13


def test_unreadable_included_file_grants_nothing():
    with tempfile.TemporaryDirectory() as d:
        ws, fora = Path(d) / "ws", Path(d) / "fora"
        ws.mkdir()
        fora.mkdir()
        (Path(d) / "state").mkdir()
        (Path(d) / "state" / "pastas.json").write_text("{ quebrado", encoding="utf-8")
        with _Ambiente([ws], d) as st:
            assert ensure_in_workspace(str(fora), settings=st)["exit_code"] == 13

def test_results_query_entity_traversal_blocked():
    from novomodelo_mcp.adapters.results import simulation_query
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d) / "ws"
        (ws / "output" / "simulation").mkdir(parents=True)
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = str(ws)
        err = simulation_query(str(ws / "output"), "../x", settings=load_settings())
        assert err["status"] == "error" and err["exit_code"] == 13, err
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


def test_find_case_dir_stops_at_workspace_root():
    from novomodelo_mcp.adapters.deck_io import find_case_dir
    from novomodelo_mcp.adapters.paths import allowed_roots
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "config.json").write_text("{}", encoding="utf-8")
        ws = Path(d) / "ws"
        ws.mkdir()
        (ws / "x.json").write_text("{}", encoding="utf-8")
        os.environ["NOVOMODELO_MCP_WORKSPACE"] = str(ws)
        roots = allowed_roots(load_settings())
        assert find_case_dir(str(ws / "x.json"), stop_at=roots) is None
    os.environ.pop("NOVOMODELO_MCP_WORKSPACE", None)


def test_schema_tipo_must_be_a_plain_name():
    from novomodelo_mcp.adapters.reference import read_schema
    for tipo in ("D:segredo", "../config", "a.b"):
        assert read_schema(load_settings(), tipo)["status"] == "error", tipo


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passaram")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
