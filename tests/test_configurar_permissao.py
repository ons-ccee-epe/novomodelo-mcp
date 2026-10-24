"""O `configurar` não abre a config do cliente para outros usuários: o arquivo regravado
e o backup guardam o modo do original (0600 quando o arquivo é novo)."""
import os
import stat
import sys

import pytest

from novomodelo_mcp import client_config as C

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="modo POSIX")


def _modo(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def test_regravar_preserva_0600_no_arquivo_e_no_backup(tmp_path):
    alvo = tmp_path / ".claude.json"
    alvo.write_text("{}", encoding="utf-8")
    os.chmod(alvo, 0o600)
    feito = C.apply([(alvo, '{"mcpServers": {}}', "rotulo")])
    assert _modo(alvo) == 0o600
    backups = list(tmp_path.glob(".claude.json.bak-*"))
    assert backups and all(_modo(b) == 0o600 for b in backups), feito


def test_arquivo_novo_nasce_0600(tmp_path):
    alvo = tmp_path / "sub" / "mcp.json"
    C.apply([(alvo, '{"mcpServers": {}}', "rotulo")])
    assert _modo(alvo) == 0o600
