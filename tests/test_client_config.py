"""`novomodelo-mcp configurar`: grava só a entrada `novomodelo`, com backup, e é idempotente.

Tudo num HOME temporário: nenhum arquivo de cliente real é tocado.
"""

import json
import os
import sysconfig
from pathlib import Path

import pytest
from mcp.server.fastmcp.tools import Tool

from novomodelo_mcp import client_config as C
from novomodelo_mcp.server import build_server

CLIENTES = ("claude-desktop", "claude-code", "kiro")


@pytest.fixture
def home(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setattr(C, "_home", lambda: casa)
    monkeypatch.setenv("APPDATA", str(casa / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(casa / "AppData" / "Local"))
    (tmp_path / "path-vazio").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "path-vazio"))
    monkeypatch.setattr(C, "SYSTEM_APPS", tmp_path / "Applications", raising=False)
    return casa


def _read_only(tool: Tool) -> bool:
    assert tool.annotations is not None
    return bool(tool.annotations.readOnlyHint)


def _leitura_do_servidor():
    return sorted(t.name for t in build_server()._tool_manager.list_tools() if _read_only(t))


def _entrada(cliente):
    return json.loads(C.config_path(cliente).read_text(encoding="utf-8"))["mcpServers"][
        "novomodelo"
    ]


def _backups(path: Path):
    return sorted(path.parent.glob(f"{path.name}.bak-*"))


@pytest.mark.parametrize("cliente", CLIENTES)
def test_cria_o_arquivo_quando_nao_existe(home, cliente):
    assert C.main(["--irrestrito", "--cliente", cliente]) == 0
    entrada = _entrada(cliente)
    assert Path(entrada["command"]).is_absolute()
    assert entrada["env"] == {}
    assert entrada.get("type") == ("stdio" if cliente == "claude-code" else None)
    assert str(C.config_path(cliente)).startswith(str(home))


@pytest.mark.parametrize("cliente", CLIENTES)
def test_preserva_o_resto_faz_backup_e_e_idempotente(home, cliente):
    path = C.config_path(cliente)
    path.parent.mkdir(parents=True, exist_ok=True)
    original = {
        "mcpServers": {"outro": {"command": "x"}, "novomodelo": {"command": "velho"}},
        "preferencia": True,
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    antes = path.read_bytes()

    assert C.main(["--irrestrito", "--cliente", cliente]) == 0
    gravado = json.loads(path.read_text(encoding="utf-8"))
    assert gravado["preferencia"] is True
    assert gravado["mcpServers"]["outro"] == {"command": "x"}
    assert gravado["mcpServers"]["novomodelo"]["command"] != "velho"
    [backup] = _backups(path)
    assert backup.read_bytes() == antes

    depois = path.read_bytes()
    assert C.main(["--irrestrito", "--cliente", cliente]) == 0
    assert path.read_bytes() == depois
    assert len(_backups(path)) == 1


def test_lista_liberada_e_a_das_tools_de_leitura_do_servidor(home):
    leitura = _leitura_do_servidor()
    assert C.read_only_tools() == leitura
    C.main(["--irrestrito", "--cliente", "claude-code"])
    allow = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))[
        "permissions"
    ]["allow"]
    assert allow == [f"mcp__novomodelo__{t}" for t in leitura]
    C.main(["--irrestrito", "--cliente", "kiro"])
    assert _entrada("kiro")["autoApprove"] == leitura


def test_nenhuma_tool_que_grava_entra_na_lista(home):
    tools = {t.name: t for t in build_server()._tool_manager.list_tools()}
    grava = {n for n, t in tools.items() if not _read_only(t)}
    assert grava and not grava & set(C.read_only_tools())
    C.main(["--irrestrito", "--cliente", "claude-code"])
    allow = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))[
        "permissions"
    ]["allow"]
    assert not any(r.endswith("*") for r in allow)
    assert not {r.removeprefix("mcp__novomodelo__") for r in allow} & grava


def test_liberacao_preserva_as_regras_que_ja_existiam(home):
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}, "x": 1}), encoding="utf-8"
    )
    C.main(["--irrestrito", "--cliente", "claude-code"])
    gravado = json.loads(settings.read_text(encoding="utf-8"))
    assert gravado["x"] == 1 and gravado["permissions"]["allow"][0] == "Bash(ls:*)"


@pytest.mark.parametrize("cliente", CLIENTES)
def test_mostrar_nao_grava_nada(home, cliente, capsys):
    assert C.main(["--irrestrito", "--cliente", cliente, "--mostrar", "--instrucoes"]) == 0
    assert [p for p in home.rglob("*") if p.is_file()] == []
    saida = capsys.readouterr().out
    assert '"novomodelo"' in saida and str(C.config_path(cliente)) in saida


def test_mostrar_imprime_so_o_trecho_e_nao_o_arquivo_inteiro(home, capsys):
    path = C.config_path("claude-code")
    path.write_text(json.dumps({"projects": {"segredo-do-historico": 1}}), encoding="utf-8")
    C.main(["--irrestrito", "--cliente", "claude-code", "--mostrar"])
    assert "segredo-do-historico" not in capsys.readouterr().out


def test_command_e_o_executavel_deste_pacote_mesmo_com_outro_antes_no_path(
    home, tmp_path, monkeypatch
):
    nome = "novomodelo-mcp.exe" if os.name == "nt" else "novomodelo-mcp"
    for pasta in ("outro-no-path", "scripts-deste"):
        (tmp_path / pasta).mkdir()
        exe = tmp_path / pasta / nome
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "outro-no-path"))
    real = sysconfig.get_path
    monkeypatch.setattr(
        sysconfig,
        "get_path",
        lambda key, *a, **k: (
            str(tmp_path / "scripts-deste") if key == "scripts" else real(key, *a, **k)
        ),
    )
    C.main(["--irrestrito", "--cliente", "kiro"])
    command = _entrada("kiro")["command"]
    assert os.path.normcase(command) == os.path.normcase(tmp_path / "scripts-deste" / nome)


def test_workspace_vai_para_o_env_e_nada_mais(home, tmp_path):
    estudos = tmp_path / "estudos"
    estudos.mkdir()
    C.main(["--cliente", "claude-desktop", "--workspace", str(estudos)])
    assert _entrada("claude-desktop")["env"] == {"NOVOMODELO_MCP_WORKSPACE": str(estudos.resolve())}


def test_sem_instrucoes_nenhum_arquivo_de_instrucoes_e_tocado(home):
    C.main(["--irrestrito", "--cliente", "claude-code"])
    C.main(["--irrestrito", "--cliente", "kiro"])
    assert not (home / ".claude" / "CLAUDE.md").exists()
    assert not (home / ".kiro" / "steering").exists()


def test_instrucoes_aparecem_uma_vez_so(home):
    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True)
    claude_md.write_text("# minhas regras\n", encoding="utf-8")
    for _ in range(2):
        C.main(["--irrestrito", "--cliente", "claude-code", "--instrucoes"])
        C.main(["--irrestrito", "--cliente", "kiro", "--instrucoes"])
    texto = claude_md.read_text(encoding="utf-8")
    assert texto.startswith("# minhas regras\n") and texto.count(C.INSTRUCTIONS_LINE) == 1
    steering = (home / ".kiro" / "steering" / "novomodelo.md").read_text(encoding="utf-8")
    assert "inclusion: always" in steering and steering.count(C.INSTRUCTIONS_LINE) == 1


def test_desktop_instrucoes_so_imprime_a_linha(home, capsys):
    C.main(["--irrestrito", "--cliente", "claude-desktop", "--instrucoes"])
    assert C.INSTRUCTIONS_LINE in capsys.readouterr().out
    assert [p.name for p in home.rglob("*.md")] == []


def test_json_invalido_erro_claro_e_nada_gravado(home, capsys):
    path = C.config_path("claude-code")
    path.write_text("{ isto não é json", encoding="utf-8")
    assert C.main(["--irrestrito", "--cliente", "claude-code"]) == 1
    assert "não é um JSON válido" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == "{ isto não é json"
    assert _backups(path) == [] and not (home / ".claude").exists()


def test_sem_subcomando_o_executavel_sobe_o_servidor(monkeypatch):
    from novomodelo_mcp import server

    chamado = []
    monkeypatch.setattr(
        server, "build_server", lambda: type("S", (), {"run": lambda self: chamado.append("run")})()
    )
    monkeypatch.setattr("sys.argv", ["novomodelo-mcp"])
    server.main()
    assert chamado == ["run"]


def test_subcomando_configurar_pelo_executavel(home, monkeypatch):
    from novomodelo_mcp import server

    monkeypatch.setattr(
        "sys.argv", ["novomodelo-mcp", "configurar", "--irrestrito", "--cliente", "kiro"]
    )
    with pytest.raises(SystemExit) as saida:
        server.main()
    assert saida.value.code == 0 and C.config_path("kiro").exists()


def test_workspace_que_nao_existe_e_criado_ao_gravar(home, tmp_path, capsys):
    pasta = tmp_path / "Documents" / "novomodelo"
    assert C.main(["--cliente", "claude-desktop", "--workspace", str(pasta)]) == 0
    assert pasta.is_dir()
    assert str(pasta) in capsys.readouterr().out
    assert _entrada("claude-desktop")["env"]["NOVOMODELO_MCP_WORKSPACE"] == str(pasta.resolve())


def test_mostrar_nao_cria_o_workspace(home, tmp_path):
    pasta = tmp_path / "novomodelo"
    assert C.main(["--cliente", "kiro", "--workspace", str(pasta), "--mostrar"]) == 0
    assert not pasta.exists()


def test_workspace_que_ja_existe_continua_igual(home, tmp_path):
    pasta = tmp_path / "estudos"
    pasta.mkdir()
    (pasta / "caso.json").write_text("{}", encoding="utf-8")
    assert C.main(["--cliente", "kiro", "--workspace", str(pasta)]) == 0
    assert (pasta / "caso.json").read_text(encoding="utf-8") == "{}"


def test_workspace_que_nao_pode_ser_criado_da_erro_claro(home, tmp_path, capsys):
    arquivo = tmp_path / "um-arquivo"
    arquivo.write_text("x", encoding="utf-8")
    assert C.main(["--cliente", "kiro", "--workspace", str(arquivo / "novomodelo")]) == 1
    assert "não foi possível criar a pasta" in capsys.readouterr().err
    assert not C.config_path("kiro").exists()


FECHAR_CLAUDE_CODE = "Feche o Claude Code antes de gravar"
REABRIR = "Feche e abra o cliente e peça o server_info."


def test_aviso_de_fechar_o_claude_code_sai_antes_de_gravar(home, capsys):
    assert C.main(["--irrestrito", "--cliente", "claude-code"]) == 0
    linhas = capsys.readouterr().out.splitlines()
    aviso = next(i for i, linha in enumerate(linhas) if linha.startswith(FECHAR_CLAUDE_CODE))
    gravou = next(
        i for i, linha in enumerate(linhas) if linha.startswith(("criado:", "atualizado:"))
    )
    assert aviso < gravou


def test_mostrar_tambem_avisa_para_fechar_antes_de_gravar(home, capsys):
    assert C.main(["--irrestrito", "--cliente", "claude-code", "--mostrar"]) == 0
    linhas = capsys.readouterr().out.splitlines()
    assert linhas[0].startswith(FECHAR_CLAUDE_CODE)
    assert REABRIR not in linhas


@pytest.mark.parametrize("cliente", CLIENTES)
def test_depois_de_gravar_so_pede_para_reabrir_o_cliente(home, cliente, capsys):
    assert C.main(["--irrestrito", "--cliente", cliente]) == 0
    saida = capsys.readouterr().out
    assert saida.splitlines()[-1] == REABRIR
    assert "Depois, feche o cliente" not in saida


NOMES = {"claude-desktop": "Claude Desktop", "claude-code": "Claude Code", "kiro": "Kiro"}


def _nao_encontrado(cliente):
    return (
        f"{NOMES[cliente]} não encontrado nesta máquina; a configuração fica pronta para "
        "quando você instalar"
    )


@pytest.mark.parametrize("cliente", CLIENTES)
def test_cliente_ausente_avisa_e_grava_mesmo_assim(home, cliente, capsys):
    assert C.main(["--irrestrito", "--cliente", cliente]) == 0
    linhas = capsys.readouterr().out.splitlines()
    aviso = next(i for i, linha in enumerate(linhas) if linha.startswith(_nao_encontrado(cliente)))
    gravou = next(
        i for i, linha in enumerate(linhas) if linha.startswith(("criado:", "atualizado:"))
    )
    assert aviso < gravou and C.config_path(cliente).exists()


@pytest.mark.parametrize("cliente", CLIENTES)
def test_mostrar_tambem_avisa_que_o_cliente_nao_foi_encontrado(home, cliente, capsys):
    assert C.main(["--irrestrito", "--cliente", cliente, "--mostrar"]) == 0
    assert _nao_encontrado(cliente) in capsys.readouterr().out
    assert [p for p in home.rglob("*") if p.is_file()] == []


@pytest.mark.parametrize(
    "cliente,pasta", [("claude-desktop", None), ("claude-code", ".claude"), ("kiro", ".kiro")]
)
def test_pasta_de_configuracao_do_cliente_conta_como_encontrado(home, cliente, pasta, capsys):
    (home / pasta if pasta else C.config_path(cliente).parent).mkdir(parents=True)
    assert C.main(["--irrestrito", "--cliente", cliente]) == 0
    assert "não encontrado nesta máquina" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "cliente,programa", [("claude-code", "claude"), ("kiro", "kiro"), ("kiro", "kiro-cli")]
)
def test_programa_no_path_conta_como_encontrado(
    home, tmp_path, monkeypatch, cliente, programa, capsys
):
    pasta = tmp_path / "bin"
    pasta.mkdir()
    exe = pasta / (f"{programa}.exe" if os.name == "nt" else programa)
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(pasta))
    assert C.main(["--irrestrito", "--cliente", cliente]) == 0
    assert "não encontrado nesta máquina" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "plataforma,cliente,instalado",
    [
        ("darwin", "claude-desktop", "Applications/Claude.app"),
        ("darwin", "kiro", "Applications/Kiro.app"),
        ("win32", "claude-desktop", "AppData/Local/AnthropicClaude"),
        ("win32", "claude-desktop", "AppData/Local/Programs/Claude"),
        ("win32", "kiro", "AppData/Local/Programs/Kiro"),
    ],
)
def test_programa_instalado_conta_como_encontrado(
    home, tmp_path, monkeypatch, plataforma, cliente, instalado, capsys
):
    monkeypatch.setattr(C.sys, "platform", plataforma)
    monkeypatch.setattr(C.shutil, "which", lambda name: None)
    assert not C.client_found(cliente)
    base = tmp_path if instalado.startswith("Applications") else home
    (base / instalado).mkdir(parents=True)
    assert C.client_found(cliente)


def test_claude_code_instalado_localmente_conta_como_encontrado(home):
    local = home / ".claude" / "local"
    local.mkdir(parents=True)
    (local / "claude").write_text("", encoding="utf-8")
    assert C.client_found("claude-code")


class _Terminal:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


def _respostas(monkeypatch, *linhas):
    fila = list(linhas)

    def responder(_prompt=""):
        if not fila:
            raise EOFError
        return fila.pop(0)

    monkeypatch.setattr(C.sys, "stdin", _Terminal(True))
    monkeypatch.setattr("builtins.input", responder)
    return fila


@pytest.mark.parametrize("extra", [[], ["--mostrar"]])
def test_sem_pasta_e_sem_terminal_sai_com_erro_e_nao_grava(home, monkeypatch, capsys, extra):
    monkeypatch.setattr(C.sys, "stdin", _Terminal(False))
    assert C.main(["--cliente", "claude-code", *extra]) == 2
    assert "--workspace <pasta>" in capsys.readouterr().err
    assert [p for p in home.rglob("*") if p.is_file()] == []


def test_sem_pasta_com_terminal_grava_as_pastas_digitadas(home, tmp_path, monkeypatch):
    a, b = tmp_path / "estudos", tmp_path / "Meus Estudos"
    _respostas(monkeypatch, "", str(a), f'"{b}"', "")
    assert C.main(["--cliente", "kiro"]) == 0
    raizes = _entrada("kiro")["env"]["NOVOMODELO_MCP_WORKSPACE"].split(os.pathsep)
    assert raizes == [str(a.resolve()), str(b.resolve())] and a.is_dir() and b.is_dir()


def test_pergunta_nunca_grava_a_sugestao_sem_ela_ser_digitada(home, monkeypatch, capsys):
    _respostas(monkeypatch, "", "")
    assert C.main(["--cliente", "kiro"]) == 2
    assert str(home / "novomodelo") in capsys.readouterr().out
    assert not C.config_path("kiro").exists() and not (home / "novomodelo").exists()


def test_irrestrito_grava_sem_workspace(home):
    assert C.main(["--irrestrito", "--cliente", "claude-desktop"]) == 0
    assert "NOVOMODELO_MCP_WORKSPACE" not in _entrada("claude-desktop")["env"]


def test_irrestrito_com_workspace_e_erro_de_uso(home, tmp_path):
    with pytest.raises(SystemExit) as saida:
        C.main(["--irrestrito", "--workspace", str(tmp_path), "--cliente", "kiro"])
    assert saida.value.code == 2 and not C.config_path("kiro").exists()
