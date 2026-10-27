"""O `configurar` não abre a config do cliente para outros usuários: o arquivo regravado
e o backup saem sempre em 0600."""

import os
import stat
import sys

import pytest

from novomodelo_mcp import client_config as C

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="modo POSIX")


def _modo(p):
    return stat.S_IMODE(os.stat(p).st_mode)


@POSIX
def test_regravar_preserva_0600_no_arquivo_e_no_backup(tmp_path):
    alvo = tmp_path / ".claude.json"
    alvo.write_text("{}", encoding="utf-8")
    os.chmod(alvo, 0o600)
    feito = C.apply([(alvo, '{"mcpServers": {}}', "rotulo")])
    assert _modo(alvo) == 0o600
    backups = list(tmp_path.glob(".claude.json.bak-*"))
    assert backups and all(_modo(b) == 0o600 for b in backups), feito


@POSIX
def test_arquivo_novo_nasce_0600(tmp_path):
    alvo = tmp_path / "sub" / "mcp.json"
    C.apply([(alvo, '{"mcpServers": {}}', "rotulo")])
    assert _modo(alvo) == 0o600


def test_backup_e_copia_byte_a_byte_e_o_novo_sai_sem_crlf_extra(tmp_path):
    alvo = tmp_path / "claude_desktop_config.json"
    original = b'{\r\n  "a": 1\r\n}\r\n'
    alvo.write_bytes(original)
    C.apply([(alvo, '{\n  "mcpServers": {}\n}\n', "rotulo")])
    [backup] = tmp_path.glob("claude_desktop_config.json.bak-*")
    assert backup.read_bytes() == original
    assert alvo.read_bytes() == b'{\n  "mcpServers": {}\n}\n'


@POSIX
def test_original_aberto_sai_fechado_em_0600_no_arquivo_e_no_backup(tmp_path):
    alvo = tmp_path / "claude_desktop_config.json"
    alvo.write_text("{}", encoding="utf-8")
    os.chmod(alvo, 0o664)
    C.apply([(alvo, '{"mcpServers": {}}', "rotulo")])
    assert _modo(alvo) == 0o600
    assert all(_modo(b) == 0o600 for b in tmp_path.glob("claude_desktop_config.json.bak-*"))
    assert alvo.read_text(encoding="utf-8") == '{"mcpServers": {}}'
