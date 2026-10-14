"""A saída do novomodelo e do bridge é lida em UTF-8 qualquer que seja a codificação do sistema.

Os dois programas escrevem UTF-8. Lida na codificação local (cp1252 no Windows), a
saída acentuada vira texto trocado, ou some: no Windows a thread que lê o pipe
morre no erro de decodificação e o `stdout` chega como `None`. O teste chama os
adaptadores num processo filho com uma locale que não é UTF-8.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
TEXTO = "São José — ”"

_PROGRAMA = f"""
import json, os, sys
argv = sys.argv[1:]
if argv[:1] in (["--version"], ["version"]):
    linha = "novomodelo v0.18.0 {TEXTO}"
else:
    linha = json.dumps({{"status": "ok", "msg": "{TEXTO}",
                         "pythonioencoding": os.environ.get("PYTHONIOENCODING")}},
                       ensure_ascii=False)
sys.stdout.buffer.write((linha + "\\n").encode("utf-8"))
"""

_DRIVER = """
import json, sys
from novomodelo_mcp.adapters.bridge import run_bridge
from novomodelo_mcp.adapters.discovery import tool_version
from novomodelo_mcp.adapters.novomodelo import run_novomodelo
out = {"novomodelo": run_novomodelo(["validate", "x"]), "bridge": run_bridge(["check", "x"]),
       "versao": tool_version(sys.argv[1])}
sys.stdout.buffer.write(json.dumps(out, ensure_ascii=True).encode("ascii"))
"""


def _programa_falso(tmp_path: Path) -> str:
    script = tmp_path / "programa_utf8.py"
    script.write_text(_PROGRAMA, encoding="utf-8")
    if os.name == "nt":
        launcher = tmp_path / "programa.cmd"
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
                            encoding="utf-8")
    else:
        launcher = tmp_path / "programa"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
                            encoding="utf-8")
        launcher.chmod(0o755)
    return str(launcher)


def _locale_nao_utf8() -> str | None:
    if os.name == "nt":
        return None
    available = subprocess.run(["locale", "-a"], capture_output=True, encoding="utf-8",
                               errors="replace").stdout.split()
    return next((n for n in ("pt_BR.ISO8859-1", "en_US.ISO8859-1", "pt_BR.iso88591",
                             "en_US.iso88591") if n in available), None)


def _adaptadores_numa_locale_nao_utf8(tmp_path: Path) -> dict:
    programa = _programa_falso(tmp_path)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("LC_", "NOVOMODELO_MCP_", "PYTHONIOENCODING"))}
    env.update(PYTHONUTF8="0", PYTHONPATH=str(SRC), NOVOMODELO_MCP_SOLVER_BIN=programa,
               NOVOMODELO_MCP_BRIDGE_BIN=programa)
    if name := _locale_nao_utf8():
        env.update(LC_ALL=name, LANG=name)
    proc = subprocess.run([sys.executable, "-c", _DRIVER, programa], capture_output=True,
                          env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    return json.loads(proc.stdout.decode("ascii"))


def test_saida_acentuada_do_novomodelo_chega_intacta(tmp_path):
    out = _adaptadores_numa_locale_nao_utf8(tmp_path)["novomodelo"]
    assert out["status"] == "ok" and out["msg"] == TEXTO


def test_saida_acentuada_do_bridge_chega_intacta_e_o_filho_escreve_utf8(tmp_path):
    out = _adaptadores_numa_locale_nao_utf8(tmp_path)["bridge"]
    assert out["status"] == "ok" and out["msg"] == TEXTO
    assert out["pythonioencoding"] == "utf-8"


def test_versao_acentuada_chega_intacta(tmp_path):
    assert _adaptadores_numa_locale_nao_utf8(tmp_path)["versao"] == f"novomodelo v0.18.0 {TEXTO}"
