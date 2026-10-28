"""`deck_edit_json` lê e grava o deck em UTF-8 qualquer que seja a codificação do sistema.

O padrão do Windows é cp1252: sem `encoding` explícito, um deck acentuado seria
lido e regravado na codificação local, corrompendo o arquivo do usuário. O teste
roda a edição num processo filho com uma locale que não é UTF-8.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
NOME = "Itaparica — São José"
NOVO = "Sobradinho — Juazeiro"

_DRIVER = """
import dataclasses, json, sys
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.tools.deck import register_deck

class _CaptureMCP:
    def __init__(self):
        self.tools = {}
    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco

mcp = _CaptureMCP()
register_deck(mcp, dataclasses.replace(load_settings(), solver_bin=sys.argv[2]))
out = mcp.tools["deck_edit_json"](sys.argv[1], json.loads(sys.argv[3]))
sys.stdout.buffer.write(json.dumps(out, ensure_ascii=True).encode("ascii"))
"""


def _locale_nao_utf8() -> str | None:
    available = (
        subprocess.run(
            ["locale", "-a"], capture_output=True, encoding="utf-8", errors="replace"
        ).stdout.split()
        if os.name != "nt"
        else []
    )
    for name in ("pt_BR.ISO8859-1", "en_US.ISO8859-1", "pt_BR.iso88591", "en_US.iso88591"):
        if name in available:
            return name
    return None


def _edit_numa_locale_nao_utf8(path: Path, changes: list[dict], tmp_path: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LC_", "NOVOMODELO_MCP_"))}
    env.update(PYTHONUTF8="0", PYTHONPATH=str(SRC))
    if name := _locale_nao_utf8():
        env.update(LC_ALL=name, LANG=name)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            _DRIVER,
            str(path),
            str(tmp_path / "novomodelo-inexistente"),
            json.dumps(changes),
        ],
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    return json.loads(proc.stdout.decode("ascii"))


def _deck(tmp_path: Path) -> Path:
    deck = tmp_path / "notas.json"
    deck.write_bytes(
        json.dumps({"nome": NOME, "limite": 50}, ensure_ascii=False, indent=2).encode("utf-8")
    )
    return deck


def test_deck_acentuado_continua_utf8_depois_da_edicao(tmp_path):
    deck = _deck(tmp_path)
    out = _edit_numa_locale_nao_utf8(deck, [{"path": "limite", "value": 99}], tmp_path)
    assert out["status"] == "ok" and out["written"] is True
    assert json.loads(deck.read_bytes().decode("utf-8")) == {"nome": NOME, "limite": 99}
    assert (tmp_path / "notas.json.bak").read_bytes().decode("utf-8") == json.dumps(
        {"nome": NOME, "limite": 50}, ensure_ascii=False, indent=2
    )


def test_valor_acentuado_novo_e_gravado_em_utf8_e_o_antigo_volta_legivel(tmp_path):
    deck = _deck(tmp_path)
    out = _edit_numa_locale_nao_utf8(deck, [{"path": "nome", "value": NOVO}], tmp_path)
    assert out["status"] == "ok"
    assert out["changes"] == [{"path": "nome", "old": NOME, "new": NOVO}]
    assert json.loads(deck.read_bytes().decode("utf-8"))["nome"] == NOVO


def _edit_in_process(deck: Path) -> dict:
    from novomodelo_mcp.adapters.deck_io import edit_json

    return edit_json(str(deck), [{"path": "limite", "value": 99}])


def _deck_bytes(newline: str) -> bytes:
    text = json.dumps({"nome": NOME, "limite": 50}, ensure_ascii=False, indent=2) + "\n"
    return text.replace("\n", newline).encode("utf-8")


def test_deck_crlf_tem_backup_identico_e_continua_crlf(tmp_path):
    deck = tmp_path / "notas.json"
    original = _deck_bytes("\r\n")
    deck.write_bytes(original)
    assert _edit_in_process(deck)["written"] is True
    assert (tmp_path / "notas.json.bak").read_bytes() == original
    editado = deck.read_bytes()
    assert editado.count(b"\r\n") == editado.count(b"\n") == original.count(b"\n")
    assert json.loads(editado.decode("utf-8")) == {"nome": NOME, "limite": 99}


def test_deck_lf_continua_lf(tmp_path):
    deck = tmp_path / "notas.json"
    original = _deck_bytes("\n")
    deck.write_bytes(original)
    assert _edit_in_process(deck)["written"] is True
    assert (tmp_path / "notas.json.bak").read_bytes() == original
    assert b"\r" not in deck.read_bytes()


def test_restore_backup_devolve_os_bytes_originais(tmp_path):
    from novomodelo_mcp.adapters.deck_io import restore_backup

    deck = tmp_path / "notas.json"
    original = _deck_bytes("\r\n")
    deck.write_bytes(original)
    _edit_in_process(deck)
    assert deck.read_bytes() != original
    assert restore_backup(str(deck)) is True
    assert deck.read_bytes() == original
