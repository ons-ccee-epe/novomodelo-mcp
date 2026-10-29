"""Comando do container, laço de leitura e registro de uma execução."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from tests.e2e.config import MOTIVO_MOTOR, Config
from tests.e2e.executor import container
from tests.e2e.executor.container import (
    HOME_AGENTE,
    LIMITE_PIDS,
    SEGREDO_CLAUDE,
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
    assert cmd[-1] == "p" and "kiro-cli" in cmd[-4]
    assert "--trust-tools=" in cmd[-4] and "autoApprove" in cmd[-2]


def test_comando_monta_caso_somente_leitura(tmp_path):
    origem = tmp_path / "casos" / "caso grande"
    cmd = _cmd(_exec(caso_origem=origem, somente_leitura=True), _cfg(tmp_path), tmp_path)
    assert _montagens(cmd) == [
        {
            "type": "bind",
            "src": str(origem),
            "dst": "/estudos/caso grande",
            "readonly": "",
            "relabel": "shared",
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
    assert "localhost/bateria:local" in cmd and "--userns=keep-id" in cmd


def test_claude_so_com_o_mcp_do_configurar(tmp_path):
    cmd = _cmd(_exec(), _cfg(tmp_path), tmp_path)
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == f"{HOME_AGENTE}/mcp-do-configurar.json"
    assert "--permission-mode" not in cmd


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
        return None

    monkeypatch.setattr(container.subprocess, "run", run)
    return feitas


def _avaliar_passou(leitura: Leitura):
    return "passou", "ok"


def _stream(nome: str) -> list[str]:
    return (FIX / nome).read_text(encoding="utf-8").splitlines()


def _pasta(tmp_path: Path) -> Path:
    return tmp_path / "resultados" / "rodada-1"


def _destino(tmp_path: Path, e: Execucao) -> Path:
    return _pasta(tmp_path) / "execucoes" / e.conjunto / e.caso / e.agente / e.config / "1"


def _nome_usado(cmd: list[str]) -> str:
    return next(a for a in cmd if a.startswith("--name=")).removeprefix("--name=")


def test_estouro_vira_erro_infra_e_remove_o_container(tmp_path, monkeypatch, remocoes):
    chamadas = _falso(
        monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl")[:3], "", -9, True)
    )
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "tempo" in r.motivo
    assert ler_registros(_pasta(tmp_path)) == [r]
    assert remocoes == [["podman", "rm", "-f", _nome_usado(chamadas[0])]]


def test_falha_no_meio_da_leitura_remove_o_container(tmp_path, monkeypatch, remocoes):
    chamadas = _falso(monkeypatch, RuntimeError("leitura interrompida"))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "leitura interrompida" in r.motivo
    assert remocoes == [["podman", "rm", "-f", _nome_usado(chamadas[0])]]


def test_execucao_normal_nao_chama_remocao(tmp_path, monkeypatch, remocoes):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))
    assert executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou).estado == "passou"
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

    monkeypatch.setattr(container.subprocess, "run", lambda *a, **k: None)
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
        return "falhou", "tool esperada não chamada"

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
