"""`install_novomodelo`: só o instalador oficial da versão esperada, com o hash conferido.

Sem rede real: a API do GitHub e o download são substituídos; o instalador é um fake.
"""

import hashlib
import json
import os
import sys
import urllib.error
from pathlib import Path

import pytest

from novomodelo_mcp.adapters import installer as I
from novomodelo_mcp.adapters import versions as V

VERSAO = "0.18.0"
SCRIPT = b"#!/bin/sh\necho instalador oficial\n"
BASE = f"https://github.com/ons-ccee-epe/novomodelo/releases/download/v{VERSAO}/"


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    V.reset_caches()
    monkeypatch.setattr(V, "expected_version", lambda: VERSAO)
    monkeypatch.setattr(V, "expected_bridge_version", lambda: VERSAO)
    yield
    V.reset_caches()


@pytest.fixture
def rede(monkeypatch):
    """API com o digest do instalador e o download dele; registra as URLs pedidas."""
    pedidas = []
    estado = {"script": SCRIPT, "digest": hashlib.sha256(SCRIPT).hexdigest(), "falha": None}

    def _fetch_bytes(url, *, timeout):
        pedidas.append(url)
        if estado["falha"]:
            return {"network_warning": estado["falha"]}
        if url.startswith("https://api.github.com/"):
            assets = [
                {"name": n, "digest": f"sha256:{estado['digest']}"}
                for n in ("novomodelo-cli-installer.sh", "novomodelo-cli-installer.ps1")
            ]
            return json.dumps({"tag_name": f"v{VERSAO}", "assets": assets}).encode()
        return estado["script"]

    monkeypatch.setattr(V, "fetch_bytes", _fetch_bytes)
    return pedidas, estado


BINARIO = "novomodelo.exe" if sys.platform == "win32" else "novomodelo"


@pytest.fixture
def instalador(monkeypatch, tmp_path):
    """Substitui a execução do instalador; o fake cria o binário que responde a versão.

    No Windows o binário falso não é um `.exe` de verdade: a pergunta da versão é
    substituída, e o resto da verificação (nome e caminho do binário) continua real.
    """
    execucoes = []

    def _run(cmd, **kw):
        execucoes.append({"cmd": cmd, "env": kw.get("env")})
        dest = kw["env"]["NOVOMODELO_CLI_INSTALL_DIR"]
        os.makedirs(os.path.join(dest, "bin"), exist_ok=True)
        binario = os.path.join(dest, "bin", BINARIO)
        with open(binario, "w", encoding="utf-8") as fh:
            fh.write(f"#!/bin/sh\necho 'novomodelo   v{VERSAO}'\n")
        os.chmod(binario, 0o755)
        return types_proc(0, "instalado", "")

    monkeypatch.setattr(I, "_run_installer", _run)
    if sys.platform == "win32":
        monkeypatch.setattr(
            I,
            "tool_version",
            lambda path: f"novomodelo   v{VERSAO}" if os.path.basename(path) == BINARIO else None,
        )
    return execucoes


def types_proc(code, out, err):
    import types

    return types.SimpleNamespace(returncode=code, stdout=out, stderr=err)


def test_sem_confirmar_devolve_so_o_plano(rede, instalador, tmp_path):
    pedidas, _ = rede
    env = I.install(confirm=False, install_dir=str(tmp_path / "nm"))
    assert env["status"] == "ok" and env["executed"] is False
    plano = env["plan"]
    assert plano["url"].startswith(BASE) and plano["sha256"] == hashlib.sha256(SCRIPT).hexdigest()
    assert plano["destination"] == str(tmp_path / "nm" / "bin")
    assert env["manual_command"]
    assert not any(u.startswith("https://github.com/") for u in pedidas)
    assert instalador == []


def test_url_so_do_release_oficial_da_versao_esperada():
    url = I.installer_url(VERSAO)
    assert url.startswith(BASE)
    assert url.rsplit("/", 1)[1] in ("novomodelo-cli-installer.sh", "novomodelo-cli-installer.ps1")


def test_hash_errado_nada_e_executado(rede, instalador, tmp_path):
    _, estado = rede
    estado["script"] = b"#!/bin/sh\necho adulterado\n"
    env = I.install(confirm=True, install_dir=str(tmp_path / "nm"))
    assert env["status"] == "error" and "hash" in " ".join(env["diagnostics"])
    assert env["manual_command"] and instalador == []
    assert not (tmp_path / "nm").exists()


def test_sem_rede_aviso_com_o_comando_manual(rede, instalador, tmp_path):
    _, estado = rede
    estado["falha"] = "não foi possível acessar api.github.com: sem conexão"
    env = I.install(confirm=True, install_dir=str(tmp_path / "nm"))
    assert env["status"] == "error" and env["network_warning"] and env["manual_command"]
    assert instalador == []


def test_variaveis_que_trocam_a_origem_nao_chegam_ao_instalador(
    rede, instalador, tmp_path, monkeypatch
):
    for var in I.SCRUBBED_ENV:
        monkeypatch.setenv(var, "https://evil.example/")
    env = I.install(confirm=True, install_dir=str(tmp_path / "nm"))
    assert env["status"] == "ok", env
    passado = instalador[0]["env"]
    assert not any(v in passado for v in I.SCRUBBED_ENV)
    assert passado["NOVOMODELO_CLI_INSTALL_DIR"] == str(tmp_path / "nm")
    assert "NOVOMODELO_CLI_NO_MODIFY_PATH" not in passado


def test_instalacao_confirma_a_versao_e_devolve_o_caminho(rede, instalador, tmp_path):
    env = I.install(confirm=True, install_dir=str(tmp_path / "nm"))
    assert env["status"] == "ok" and env["executed"] is True
    assert env["installed_version"] == VERSAO
    assert Path(env["path"]) == tmp_path / "nm" / "bin" / BINARIO
    assert "NOVOMODELO_MCP_SOLVER_BIN" in env["configuration"]


def test_pasta_relativa_e_recusada(rede, instalador):
    env = I.install(confirm=True, install_dir="relativa/nm")
    assert env["status"] == "error" and env["exit_code"] == 22 and instalador == []


def test_redirecionamento_para_outro_host_e_recusado():
    handler = V._AllowlistRedirect()
    with pytest.raises(urllib.error.URLError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/x")


def test_tool_nunca_levanta(monkeypatch):
    from novomodelo_mcp.server import build_server

    monkeypatch.setattr(I, "install", lambda **k: 1 / 0)
    fn = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}["install_novomodelo"]
    assert fn()["status"] == "error"


def test_aviso_de_executavel_ausente_sugere_a_tool(monkeypatch):
    monkeypatch.setattr(
        V,
        "_read_local",
        lambda settings: {
            "executable": {"version": None, "reason": "não encontrado"},
            "library": {"version": VERSAO},
            "bridge": {"version": VERSAO},
            "docs": {"version": None, "reason": "sem manifesto"},
        },
    )
    avisos = V.version_warnings(object())
    assert len(avisos) == 1 and "install_novomodelo" in avisos[0]
