"""`novomodelo-mcp configurar`: grava só a entrada `novomodelo`, com backup, e é idempotente.

Tudo num HOME temporário: nenhum arquivo de cliente real é tocado.
"""
import json
import os
import sysconfig
from pathlib import Path

import pytest

from novomodelo_mcp import client_config as C
from novomodelo_mcp.server import build_server

CLIENTES = ("claude-desktop", "claude-code", "kiro")


@pytest.fixture
def home(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setattr(C, "_home", lambda: casa)
    monkeypatch.setenv("APPDATA", str(casa / "AppData" / "Roaming"))
    return casa


def _leitura_do_servidor():
    return sorted(t.name for t in build_server()._tool_manager.list_tools()
                  if t.annotations.readOnlyHint)


def _entrada(cliente):
    return json.loads(C.config_path(cliente).read_text(encoding="utf-8"))["mcpServers"]["novomodelo"]


def _backups(path: Path):
    return sorted(path.parent.glob(f"{path.name}.bak-*"))


@pytest.mark.parametrize("cliente", CLIENTES)
def test_cria_o_arquivo_quando_nao_existe(home, cliente):
    assert C.main(["--cliente", cliente]) == 0
    entrada = _entrada(cliente)
    assert Path(entrada["command"]).is_absolute()
    assert entrada["env"] == {}
    assert entrada.get("type") == ("stdio" if cliente == "claude-code" else None)
    assert str(C.config_path(cliente)).startswith(str(home))


@pytest.mark.parametrize("cliente", CLIENTES)
def test_preserva_o_resto_faz_backup_e_e_idempotente(home, cliente):
    path = C.config_path(cliente)
    path.parent.mkdir(parents=True, exist_ok=True)
    original = {"mcpServers": {"outro": {"command": "x"}, "novomodelo": {"command": "velho"}},
                "preferencia": True}
    path.write_text(json.dumps(original), encoding="utf-8")
    antes = path.read_bytes()

    assert C.main(["--cliente", cliente]) == 0
    gravado = json.loads(path.read_text(encoding="utf-8"))
    assert gravado["preferencia"] is True
    assert gravado["mcpServers"]["outro"] == {"command": "x"}
    assert gravado["mcpServers"]["novomodelo"]["command"] != "velho"
    [backup] = _backups(path)
    assert backup.read_bytes() == antes

    depois = path.read_bytes()
    assert C.main(["--cliente", cliente]) == 0
    assert path.read_bytes() == depois
    assert len(_backups(path)) == 1


def test_lista_liberada_e_a_das_tools_de_leitura_do_servidor(home):
    leitura = _leitura_do_servidor()
    assert C.read_only_tools() == leitura
    C.main(["--cliente", "claude-code"])
    allow = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))[
        "permissions"]["allow"]
    assert allow == [f"mcp__novomodelo__{t}" for t in leitura]
    C.main(["--cliente", "kiro"])
    assert _entrada("kiro")["autoApprove"] == leitura


def test_nenhuma_tool_que_grava_entra_na_lista(home):
    tools = {t.name: t for t in build_server()._tool_manager.list_tools()}
    grava = {n for n, t in tools.items() if not t.annotations.readOnlyHint}
    assert grava and not grava & set(C.read_only_tools())
    C.main(["--cliente", "claude-code"])
    allow = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))[
        "permissions"]["allow"]
    assert not any(r.endswith("*") for r in allow)
    assert not {r.removeprefix("mcp__novomodelo__") for r in allow} & grava


def test_liberacao_preserva_as_regras_que_ja_existiam(home):
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}, "x": 1}),
                        encoding="utf-8")
    C.main(["--cliente", "claude-code"])
    gravado = json.loads(settings.read_text(encoding="utf-8"))
    assert gravado["x"] == 1 and gravado["permissions"]["allow"][0] == "Bash(ls:*)"


@pytest.mark.parametrize("cliente", CLIENTES)
def test_mostrar_nao_grava_nada(home, cliente, capsys):
    assert C.main(["--cliente", cliente, "--mostrar", "--instrucoes"]) == 0
    assert [p for p in home.rglob("*") if p.is_file()] == []
    saida = capsys.readouterr().out
    assert '"novomodelo"' in saida and str(C.config_path(cliente)) in saida


def test_mostrar_imprime_so_o_trecho_e_nao_o_arquivo_inteiro(home, capsys):
    path = C.config_path("claude-code")
    path.write_text(json.dumps({"projects": {"segredo-do-historico": 1}}), encoding="utf-8")
    C.main(["--cliente", "claude-code", "--mostrar"])
    assert "segredo-do-historico" not in capsys.readouterr().out


def test_command_e_o_executavel_deste_pacote_mesmo_com_outro_antes_no_path(
        home, tmp_path, monkeypatch):
    nome = "novomodelo-mcp.exe" if os.name == "nt" else "novomodelo-mcp"
    for pasta in ("outro-no-path", "scripts-deste"):
        (tmp_path / pasta).mkdir()
        exe = tmp_path / pasta / nome
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "outro-no-path"))
    real = sysconfig.get_path
    monkeypatch.setattr(sysconfig, "get_path", lambda key, *a, **k: (
        str(tmp_path / "scripts-deste") if key == "scripts" else real(key, *a, **k)))
    C.main(["--cliente", "kiro"])
    command = _entrada("kiro")["command"]
    assert os.path.normcase(command) == os.path.normcase(tmp_path / "scripts-deste" / nome)


def test_workspace_vai_para_o_env_e_nada_mais(home, tmp_path):
    estudos = tmp_path / "estudos"
    estudos.mkdir()
    C.main(["--cliente", "claude-desktop", "--workspace", str(estudos)])
    assert _entrada("claude-desktop")["env"] == {"NOVOMODELO_MCP_WORKSPACE": str(estudos.resolve())}


def test_sem_instrucoes_nenhum_arquivo_de_instrucoes_e_tocado(home):
    C.main(["--cliente", "claude-code"])
    C.main(["--cliente", "kiro"])
    assert not (home / ".claude" / "CLAUDE.md").exists()
    assert not (home / ".kiro" / "steering").exists()


def test_instrucoes_aparecem_uma_vez_so(home):
    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True)
    claude_md.write_text("# minhas regras\n", encoding="utf-8")
    for _ in range(2):
        C.main(["--cliente", "claude-code", "--instrucoes"])
        C.main(["--cliente", "kiro", "--instrucoes"])
    texto = claude_md.read_text(encoding="utf-8")
    assert texto.startswith("# minhas regras\n") and texto.count(C.INSTRUCTIONS_LINE) == 1
    steering = (home / ".kiro" / "steering" / "novomodelo.md").read_text(encoding="utf-8")
    assert "inclusion: always" in steering and steering.count(C.INSTRUCTIONS_LINE) == 1


def test_desktop_instrucoes_so_imprime_a_linha(home, capsys):
    C.main(["--cliente", "claude-desktop", "--instrucoes"])
    assert C.INSTRUCTIONS_LINE in capsys.readouterr().out
    assert [p.name for p in home.rglob("*.md")] == []


def test_json_invalido_erro_claro_e_nada_gravado(home, capsys):
    path = C.config_path("claude-code")
    path.write_text("{ isto não é json", encoding="utf-8")
    assert C.main(["--cliente", "claude-code"]) == 1
    assert "não é um JSON válido" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == "{ isto não é json"
    assert _backups(path) == [] and not (home / ".claude").exists()


def test_sem_subcomando_o_executavel_sobe_o_servidor(monkeypatch):
    from novomodelo_mcp import server
    chamado = []
    monkeypatch.setattr(server, "build_server", lambda: type("S", (), {
        "run": lambda self: chamado.append("run")})())
    monkeypatch.setattr("sys.argv", ["novomodelo-mcp"])
    server.main()
    assert chamado == ["run"]


def test_subcomando_configurar_pelo_executavel(home, monkeypatch):
    from novomodelo_mcp import server
    monkeypatch.setattr("sys.argv", ["novomodelo-mcp", "configurar", "--cliente", "kiro"])
    with pytest.raises(SystemExit) as saida:
        server.main()
    assert saida.value.code == 0 and C.config_path("kiro").exists()
