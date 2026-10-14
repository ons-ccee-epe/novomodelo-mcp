"""O script que o workflow de release usa confere a versão anunciada pelo MCP instalado.

Sobe o servidor deste checkout por stdio (sem `--server-info`, que usaria a rede).
"""
import os
import subprocess
import sys
from pathlib import Path

import novomodelo_mcp

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "conferir_instalacao.py"
SERVIDOR = [sys.executable, "-m", "novomodelo_mcp"]


def _rodar(versao):
    return subprocess.run([sys.executable, str(SCRIPT), "--versao", versao, "--", *SERVIDOR],
                          capture_output=True, encoding="utf-8", errors="replace", timeout=120,
                          env={**os.environ, "PYTHONPATH": str(ROOT / "src")})


def test_versao_certa_passa():
    proc = _rodar(novomodelo_mcp.__version__)
    assert proc.returncode == 0, proc.stderr
    assert f"initialize: novomodelo {novomodelo_mcp.__version__}" in proc.stdout


def test_versao_errada_falha():
    proc = _rodar("9.9.9")
    assert proc.returncode == 1 and "esperada 9.9.9" in proc.stderr
