"""Comando do container, laço de leitura e registro de uma execução."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.e2e.config import MOTIVO_MOTOR, Config
from tests.e2e.executor import container
from tests.e2e.executor.container import (
    ENDURECIMENTO,
    GID_AGENTE,
    HOME_AGENTE,
    LIMITE_PIDS,
    SEGREDO_CLAUDE,
    UID_AGENTE,
    ComandoRecusado,
    Execucao,
    MotorAusente,
    Saida,
    comando,
    executar,
    limite_atingido,
    nome_container,
    rodar_container,
)
from tests.e2e.executor.eventos import Leitura
from tests.e2e.resultado.armazenamento import ler_registros
from tests.e2e.resultado.modelos import Avaliacao, Metricas
from tests.e2e.textos import sem_caminhos

FIX = Path(__file__).parent / "fixtures"
TOKEN_FALSO = "sk-ant-teste-000000000000"
SOCKETS = ("/run/podman", "/var/run/docker.sock", "docker.sock", "podman.sock")
NOME = "bateria-teste-1"


def _exec(**k) -> Execucao:
    base = dict(
        conjunto="usuario",
        caso="caso-exemplo",
        agente="claude",
        config="local",
        repeticao=1,
        pedido="p",
        caso_origem=None,
        somente_leitura=False,
        timeout_s=60,
        imagem="localhost/bateria:local",
    )
    return Execucao(**{**base, **k})


def _cfg(tmp_path: Path, motor: str = "podman", memoria: str = "6g") -> Config:
    return Config(
        motor=motor,
        resultados=tmp_path / "resultados",
        casos=None,
        cenarios_extra=None,
        token_claude=tmp_path / "segredos" / "token-claude",
        volume_kiro="volume-kiro-teste",
        cache=tmp_path / "cache",
        memoria=memoria,
    )


def _cmd(e: Execucao, cfg: Config, trabalho: Path) -> list[str]:
    return comando(e, cfg, trabalho, NOME)


def _montagens(cmd: list[str]) -> list[dict[str, str]]:
    montagens = []
    for i, arg in enumerate(cmd[:-1]):
        if arg == "--mount":
            campos = [c.split("=", 1) for c in cmd[i + 1].split(",")]
            montagens.append({c[0]: (c[1] if len(c) == 2 else "") for c in campos})
    return montagens


@pytest.mark.parametrize("motor", ["podman", "docker"])
@pytest.mark.parametrize("agente", ["claude", "kiro"])
def test_comando_nao_monta_home_nem_socket(tmp_path, monkeypatch, agente, motor):
    xdg = str(tmp_path / "xdg-runtime")
    monkeypatch.setenv("XDG_RUNTIME_DIR", xdg)
    origem = tmp_path / "casos" / "caso exemplo"
    e = _exec(agente=agente, caso_origem=origem, somente_leitura=True)
    if motor == "docker":
        with pytest.raises(ComandoRecusado, match="podman"):
            _cmd(e, _cfg(tmp_path, motor), tmp_path / "trabalho")
        return
    cmd = _cmd(e, _cfg(tmp_path, motor), tmp_path / "trabalho")
    casa = Path.home().resolve()
    assert "-v" not in cmd and "--volume" not in cmd
    for montagem in _montagens(cmd):
        if montagem["type"] == "bind":
            fonte = Path(montagem["src"]).resolve()
            assert fonte != casa and fonte not in casa.parents
    for arg in cmd:
        assert not any(s in arg for s in SOCKETS)
        assert xdg not in arg
    for proibido in ("--privileged", "--cap-add", "--network=host", "--net=host"):
        assert not any(a.startswith(proibido) for a in cmd)
    assert not any(cmd[i : i + 2] == ["--network", "host"] for i in range(len(cmd)))
    assert cmd[cmd.index("-w") + 1] == "/estudos"


def test_comando_endurece_o_container(tmp_path):
    cmd = _cmd(_exec(), _cfg(tmp_path), tmp_path)
    assert "--security-opt=no-new-privileges" in cmd
    assert "--cap-drop=ALL" in cmd
    assert cmd.index("--cap-drop=ALL") < cmd.index("localhost/bateria:local")
    assert all(opcao in cmd for opcao in ENDURECIMENTO)
    assert f"--pids-limit={LIMITE_PIDS}" in cmd and 0 < LIMITE_PIDS <= 4096
    assert f"--name={NOME}" in cmd
    assert cmd.index(f"--name={NOME}") < cmd.index("localhost/bateria:local")


@pytest.mark.parametrize("caminho", ["home", "raiz", "pai_da_home", "home_com_ponto_ponto"])
def test_comando_recusa_caso_na_raiz_ou_na_home(tmp_path, caminho):
    casa = Path.home()
    origem = {
        "home": casa,
        "raiz": Path(casa.anchor),
        "pai_da_home": casa.parent,
        "home_com_ponto_ponto": casa / "x" / "..",
    }[caminho]
    with pytest.raises(ComandoRecusado, match="home"):
        _cmd(_exec(caso_origem=origem, somente_leitura=True), _cfg(tmp_path), tmp_path)


def test_comando_recusa_caminho_com_virgula(tmp_path):
    origem = tmp_path / "caso,dst=x"
    with pytest.raises(ComandoRecusado, match="vírgula"):
        _cmd(_exec(caso_origem=origem, somente_leitura=True), _cfg(tmp_path), tmp_path)


def test_comando_recusa_memoria_invalida(tmp_path):
    with pytest.raises(ComandoRecusado, match="memória"):
        _cmd(_exec(), _cfg(tmp_path, memoria="muita"), tmp_path)


def test_token_do_claude_entra_so_por_secret(tmp_path):
    cfg = _cfg(tmp_path)
    cmd = _cmd(_exec(), cfg, tmp_path / "trabalho")
    segredo = cmd[cmd.index("--secret") + 1]
    assert segredo == f"{SEGREDO_CLAUDE},type=env,target=CLAUDE_CODE_OAUTH_TOKEN"
    assert "-e" not in cmd and "--env" not in cmd and "--env-file" not in cmd
    assert not any(str(cfg.token_claude) in a or "token-claude" in a for a in cmd)
    assert not any("sk-ant" in a for a in cmd)


def test_comando_do_kiro_usa_o_volume_da_config_e_nao_o_segredo_do_claude(tmp_path):
    cmd = _cmd(_exec(agente="kiro"), _cfg(tmp_path), tmp_path)
    assert _montagens(cmd) == [
        {
            "type": "volume",
            "src": "volume-kiro-teste",
            "dst": f"{HOME_AGENTE}/.local/share/kiro-cli",
        }
    ]
    assert "--secret" not in cmd
    assert cmd[-1] == "p" and "kiro-cli" in cmd[-5]
    assert "--trust-tools=" in cmd[-5] and "autoApprove" in cmd[-3]
    assert cmd[-2] == ""


def test_comando_monta_caso_somente_leitura_sem_reetiquetar(tmp_path):
    origem = (tmp_path / "casos" / "caso grande").resolve()
    cmd = _cmd(_exec(caso_origem=origem, somente_leitura=True), _cfg(tmp_path), tmp_path)
    assert _montagens(cmd) == [
        {
            "type": "bind",
            "src": str(origem),
            "dst": "/estudos/caso grande",
            "readonly": "",
        }
    ]


def test_comando_monta_a_copia_do_caso_com_espaco(tmp_path):
    trabalho = tmp_path / "trabalho"
    cmd = _cmd(_exec(caso_origem=tmp_path / "casos" / "caso T"), _cfg(tmp_path), trabalho)
    assert _montagens(cmd) == [
        {
            "type": "bind",
            "src": str(trabalho / "caso T"),
            "dst": "/estudos/caso T",
            "relabel": "private",
        }
    ]


def test_comando_sem_caso_nao_monta_nada_alem_do_volume_do_kiro(tmp_path):
    assert _montagens(_cmd(_exec(), _cfg(tmp_path), tmp_path)) == []
    assert len(_montagens(_cmd(_exec(agente="kiro"), _cfg(tmp_path), tmp_path))) == 1


@pytest.mark.parametrize("motor", ["podman", "/usr/bin/podman", "docker"])
def test_comando_usa_o_motor_da_config(tmp_path, motor):
    if Path(motor).name == "docker":
        with pytest.raises(ComandoRecusado, match=re.escape(MOTIVO_MOTOR)):
            _cmd(_exec(), _cfg(tmp_path, motor), tmp_path)
        return
    cmd = _cmd(_exec(), _cfg(tmp_path, motor), tmp_path)
    assert cmd[:4] == [motor, "run", "--rm", "-i"]
    assert "localhost/bateria:local" in cmd
    assert f"--userns=keep-id:uid={UID_AGENTE},gid={GID_AGENTE}" in cmd


def test_claude_so_com_o_mcp_do_configurar(tmp_path):
    cmd = _cmd(_exec(), _cfg(tmp_path), tmp_path)
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == f"{HOME_AGENTE}/mcp-do-configurar.json"
    assert "--permission-mode" not in cmd


PERMISSOES_AMPLAS = (
    "--permission-mode",
    "bypassPermissions",
    "--dangerously-skip-permissions",
    "--trust-all-tools",
)


def test_sem_liberar_o_claude_nao_recebe_allowed_tools(tmp_path):
    cmd = _cmd(_exec(), _cfg(tmp_path), tmp_path)
    assert "--allowedTools" not in cmd
    assert not any(a in cmd for a in PERMISSOES_AMPLAS)


@pytest.mark.parametrize("agente", ["claude", "kiro"])
def test_liberar_entra_so_com_as_tools_do_mcp_pedidas(tmp_path, agente):
    e = _exec(agente=agente, liberar=("run_start", "deck_edit_json", "run_start"))
    cmd = _cmd(e, _cfg(tmp_path), tmp_path)
    assert not any(a in cmd for a in PERMISSOES_AMPLAS)
    assert not any(any(p in a for p in PERMISSOES_AMPLAS) for a in cmd)
    if agente == "claude":
        valor = cmd[cmd.index("--allowedTools") + 1]
        assert valor == "mcp__novomodelo__run_start,mcp__novomodelo__deck_edit_json"
        assert cmd.count("--allowedTools") == 1
    else:
        assert "--allowedTools" not in cmd
        assert cmd[-2] == "run_start,deck_edit_json"
        assert cmd[-1] == "p"


def test_kiro_soma_as_liberadas_ao_auto_approve_do_configurar(tmp_path):
    cmd = _cmd(_exec(agente="kiro", liberar=("run_start",)), _cfg(tmp_path), tmp_path)
    mcp = tmp_path / "home" / ".kiro" / "settings" / "mcp.json"
    mcp.parent.mkdir(parents=True)
    mcp.write_text(
        json.dumps({"mcpServers": {"novomodelo": {"autoApprove": ["deck_list"]}}}),
        encoding="utf-8",
    )
    script = cmd[-3].replace("pathlib.Path.home()", "pathlib.Path(sys.argv[2])")
    saida = subprocess.run(
        [sys.executable, "-c", script, cmd[-2], str(tmp_path / "home")],
        capture_output=True,
        text=True,
        check=True,
    )
    assert saida.stdout.strip() == "@novomodelo/deck_list,@novomodelo/run_start"


@pytest.mark.parametrize("agente", ["claude", "kiro"])
@pytest.mark.parametrize(
    ("nome", "motivo"),
    [
        ("Bash", "inválida"),
        ("Write", "inválida"),
        ("WebFetch", "inválida"),
        ("*", "inválida"),
        ("mcp__novomodelo__run_start", "não registrada"),
        ("run_start,Bash", "inválida"),
        ("run_start; rm", "inválida"),
        ("tool_que_nao_existe", "não registrada"),
        ("instalar_novomodelo", "nunca é liberada"),
    ],
)
def test_liberar_recusa_o_que_nao_e_tool_do_mcp_liberavel(tmp_path, agente, nome, motivo):
    with pytest.raises(ComandoRecusado, match=motivo):
        _cmd(_exec(agente=agente, liberar=(nome,)), _cfg(tmp_path), tmp_path)


def test_tool_recusada_em_liberar_vira_erro_infra_sem_container(tmp_path, monkeypatch):
    chamado = []
    monkeypatch.setattr(container, "rodar_container", lambda *a, **k: chamado.append(a))
    pasta = tmp_path / "rodada"
    pasta.mkdir()
    registro = executar(
        _exec(liberar=("Bash",)),
        _cfg(tmp_path),
        pasta,
        lambda leitura: Avaliacao("passou", ""),
    )
    assert registro.estado == "erro_infra" and "inválida" in registro.motivo
    assert not chamado


def test_tools_do_servidor_marca_as_de_leitura_e_as_de_rede():
    tools = container.tools_do_servidor()
    assert tools["deck_list"] == container.AnotacoesTool(so_leitura=True, rede=False)
    assert tools["run_start"] == container.AnotacoesTool(so_leitura=False, rede=False)
    assert tools["incluir_pastas"].so_leitura is False
    assert tools["server_info"].rede is True


@pytest.mark.parametrize("agente", ["claude", "kiro"])
@pytest.mark.parametrize(
    ("anotacoes", "motivo"),
    [
        (container.AnotacoesTool(so_leitura=False, rede=True), "usa a rede"),
        (container.AnotacoesTool(so_leitura=True, rede=True), "usa a rede"),
        (container.AnotacoesTool(so_leitura=None, rede=None), "sem anotação"),
        (container.AnotacoesTool(so_leitura=False, rede=None), "sem anotação"),
        (container.AnotacoesTool(so_leitura=None, rede=False), "sem anotação"),
    ],
)
def test_liberar_recusa_tool_de_rede_ou_sem_anotacao_pelo_que_o_servidor_declara(
    tmp_path, monkeypatch, agente, anotacoes, motivo
):
    falsas = {
        **container.tools_do_servidor(),
        "tool_falsa": anotacoes,
    }
    monkeypatch.setattr(container, "tools_do_servidor", lambda: falsas)
    with pytest.raises(ComandoRecusado, match=motivo):
        _cmd(_exec(agente=agente, liberar=("tool_falsa",)), _cfg(tmp_path), tmp_path)


def test_liberar_aceita_tool_falsa_anotada_que_grava_sem_rede(tmp_path, monkeypatch):
    falsas = {"tool_falsa": container.AnotacoesTool(so_leitura=False, rede=False)}
    monkeypatch.setattr(container, "tools_do_servidor", lambda: falsas)
    cmd = _cmd(_exec(liberar=("tool_falsa",)), _cfg(tmp_path), tmp_path)
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__novomodelo__tool_falsa"


@pytest.mark.parametrize("memoria", ["6g", "3g"])
def test_cada_container_tem_o_teto_de_memoria_da_config(tmp_path, memoria):
    cmd = _cmd(_exec(), _cfg(tmp_path, memoria=memoria), tmp_path)
    assert f"--memory={memoria}" in cmd and f"--memory-swap={memoria}" in cmd


def test_nome_do_container_e_seguro_e_unico():
    e = _exec(caso="caso.x", config="v-1", repeticao=3)
    a, b = nome_container(e, "rodada 1/../x"), nome_container(e, "rodada 1/../x")
    assert a != b
    for nome in (a, b):
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", nome)
        assert "caso.x" in nome and "claude" in nome and "-3-" in nome


def test_limite_de_uso_e_reconhecido_e_resposta_comum_nao():
    lim = [
        json.dumps(
            {
                "t": 1,
                "evento": {
                    "type": "result",
                    "is_error": True,
                    "result": "Claude AI usage limit reached|1792900000",
                },
            }
        )
    ]
    assert limite_atingido(lim, "")
    assert limite_atingido([], "Error: 429 Too Many Requests")
    ok = [
        json.dumps(
            {
                "t": 1,
                "evento": {"type": "result", "is_error": False, "result": "o limite superior caiu"},
            }
        )
    ]
    assert not limite_atingido(ok, "")


def test_rodar_container_embrulha_as_linhas_json_e_guarda_o_resto():
    script = "import json;print(json.dumps({'type':'x'}));print('texto solto')"
    saida = rodar_container([sys.executable, "-c", script], 30)
    assert not saida.estourou and saida.codigo == 0
    primeira = json.loads(saida.linhas[0])
    assert primeira["evento"] == {"type": "x"} and primeira["t"] >= 0
    assert saida.linhas[1].strip() == "texto solto"


def test_rodar_container_vigia_mata_o_processo_parado():
    saida = rodar_container([sys.executable, "-c", "import time;time.sleep(60)"], 1)
    assert saida.estourou and saida.codigo != 0


def test_rodar_container_sem_o_executavel_levanta_motor_ausente(tmp_path):
    with pytest.raises(MotorAusente):
        rodar_container([str(tmp_path / "motor-que-nao-existe")], 5)


def _falso(monkeypatch, saida: Saida | BaseException):
    chamadas: list[list[str]] = []

    def rodar(cmd, timeout_s):
        chamadas.append(cmd)
        if isinstance(saida, BaseException):
            raise saida
        return saida

    monkeypatch.setattr(container, "rodar_container", rodar)
    return chamadas


@pytest.fixture
def remocoes(monkeypatch):
    feitas: list[list[str]] = []

    def run(cmd, **kwargs):
        feitas.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(container.subprocess, "run", run)
    return feitas


def _avaliar_passou(leitura: Leitura):
    return Avaliacao("passou", "ok")


def _stream(nome: str) -> list[str]:
    return (FIX / nome).read_text(encoding="utf-8").splitlines()


def _pasta(tmp_path: Path) -> Path:
    return tmp_path / "resultados" / "rodada-1"


def _destino(tmp_path: Path, e: Execucao) -> Path:
    return _pasta(tmp_path) / "execucoes" / e.conjunto / e.caso / e.agente / e.config / "1"


def _nome_usado(cmd: list[str]) -> str:
    return next(a for a in cmd if a.startswith("--name=")).removeprefix("--name=")


def _remocao(cmd: list[str]) -> list[str]:
    return ["podman", "rm", "-f", "--ignore", _nome_usado(cmd)]


def test_estouro_vira_erro_infra_e_remove_o_container(tmp_path, monkeypatch, remocoes):
    chamadas = _falso(
        monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl")[:3], "", -9, True)
    )
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "tempo" in r.motivo
    assert ler_registros(_pasta(tmp_path)) == [r]
    assert remocoes == [_remocao(chamadas[0])]


def test_falha_no_meio_da_leitura_remove_o_container(tmp_path, monkeypatch, remocoes):
    chamadas = _falso(monkeypatch, RuntimeError("leitura interrompida"))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "leitura interrompida" in r.motivo
    assert remocoes == [_remocao(chamadas[0])]


def test_execucao_normal_tambem_remove_o_container(tmp_path, monkeypatch, remocoes):
    chamadas = _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))
    assert executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou).estado == "passou"
    assert remocoes == [_remocao(chamadas[0])]
    stderr = (_destino(tmp_path, _exec()) / "stderr.txt").read_text(encoding="utf-8")
    assert "não confirmado" not in stderr


def _remocao_falha(monkeypatch, modo: str) -> None:
    def run(cmd, **kwargs):
        if modo == "estouro":
            raise subprocess.TimeoutExpired(cmd, 30)
        if modo == "sem_motor":
            raise FileNotFoundError(cmd[0])
        return SimpleNamespace(returncode=125)

    monkeypatch.setattr(container.subprocess, "run", run)


@pytest.mark.parametrize("modo", ["codigo", "estouro", "sem_motor"])
def test_remocao_nao_confirmada_vai_para_o_stderr(tmp_path, monkeypatch, modo):
    chamadas = _falso(
        monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), f"x {TOKEN_FALSO}", 0, False)
    )
    _remocao_falha(monkeypatch, modo)
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    stderr = (_destino(tmp_path, _exec()) / "stderr.txt").read_text(encoding="utf-8")
    assert f"container {_nome_usado(chamadas[0])} não confirmado como removido" in stderr
    assert TOKEN_FALSO not in stderr and r.estado == "passou"


def test_comando_recusado_nao_chama_remocao(tmp_path, monkeypatch, remocoes):
    _falso(monkeypatch, Saida([], "", 0, False))
    executar(_exec(caso_origem=Path.home()), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert remocoes == []


def test_limite_de_uso_vira_erro_infra(tmp_path, monkeypatch, remocoes):
    linhas = [
        json.dumps(
            {
                "t": 1,
                "evento": {"type": "result", "is_error": True, "result": "usage limit reached"},
            }
        )
    ]
    _falso(monkeypatch, Saida(linhas, "", 1, False))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "limite" in r.motivo


def test_motor_ausente_vira_erro_infra(tmp_path, monkeypatch, remocoes):
    _falso(monkeypatch, MotorAusente("podman"))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and r.motivo == "motor de container ausente: podman"
    assert (_destino(tmp_path, _exec()) / "registro.json").is_file()
    assert remocoes == []


def test_outro_arquivo_ausente_nao_vira_motor_ausente(tmp_path, monkeypatch, remocoes):
    _falso(monkeypatch, FileNotFoundError(2, "No such file", str(tmp_path / "x")))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "motor" not in r.motivo


@pytest.mark.parametrize("agente", ["claude", "kiro"])
def test_motor_que_nao_e_podman_vira_erro_infra_sem_montar_comando(tmp_path, monkeypatch, agente):
    chamadas = _falso(monkeypatch, Saida([], "", 0, False))
    montados: list[Execucao] = []
    original = container.comando
    monkeypatch.setattr(container, "comando", lambda e, *a: montados.append(e) or original(e, *a))
    r = executar(_exec(agente=agente), _cfg(tmp_path, "docker"), _pasta(tmp_path), _avaliar_passou)
    assert (r.estado, r.motivo) == ("erro_infra", MOTIVO_MOTOR)
    assert chamadas == [] and montados == []
    assert ler_registros(_pasta(tmp_path)) == [r]


def test_caso_ausente_vira_erro_infra_com_o_nome_logico(tmp_path, monkeypatch):
    chamadas = _falso(monkeypatch, Saida([], "", 0, False))
    origem = tmp_path / "casos" / "nao-existe"
    r = executar(_exec(caso_origem=origem), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert (r.estado, r.motivo) == ("erro_infra", "caso indisponível: caso-exemplo")
    assert chamadas == []


def test_caso_na_home_vira_erro_infra_sem_copiar(tmp_path, monkeypatch):
    chamadas = _falso(monkeypatch, Saida([], "", 0, False))
    copias: list[object] = []
    monkeypatch.setattr(container.shutil, "copytree", lambda *a, **k: copias.append(a))
    r = executar(_exec(caso_origem=Path.home()), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "home" in r.motivo
    assert chamadas == [] and copias == []


@pytest.mark.parametrize("onde", ["rodar", "avaliar"])
def test_motivo_nunca_grava_caminho_do_host(tmp_path, monkeypatch, onde):
    caminho = str(tmp_path / "pasta secreta" / "arquivo.json")
    erro = OSError(13, "Permission denied", caminho)
    if onde == "rodar":
        _falso(monkeypatch, RuntimeError(f"falhou ao abrir {caminho} e {Path.home()}"))
        avaliar = _avaliar_passou
    else:
        _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))

        def avaliar(leitura):
            raise erro

    monkeypatch.setattr(container.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), avaliar)
    gravado = (_destino(tmp_path, _exec()) / "registro.json").read_text(encoding="utf-8")
    for texto in (r.motivo, gravado):
        assert str(tmp_path) not in texto and "pasta secreta" not in texto
        assert str(Path.home()) not in texto
    assert r.estado == "erro_infra"


def test_codigo_nao_zero_sem_evento_de_fim_vira_erro_infra(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl")[:4], "falhou", 125, False))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "125" in r.motivo


def test_excecao_de_avaliar_vira_erro_infra(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))

    def avaliar(leitura):
        raise RuntimeError("juiz sem resposta")

    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), avaliar)
    assert r.estado == "erro_infra" and "juiz sem resposta" in r.motivo


def test_estado_vem_de_avaliar_com_a_leitura_do_agente(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("kiro-stream-sintetico.jsonl"), "", 0, False))
    vistos: list[Leitura] = []

    def avaliar(leitura):
        vistos.append(leitura)
        return Avaliacao("falhou", "tool esperada não chamada")

    e = _exec(agente="kiro")
    r = executar(e, _cfg(tmp_path), _pasta(tmp_path), avaliar)
    assert (r.estado, r.motivo) == ("falhou", "tool esperada não chamada")
    assert vistos[0].eventos[-1].tipo == "fim"
    assert (r.rodada, r.agente, r.repeticao) == ("rodada-1", "kiro", 1)


def _stream_com_token() -> list[str]:
    return [
        json.dumps(
            {
                "t": 1.0,
                "evento": {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": f"eco {TOKEN_FALSO}"}]},
                },
            }
        ),
        json.dumps(
            {"t": 2.0, "evento": {"type": "result", "result": f"fim {TOKEN_FALSO}", "usage": {}}}
        ),
    ]


@pytest.mark.parametrize("estourou", [False, True])
def test_logs_gravados_mascarados(tmp_path, monkeypatch, remocoes, estourou):
    cfg = _cfg(tmp_path)
    cfg.token_claude.parent.mkdir(parents=True)
    cfg.token_claude.write_text("valor-literal-do-token-falso\n", encoding="utf-8")
    _falso(
        monkeypatch,
        Saida(
            [*_stream_com_token(), "texto valor-literal-do-token-falso"],
            f"stderr {TOKEN_FALSO}",
            -9 if estourou else 0,
            estourou,
        ),
    )
    executar(_exec(), cfg, _pasta(tmp_path), _avaliar_passou)
    destino = _destino(tmp_path, _exec())
    for nome in ("log.jsonl", "stderr.txt", "resposta.md"):
        texto = (destino / nome).read_text(encoding="utf-8")
        assert TOKEN_FALSO not in texto and "valor-literal-do-token-falso" not in texto
        assert "***" in texto
    assert not list(_pasta(tmp_path).glob(".trabalho-*"))


def test_registro_tem_as_tools_chamadas_com_o_status_do_envelope(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert [(t.nome, t.ok) for t in r.tools] == [("server_info", True), ("case_validate", False)]
    assert all(t.duracao_s == 0.5 for t in r.tools)
    assert r.estado == "passou" and r.duracao_s >= 0


def _uso_e_resultado(conteudo: str, is_error: bool) -> list[str]:
    return [
        json.dumps(
            {
                "t": 1.0,
                "evento": {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "tool_use", "id": "u", "name": "mcp__novomodelo__deck_list"}
                        ]
                    },
                },
            }
        ),
        json.dumps(
            {
                "t": 1.25,
                "evento": {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "u",
                                "is_error": is_error,
                                "content": conteudo,
                            }
                        ]
                    },
                },
            }
        ),
        json.dumps({"t": 2.0, "evento": {"type": "result", "result": "ok", "usage": {}}}),
    ]


@pytest.mark.parametrize(
    ("conteudo", "is_error", "ok"),
    [
        ('{"status": "ok"}', False, True),
        ('{"status": "error", "exit_code": 1}', False, False),
        ('{"status": "ok"}', True, False),
        ("texto que não é JSON", False, None),
        ('["lista", "sem", "status"]', False, None),
    ],
)
def test_ok_da_tool_vem_do_status_do_envelope(tmp_path, monkeypatch, conteudo, is_error, ok):
    _falso(monkeypatch, Saida(_uso_e_resultado(conteudo, is_error), "", 0, False))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert [(t.nome, t.ok, t.duracao_s) for t in r.tools] == [("deck_list", ok, 0.25)]


def test_registro_marca_negacao_como_nao_ok_e_sem_resultado_como_nulo(tmp_path, monkeypatch):
    linhas = _stream("kiro-stream-sintetico.jsonl")
    sem_fim_de_solver = [ln for ln in linhas if '"k5", "kind"' not in ln]
    _falso(monkeypatch, Saida(sem_fim_de_solver, "", 0, False))
    r = executar(_exec(agente="kiro"), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert [(t.nome, t.ok) for t in r.tools] == [
        ("server_info", False),
        ("solver_version", None),
        ("case_validate", False),
    ]
    assert r.tools[1].duracao_s is None


def test_caso_copiado_para_o_trabalho_e_apagado_no_fim(tmp_path, monkeypatch):
    origem = tmp_path / "casos" / "caso-exemplo"
    origem.mkdir(parents=True)
    (origem / "config.json").write_text("{}", encoding="utf-8")
    vistos: list[bool] = []

    def rodar(cmd, timeout_s):
        [montagem] = _montagens(cmd)
        assert montagem["dst"] == "/estudos/caso-exemplo" and "readonly" not in montagem
        vistos.append((Path(montagem["src"]) / "config.json").is_file())
        return Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False)

    monkeypatch.setattr(container, "rodar_container", rodar)
    r = executar(_exec(caso_origem=origem), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert vistos == [True] and r.estado == "passou"
    assert not list(_pasta(tmp_path).glob(".trabalho-*"))
    assert (origem / "config.json").is_file()


def _link_ou_pula(link: Path, alvo: Path) -> None:
    try:
        link.symlink_to(alvo, target_is_directory=alvo.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("o sistema não deixa criar link simbólico")


def test_copia_do_caso_mantem_links_sem_seguir(tmp_path, monkeypatch):
    fora = tmp_path / "fora-do-caso"
    fora.mkdir()
    (fora / "segredo.txt").write_text("conteudo de fora", encoding="utf-8")
    origem = tmp_path / "casos" / "caso-exemplo"
    origem.mkdir(parents=True)
    (origem / "config.json").write_text("{}", encoding="utf-8")
    _link_ou_pula(origem / "atalho.txt", fora / "segredo.txt")
    vistos: list[tuple[bool, bool]] = []

    def rodar(cmd, timeout_s):
        copia = Path(_montagens(cmd)[0]["src"])
        vistos.append(((copia / "atalho.txt").is_symlink(), (copia / "config.json").is_file()))
        return Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False)

    monkeypatch.setattr(container, "rodar_container", rodar)
    monkeypatch.setattr(container.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    executar(_exec(caso_origem=origem), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert vistos == [(True, True)]


def test_comando_monta_o_caminho_resolvido_de_um_caso_que_e_link(tmp_path):
    real = tmp_path / "casos-reais" / "caso-real"
    real.mkdir(parents=True)
    link = tmp_path / "caso-link"
    _link_ou_pula(link, real)
    cmd = _cmd(_exec(caso_origem=link, somente_leitura=True), _cfg(tmp_path), tmp_path)
    [montagem] = _montagens(cmd)
    assert montagem["src"] == str(real.resolve()) and montagem["dst"] == "/estudos/caso-link"


def test_executar_copia_e_monta_pelo_mesmo_caminho_resolvido(tmp_path, monkeypatch):
    real = tmp_path / "casos-reais" / "caso-real"
    real.mkdir(parents=True)
    (real / "config.json").write_text("{}", encoding="utf-8")
    link = tmp_path / "caso-link"
    _link_ou_pula(link, real)
    copiados: list[Path] = []
    original = container.shutil.copytree

    def copiar(fonte, destino, **k):
        copiados.append(Path(fonte))
        assert k.get("symlinks") is True
        return original(fonte, destino, **k)

    monkeypatch.setattr(container.shutil, "copytree", copiar)
    monkeypatch.setattr(container.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))
    executar(_exec(caso_origem=link), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert copiados == [real.resolve()]


def test_guard_protege_a_home_do_ambiente(tmp_path, monkeypatch):
    outra = tmp_path / "outra-home"
    outra.mkdir()
    monkeypatch.setenv("HOME", str(outra))
    monkeypatch.setenv("USERPROFILE", str(outra))
    assert Path.home() == outra
    with pytest.raises(ComandoRecusado, match="home"):
        _cmd(_exec(caso_origem=outra, somente_leitura=True), _cfg(tmp_path), tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="pwd só existe fora do Windows")
def test_guard_protege_a_home_da_conta_mesmo_com_home_trocado(tmp_path, monkeypatch):
    import pwd

    da_conta = Path(pwd.getpwuid(os.getuid()).pw_dir)
    monkeypatch.setenv("HOME", str(tmp_path / "outra-home"))
    assert Path.home() != da_conta
    with pytest.raises(ComandoRecusado, match="home"):
        _cmd(_exec(caso_origem=da_conta, somente_leitura=True), _cfg(tmp_path), tmp_path)


@pytest.mark.parametrize(
    ("texto", "vazado"),
    [
        ("falhou em /dados/pasta com espaço/arquivo.json final", ("pasta", "espaço", "arquivo")),
        ("PATH=a:/opt/ferramenta/bin:/usr/local/bin", ("/opt/ferramenta", "/usr/local")),
        (r"falhou em C:\dados\outra pasta\x.json final", ("dados", "outra", "x.json")),
        ("falhou em '/dados/nome com espaço' e mais", ("dados", "espaço")),
    ],
)
def test_sem_caminhos_trata_espaco_e_dois_pontos(texto, vazado):
    limpo = sem_caminhos(texto)
    assert "<caminho>" in limpo
    assert not any(v in limpo for v in vazado)


def test_sem_caminhos_preserva_url_e_texto_comum():
    texto = "erro 429 em https://exemplo.invalid/api: tente de novo"
    assert sem_caminhos(texto) == texto


def _gravado(tmp_path: Path, e: Execucao) -> dict:
    return json.loads((_destino(tmp_path, e) / "registro.json").read_text(encoding="utf-8"))


def test_executar_grava_os_tokens_do_stream_do_claude(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert (r.metricas.tokens_entrada, r.metricas.tokens_saida) == (60, r.metricas.tokens_saida)
    assert r.metricas.tokens_saida and r.metricas.tokens_saida > 0
    gravado = _gravado(tmp_path, _exec())["metricas"]
    assert gravado["tokens_entrada"] == 60 and gravado["nota_juiz"] is None


def test_kiro_sem_tokens_no_stream_fica_nulo(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("kiro-stream-sintetico.jsonl"), "", 0, False))
    r = executar(_exec(agente="kiro"), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.metricas == Metricas()


def test_metricas_de_avaliar_chegam_ao_registro_sem_perder_os_tokens(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))

    def avaliar(leitura):
        return Avaliacao("passou", "ok", Metricas(acerto_tool=True, nota_juiz=2, contornos=1))

    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), avaliar)
    gravado = _gravado(tmp_path, _exec())["metricas"]
    assert (gravado["acerto_tool"], gravado["nota_juiz"], gravado["contornos"]) == (True, 2, 1)
    assert gravado["tokens_entrada"] == 60 == r.metricas.tokens_entrada


def test_avaliar_que_informa_tokens_nao_e_sobrescrito(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))

    def avaliar(leitura):
        return Avaliacao("passou", "ok", Metricas(tokens_entrada=7))

    assert executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), avaliar).metricas.tokens_entrada == 7


def test_erro_infra_mantem_os_tokens_e_deixa_o_resto_nulo(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))

    def avaliar(leitura):
        raise RuntimeError("juiz sem resposta")

    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), avaliar)
    assert r.estado == "erro_infra"
    assert r.metricas == Metricas(tokens_entrada=60, tokens_saida=r.metricas.tokens_saida)
    assert r.metricas.tokens_saida


def test_erro_infra_sem_leitura_tem_metricas_vazias(tmp_path, monkeypatch):
    _falso(monkeypatch, FileNotFoundError("podman"))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and r.metricas == Metricas()


def test_avaliar_recebe_a_leitura_mascarada(tmp_path, monkeypatch, remocoes):
    cfg = _cfg(tmp_path)
    cfg.token_claude.parent.mkdir(parents=True)
    cfg.token_claude.write_text("valor-literal-do-token-falso\n", encoding="utf-8")
    linha = json.dumps(
        {"t": 1.5, "evento": {"type": "result", "result": "eco valor-literal-do-token-falso"}}
    )
    _falso(monkeypatch, Saida([*_stream_com_token(), linha], "", 0, False))
    recebidas: list[Leitura] = []

    def avaliar(leitura: Leitura) -> Avaliacao:
        recebidas.append(leitura)
        return Avaliacao("passou", "ok")

    executar(_exec(), cfg, _pasta(tmp_path), avaliar)
    [leitura] = recebidas
    texto = json.dumps([(ev.args, ev.dados) for ev in leitura.eventos], ensure_ascii=False)
    assert TOKEN_FALSO not in texto and "valor-literal-do-token-falso" not in texto
    assert "***" in texto


def test_caso_do_c08_montado_em_montar_em_com_o_nome_logico(tmp_path):
    origem = tmp_path / "preparados" / "exemplo_1dtoy"
    e = _exec(caso_origem=origem, montar_em="/mnt/outros")
    [montagem] = _montagens(_cmd(e, _cfg(tmp_path), tmp_path / "trabalho"))
    assert montagem["dst"] == "/mnt/outros/exemplo_1dtoy"
    assert montagem["src"] == str(tmp_path / "trabalho" / "exemplo_1dtoy")
    [padrao] = _montagens(_cmd(_exec(caso_origem=origem), _cfg(tmp_path), tmp_path / "t"))
    assert padrao["dst"] == "/estudos/exemplo_1dtoy"


@pytest.mark.parametrize("destino", ["relativo", "/mnt/../etc", "/mnt/a b", "/"])
def test_montar_em_invalido_e_recusado(tmp_path, destino):
    e = _exec(caso_origem=tmp_path / "casos" / "c", montar_em=destino)
    with pytest.raises(ComandoRecusado, match="destino"):
        _cmd(e, _cfg(tmp_path), tmp_path)


def test_sem_output_copia_o_caso_sem_as_pastas_de_saida(tmp_path, monkeypatch):
    caso = tmp_path / "casos" / "v18"
    (caso / "output" / "simulation").mkdir(parents=True)
    (caso / "output-2").mkdir()
    (caso / "system").mkdir()
    (caso / "config.json").write_text("{}", encoding="utf-8")
    copiados: list[list[str]] = []

    def rodar(cmd, timeout_s):
        [montagem] = _montagens(cmd)
        copiados.append(sorted(p.name for p in Path(montagem["src"]).iterdir()))
        return Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False)

    monkeypatch.setattr(container, "rodar_container", rodar)
    monkeypatch.setattr(container.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    for sem_output, esperado in ((True, ["config.json", "system"]), (False, None)):
        e = _exec(caso_origem=caso, sem_output=sem_output, repeticao=1 if sem_output else 2)
        executar(e, _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
        if esperado is not None:
            assert copiados[-1] == esperado
    assert copiados[-1] == ["config.json", "output", "output-2", "system"]
