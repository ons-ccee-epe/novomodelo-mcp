"""Imagens por configuração do MCP e secret do token, com um motor falso."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.config import MOTIVO_MOTOR, Config
from tests.e2e.executor import imagens
from tests.e2e.executor.container import HOME_AGENTE, PASTA_ESTUDOS, SEGREDO_CLAUDE
from tests.e2e.executor.imagens import (
    CLAUDE_CODE_VERSAO,
    ConfigMCP,
    FalhaPreparo,
    construir,
    criar_segredo,
    ler_config_mcp,
    tag_imagem,
    versoes_fixadas,
)

TOKEN_FALSO = "sk-ant-teste-000000000000"
NOVOMODELO = "9.8.7"
WHEEL = "novomodelo_mcp-1.2.3-py3-none-any.whl"


def _cfg(tmp_path: Path, motor: str = "podman") -> Config:
    return Config(
        motor=motor,
        resultados=tmp_path / "resultados",
        casos=None,
        cenarios_extra=None,
        token_claude=tmp_path / "token",
        volume_kiro="vol",
        cache=tmp_path / "cache",
    )


def _wheel(tmp_path: Path, nome: str = WHEEL) -> Path:
    arquivo = tmp_path / nome
    arquivo.write_bytes(b"wheel falsa")
    return arquivo


class MotorFalso:
    def __init__(
        self, versoes: dict[str, str] | None = None, codigo_build: int = 0, existe: int = 1
    ) -> None:
        self.chamadas: list[tuple[list[str], dict]] = []
        self.versoes = versoes
        self.codigo_build = codigo_build
        self.existe = existe
        self.contexto: list[str] = []

    def __call__(self, cmd, **kwargs):
        self.chamadas.append((list(cmd), kwargs))
        if cmd[1] == "build":
            self.contexto = sorted(
                p.relative_to(cmd[-1]).as_posix() for p in Path(cmd[-1]).rglob("*")
            )
            return subprocess.CompletedProcess(cmd, self.codigo_build, "", "")
        if cmd[1:3] == ["secret", "exists"]:
            return subprocess.CompletedProcess(cmd, self.existe, "", "")
        return subprocess.CompletedProcess(cmd, 0, json.dumps(self.versoes or {}), "")


def _build_args(cmd: list[str]) -> dict[str, str]:
    pares = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--build-arg"]
    return dict(p.split("=", 1) for p in pares)


@pytest.fixture(autouse=True)
def _versao_esperada(monkeypatch):
    monkeypatch.setattr(imagens, "expected_version", lambda: NOVOMODELO)


def test_config_mcp_sem_e_wheel(tmp_path):
    assert ler_config_mcp("sem") == ConfigMCP("sem-mcp", None)
    wheel = _wheel(tmp_path)
    assert ler_config_mcp(str(wheel)) == ConfigMCP("mcp-1.2.3", wheel.resolve())


@pytest.mark.parametrize(
    "nome", ["novomodelo_mcp-1.2.3.tar.gz", "outro_pacote-1.2.3-py3-none-any.whl", "x.whl"]
)
def test_config_mcp_recusa_o_que_nao_e_wheel_do_mcp(tmp_path, nome):
    with pytest.raises(ValueError):
        ler_config_mcp(str(_wheel(tmp_path, nome)))


def test_config_mcp_recusa_wheel_ausente(tmp_path):
    with pytest.raises(ValueError):
        ler_config_mcp(str(tmp_path / WHEEL))


def test_tag_por_agente_e_config(tmp_path):
    sem = ler_config_mcp("sem")
    com = ler_config_mcp(str(_wheel(tmp_path)))
    assert tag_imagem(sem, "claude") == "localhost/novomodelo-mcp-bateria:claude-sem-mcp"
    assert tag_imagem(com, "kiro") == "localhost/novomodelo-mcp-bateria:kiro-mcp-1.2.3"
    tags = {tag_imagem(c, a) for c in (sem, com) for a in ("claude", "kiro")}
    assert len(tags) == 4
    with pytest.raises(ValueError):
        tag_imagem(sem, "outro")


def test_versoes_fixadas_do_novomodelo_vem_do_pin_do_produto():
    versoes = versoes_fixadas()
    assert versoes["NOVOMODELO_VERSAO"] == NOVOMODELO
    assert versoes["BRIDGE_VERSAO"] == NOVOMODELO
    assert versoes["CLAUDE_CODE_VERSAO"] == CLAUDE_CODE_VERSAO


def test_versoes_fixadas_sem_pin_do_produto_falha(monkeypatch):
    monkeypatch.setattr(imagens, "expected_version", lambda: None)
    with pytest.raises(FalhaPreparo):
        versoes_fixadas()


def test_build_passa_as_versoes_fixadas(tmp_path):
    wheel = _wheel(tmp_path)
    motor = MotorFalso(
        {
            "novomodelo": NOVOMODELO,
            "novomodelo-bridge": NOVOMODELO,
            "claude-code": CLAUDE_CODE_VERSAO,
            "novomodelo-mcp": "1.2.3",
        }
    )
    versoes = construir(ler_config_mcp(str(wheel)), "claude", _cfg(tmp_path), rodar=motor)

    build, kwargs_build = motor.chamadas[0]
    assert build[:2] == ["podman", "build"]
    assert build[build.index("-f") + 1] == str(imagens.CONTAINERFILE)
    assert build[build.index("-t") + 1] == "localhost/novomodelo-mcp-bateria:claude-mcp-1.2.3"
    args = _build_args(build)
    assert args == {
        **versoes_fixadas(),
        "AGENTE": "claude",
        "CLIENTE": "claude-code",
        "CONFIG": "mcp",
        "HOME_AGENTE": HOME_AGENTE,
        "PASTA_ESTUDOS": PASTA_ESTUDOS,
    }
    assert motor.contexto == ["wheel", f"wheel/{WHEEL}"]
    assert not any(TOKEN_FALSO in a or "token" in a.lower() for a in build)

    leitura, _ = motor.chamadas[1]
    assert leitura[:3] == ["podman", "run", "--rm"]
    assert "--network=none" in leitura
    assert leitura[-2:] == ["cat", f"{HOME_AGENTE}/versoes.json"]
    assert versoes == {
        "novomodelo": NOVOMODELO,
        "novomodelo-bridge": NOVOMODELO,
        "claude-code": CLAUDE_CODE_VERSAO,
        "mcp:mcp-1.2.3": "1.2.3",
    }


def test_build_sem_mcp_leva_contexto_vazio(tmp_path):
    motor = MotorFalso(
        {"novomodelo": NOVOMODELO, "novomodelo-bridge": NOVOMODELO, "kiro-cli": "1.0.0"}
    )
    versoes = construir(ler_config_mcp("sem"), "kiro", _cfg(tmp_path), rodar=motor)
    args = _build_args(motor.chamadas[0][0])
    assert args["CONFIG"] == "sem-mcp"
    assert args["CLIENTE"] == "kiro"
    assert motor.contexto == ["wheel"]
    assert versoes["kiro-cli"] == "1.0.0 (não fixada)"
    assert not any(k.startswith("mcp:") for k in versoes)


def test_build_com_falha_do_motor_nao_le_versoes(tmp_path):
    motor = MotorFalso(codigo_build=1)
    with pytest.raises(FalhaPreparo):
        construir(ler_config_mcp("sem"), "claude", _cfg(tmp_path), rodar=motor)
    assert len(motor.chamadas) == 1


@pytest.mark.parametrize(
    "versoes",
    [
        {"novomodelo": NOVOMODELO, "novomodelo-bridge": NOVOMODELO},
        {"novomodelo": NOVOMODELO, "novomodelo-bridge": NOVOMODELO, "claude-code": "0.0.1"},
        {"novomodelo": "0.0.1", "novomodelo-bridge": NOVOMODELO, "claude-code": CLAUDE_CODE_VERSAO},
    ],
)
def test_build_recusa_imagem_com_versao_ausente_ou_diferente_da_fixada(tmp_path, versoes):
    with pytest.raises(FalhaPreparo):
        construir(ler_config_mcp("sem"), "claude", _cfg(tmp_path), rodar=MotorFalso(versoes))


def test_build_recusa_motor_que_nao_e_podman(tmp_path):
    motor = MotorFalso()
    with pytest.raises(FalhaPreparo, match=MOTIVO_MOTOR):
        construir(ler_config_mcp("sem"), "claude", _cfg(tmp_path, "docker"), rodar=motor)
    assert motor.chamadas == []


@pytest.mark.parametrize(("existe", "troca"), [(1, []), (0, ["--replace"])])
def test_segredo_sem_valor_na_linha_de_comando(tmp_path, existe, troca):
    cfg = _cfg(tmp_path)
    cfg.token_claude.write_text(TOKEN_FALSO, encoding="utf-8")
    motor = MotorFalso(existe=existe)
    criar_segredo(cfg, rodar=motor)

    (consulta, _), (cmd, kwargs) = motor.chamadas
    assert consulta == ["podman", "secret", "exists", SEGREDO_CLAUDE]
    assert cmd == ["podman", "secret", "create", *troca, SEGREDO_CLAUDE, str(cfg.token_claude)]
    assert not any(TOKEN_FALSO in a for a in cmd)
    assert "input" not in kwargs
    assert kwargs["stdin"] == subprocess.DEVNULL


def test_segredo_com_consulta_recusada_nao_cria(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.token_claude.write_text(TOKEN_FALSO, encoding="utf-8")
    motor = MotorFalso(existe=125)
    with pytest.raises(FalhaPreparo):
        criar_segredo(cfg, rodar=motor)
    assert len(motor.chamadas) == 1


def test_segredo_recusa_motor_que_nao_e_podman(tmp_path):
    cfg = _cfg(tmp_path, "docker")
    cfg.token_claude.write_text(TOKEN_FALSO, encoding="utf-8")
    motor = MotorFalso()
    with pytest.raises(FalhaPreparo, match=MOTIVO_MOTOR):
        criar_segredo(cfg, rodar=motor)
    assert motor.chamadas == []


def test_segredo_com_token_ausente_falha_sem_chamar_o_motor(tmp_path):
    motor = MotorFalso()
    with pytest.raises(FalhaPreparo):
        criar_segredo(_cfg(tmp_path), rodar=motor)
    assert motor.chamadas == []


def test_segredo_recusado_pelo_motor_nao_mostra_o_valor(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.token_claude.write_text(TOKEN_FALSO, encoding="utf-8")

    def recusa(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 125, "", TOKEN_FALSO)

    with pytest.raises(FalhaPreparo) as erro:
        criar_segredo(cfg, rodar=recusa)
    assert TOKEN_FALSO not in str(erro.value)
