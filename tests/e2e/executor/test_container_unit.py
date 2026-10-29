"""Comando do container, laço de leitura e registro de uma execução."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.e2e.config import Config
from tests.e2e.executor import container
from tests.e2e.executor.container import (
    HOME_AGENTE,
    SEGREDO_CLAUDE,
    Execucao,
    Saida,
    comando,
    executar,
    limite_atingido,
    rodar_container,
)
from tests.e2e.executor.eventos import Leitura
from tests.e2e.resultado.armazenamento import ler_registros

FIX = Path(__file__).parent / "fixtures"
TOKEN_FALSO = "sk-ant-teste-000000000000"
SOCKETS = ("/run/podman", "/var/run/docker.sock", "docker.sock", "podman.sock")


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


def _cfg(tmp_path: Path, motor: str = "podman") -> Config:
    return Config(
        motor=motor,
        resultados=tmp_path / "resultados",
        casos=None,
        cenarios_extra=None,
        token_claude=tmp_path / "segredos" / "token-claude",
        volume_kiro="volume-kiro-teste",
        cache=tmp_path / "cache",
    )


def _montagens(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, a in enumerate(cmd[:-1]) if a in ("-v", "--volume", "--mount")]


def _fonte(montagem: str) -> str:
    return montagem.rsplit(":", 2)[0] if montagem.count(":") >= 2 else montagem.split(":")[0]


@pytest.mark.parametrize("agente", ["claude", "kiro"])
def test_comando_nao_monta_home_nem_socket(tmp_path, monkeypatch, agente):
    xdg = str(tmp_path / "xdg-runtime")
    monkeypatch.setenv("XDG_RUNTIME_DIR", xdg)
    origem = tmp_path / "casos" / "caso exemplo"
    cmd = comando(
        _exec(agente=agente, caso_origem=origem, somente_leitura=True),
        _cfg(tmp_path),
        tmp_path / "trabalho",
    )
    casa = str(Path.home())
    for montagem in _montagens(cmd):
        fonte = _fonte(montagem)
        assert fonte != casa and not casa.startswith(fonte.rstrip("/\\") + "/")
    for arg in cmd:
        assert not any(s in arg for s in SOCKETS)
        assert xdg not in arg
    for proibido in ("--privileged", "--cap-add", "--network=host", "--net=host"):
        assert not any(a.startswith(proibido) for a in cmd)
    assert not any(cmd[i : i + 2] == ["--network", "host"] for i in range(len(cmd)))
    assert cmd[cmd.index("-w") + 1] == "/estudos"


def test_token_do_claude_entra_so_por_secret(tmp_path):
    cfg = _cfg(tmp_path)
    cmd = comando(_exec(), cfg, tmp_path / "trabalho")
    segredo = cmd[cmd.index("--secret") + 1]
    assert segredo == f"{SEGREDO_CLAUDE},type=env,target=CLAUDE_CODE_OAUTH_TOKEN"
    assert "-e" not in cmd and "--env" not in cmd and "--env-file" not in cmd
    assert not any(str(cfg.token_claude) in a or "token-claude" in a for a in cmd)
    assert not any("sk-ant" in a for a in cmd)


def test_comando_do_kiro_usa_o_volume_da_config_e_nao_o_segredo_do_claude(tmp_path):
    cmd = comando(_exec(agente="kiro"), _cfg(tmp_path), tmp_path)
    assert f"volume-kiro-teste:{HOME_AGENTE}/.local/share/kiro-cli" in cmd
    assert "--secret" not in cmd
    assert cmd[-1] == "p" and "kiro-cli" in cmd[-4]
    assert "--trust-tools=" in cmd[-4] and "autoApprove" in cmd[-2]


def test_comando_monta_caso_somente_leitura(tmp_path):
    origem = tmp_path / "casos" / "caso grande"
    cmd = comando(_exec(caso_origem=origem, somente_leitura=True), _cfg(tmp_path), tmp_path)
    assert f"{origem}:/estudos/caso grande:ro,z" in cmd


def test_comando_monta_a_copia_do_caso_com_espaco(tmp_path):
    trabalho = tmp_path / "trabalho"
    cmd = comando(_exec(caso_origem=tmp_path / "casos" / "caso T"), _cfg(tmp_path), trabalho)
    assert f"{trabalho / 'caso T'}:/estudos/caso T:Z" in cmd
    assert not any(a.endswith(":ro,z") for a in cmd)


def test_comando_sem_caso_nao_monta_nada_alem_do_volume_do_kiro(tmp_path):
    assert _montagens(comando(_exec(), _cfg(tmp_path), tmp_path)) == []
    assert len(_montagens(comando(_exec(agente="kiro"), _cfg(tmp_path), tmp_path))) == 1


@pytest.mark.parametrize("motor", ["podman", "docker"])
def test_comando_usa_o_motor_da_config(tmp_path, motor):
    cmd = comando(_exec(), _cfg(tmp_path, motor), tmp_path)
    assert cmd[:4] == [motor, "run", "--rm", "-i"]
    assert "localhost/bateria:local" in cmd
    assert ("--userns=keep-id" in cmd) == (motor == "podman")


def test_claude_so_com_o_mcp_do_configurar(tmp_path):
    cmd = comando(_exec(), _cfg(tmp_path), tmp_path)
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == f"{HOME_AGENTE}/mcp-do-configurar.json"
    assert "--permission-mode" not in cmd


def test_cada_container_tem_teto_de_memoria(tmp_path):
    cmd = comando(_exec(), _cfg(tmp_path), tmp_path)
    assert "--memory=6g" in cmd and "--memory-swap=6g" in cmd


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


def _falso(monkeypatch, saida: Saida | Exception):
    chamadas: list[list[str]] = []

    def rodar(cmd, timeout_s):
        chamadas.append(cmd)
        if isinstance(saida, Exception):
            raise saida
        return saida

    monkeypatch.setattr(container, "rodar_container", rodar)
    return chamadas


def _avaliar_passou(leitura: Leitura):
    return "passou", "ok"


def _stream(nome: str) -> list[str]:
    return (FIX / nome).read_text(encoding="utf-8").splitlines()


def _pasta(tmp_path: Path) -> Path:
    return tmp_path / "resultados" / "rodada-1"


def _destino(tmp_path: Path, e: Execucao) -> Path:
    return _pasta(tmp_path) / "execucoes" / e.conjunto / e.caso / e.agente / e.config / "1"


def test_estouro_vira_erro_infra(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl")[:3], "", -9, True))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "tempo" in r.motivo
    assert ler_registros(_pasta(tmp_path)) == [r]


def test_limite_de_uso_vira_erro_infra(tmp_path, monkeypatch):
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


def test_motor_ausente_vira_erro_infra(tmp_path, monkeypatch):
    _falso(monkeypatch, FileNotFoundError("podman"))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert r.estado == "erro_infra" and "motor" in r.motivo
    assert (_destino(tmp_path, _exec()) / "registro.json").is_file()


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
def test_logs_gravados_mascarados(tmp_path, monkeypatch, estourou):
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


def test_registro_tem_as_tools_chamadas(tmp_path, monkeypatch):
    _falso(monkeypatch, Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False))
    r = executar(_exec(), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert [(t.nome, t.ok) for t in r.tools] == [("server_info", True), ("case_validate", False)]
    assert all(t.duracao_s == 0.5 for t in r.tools)
    assert r.estado == "passou" and r.duracao_s >= 0


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
        montagem = next(a for a in cmd if a.endswith(":/estudos/caso-exemplo:Z"))
        vistos.append((Path(montagem.rsplit(":", 2)[0]) / "config.json").is_file())
        return Saida(_stream("claude-stream-sintetico.jsonl"), "", 0, False)

    monkeypatch.setattr(container, "rodar_container", rodar)
    r = executar(_exec(caso_origem=origem), _cfg(tmp_path), _pasta(tmp_path), _avaliar_passou)
    assert vistos == [True] and r.estado == "passou"
    assert not list(_pasta(tmp_path).glob(".trabalho-*"))
    assert (origem / "config.json").is_file()
