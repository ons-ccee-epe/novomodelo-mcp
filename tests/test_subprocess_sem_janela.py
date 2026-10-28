"""Nenhum subprocesso do servidor abre janela de console no Windows.

Sob um cliente MCP gráfico o servidor não tem console; um CLI de console lançado sem
`CREATE_NO_WINDOW` abre uma janela a cada chamada de tool.
"""

import ast
import subprocess
import sys
from pathlib import Path

from novomodelo_mcp.adapters import bridge
from novomodelo_mcp.adapters.subproc import NO_WINDOW

SRC = Path(__file__).resolve().parents[1] / "src" / "novomodelo_mcp"
_KWARGS_SEM_JANELA = {"NO_WINDOW", "_spawn_kwargs"}


def _e_chamada_de_subprocesso(node: ast.Call) -> bool:
    f = node.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr in ("run", "Popen")
        and isinstance(f.value, ast.Name)
        and f.value.id == "subprocess"
    )


def _passa_sem_janela(node: ast.Call) -> bool:
    for kw in node.keywords:
        if kw.arg == "creationflags":
            return True
        if kw.arg is None:
            alvo = kw.value.func if isinstance(kw.value, ast.Call) else kw.value
            if isinstance(alvo, ast.Name) and alvo.id in _KWARGS_SEM_JANELA:
                return True
    return False


def test_toda_chamada_de_subprocesso_em_src_passa_a_flag_sem_janela():
    faltando = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and _e_chamada_de_subprocesso(node)
                and not _passa_sem_janela(node)
            ):
                faltando.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not faltando, f"subprocesso sem CREATE_NO_WINDOW: {faltando}"


def test_no_window_so_tem_a_flag_no_windows():
    if sys.platform == "win32":
        assert NO_WINDOW == {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        assert NO_WINDOW == {}


def test_run_bridge_lanca_o_cli_sem_janela(monkeypatch, tmp_path):
    visto = {}

    def run_falso(cmd, **kwargs):
        visto.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"status": "ok"}', stderr="")

    monkeypatch.setattr(bridge, "find_bridge", lambda settings: str(tmp_path / "bridge"))
    monkeypatch.setattr(bridge.subprocess, "run", run_falso)
    bridge.run_bridge(["check", "x"])
    assert NO_WINDOW.items() <= visto.items()
