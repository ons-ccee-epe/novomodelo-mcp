"""Cancelar um run derruba a árvore inteira do comando, não só o filho direto: um solver
lançado por script deixaria o neto gravando no `output/` depois do `cancelled`."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from novomodelo_mcp.adapters import _job_runner

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="árvore POSIX; o Windows usa taskkill /T")


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and " Z " in stat.read_text(encoding="ascii"))


def test_cancel_derruba_o_neto(tmp_path):
    neto = tmp_path / "neto.pid"
    cmd = ["sh", "-c", f"sleep 300 & echo $! > '{neto}'; wait"]
    runner = subprocess.Popen([sys.executable, _job_runner.__file__, str(tmp_path), *cmd],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    prazo = time.time() + 10
    while not (neto.exists() and neto.read_text().strip()) and time.time() < prazo:
        time.sleep(0.05)
    pid_neto = int(neto.read_text())
    (tmp_path / "cancel").touch()
    runner.wait(timeout=_job_runner.GRACE_S + 3 * _job_runner.HEARTBEAT_S + 5)
    time.sleep(0.2)
    try:
        assert not _vivo(pid_neto)
    finally:
        if _vivo(pid_neto):
            os.kill(pid_neto, 9)
