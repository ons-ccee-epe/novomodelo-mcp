"""Linha de comando da bateria (`python -m novomodelo_mcp_e2e`), sem motor nem rede."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novomodelo_mcp_e2e import __main__ as cli
from novomodelo_mcp_e2e.config import Config, Problema
from novomodelo_mcp_e2e.executor.imagens import ConfigMCP, FalhaPreparo


def _cfg(tmp_path: Path) -> Config:
    return Config(
        motor="podman",
        resultados=tmp_path / "res",
        casos=None,
        cenarios_extra=None,
        token_claude=tmp_path / "token",
        volume_kiro="vol",
        cache=tmp_path / "cache",
    )


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    chamadas: dict[str, list] = {"construir": [], "segredo": []}
    problemas: list[Problema] = []
    monkeypatch.setattr(cli, "carregar_config", lambda env: _cfg(tmp_path))
    monkeypatch.setattr(cli, "verificar", lambda cfg: list(problemas))
    monkeypatch.setattr(cli, "avisos", lambda cfg: [])
    monkeypatch.setattr(cli, "aviso_do_bridge", lambda c: None)
    monkeypatch.setattr(cli, "expected_version", lambda: "1.0.0")
    chamadas["publicos"] = []

    def publicos(versao, imagem, cfg):
        chamadas["publicos"].append((versao, imagem))
        return ["exemplo_1dtoy"]

    monkeypatch.setattr(cli, "preparar_publicos", publicos)

    def construir(c, agente, cfg):
        chamadas["construir"].append((c, agente))
        return {"novomodelo": "1.0.0"}

    monkeypatch.setattr(cli, "construir", construir)
    monkeypatch.setattr(cli, "criar_segredo", lambda cfg: chamadas["segredo"].append(cfg))
    return chamadas, problemas


def test_cli_verificar_sai_1_com_problema(ambiente, capsys):
    _, problemas = ambiente
    problemas.append(Problema("token_claude", "arquivo de token não encontrado"))
    assert cli.main(["verificar"]) == 1
    assert "token_claude" in capsys.readouterr().out


def test_cli_verificar_sai_0_e_mostra_avisos(ambiente, monkeypatch, capsys):
    monkeypatch.setattr(cli, "avisos", lambda cfg: ["permissão do token não verificada"])
    assert cli.main(["verificar"]) == 0
    assert "permissão do token não verificada" in capsys.readouterr().out


def test_cli_preparar_constroi_uma_imagem_por_config_e_agente(ambiente, tmp_path, capsys):
    chamadas, _ = ambiente
    wheel = tmp_path / "novomodelo_mcp-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"x")
    rc = cli.main(["preparar", "--mcp", "sem", str(wheel), "--agentes", "claude,kiro"])
    assert rc == 0
    assert chamadas["construir"] == [
        (ConfigMCP("sem-mcp", None), "claude"),
        (ConfigMCP("sem-mcp", None), "kiro"),
        (ConfigMCP("mcp-1.2.3", wheel.resolve()), "claude"),
        (ConfigMCP("mcp-1.2.3", wheel.resolve()), "kiro"),
    ]
    assert len(chamadas["segredo"]) == 1
    assert chamadas["publicos"] == [("1.0.0", "localhost/novomodelo-mcp-bateria:claude-sem-mcp")]
    linhas = [json.loads(linha) for linha in capsys.readouterr().out.splitlines() if "{" in linha]
    imagens = [linha["imagem"] for linha in linhas if "imagem" in linha]
    assert imagens[0].endswith(":claude-sem-mcp")


def test_cli_preparar_so_kiro_nao_cria_o_secret_do_claude(ambiente):
    chamadas, problemas = ambiente
    problemas.append(Problema("token_claude", "arquivo de token não encontrado"))
    assert cli.main(["preparar", "--mcp", "sem", "--agentes", "kiro"]) == 0
    assert chamadas["segredo"] == []


def test_cli_preparar_para_com_problema_do_agente_pedido(ambiente):
    chamadas, problemas = ambiente
    problemas.append(Problema("token_claude", "arquivo de token não encontrado"))
    assert cli.main(["preparar", "--mcp", "sem", "--agentes", "claude"]) == 1
    assert chamadas == {"construir": [], "segredo": [], "publicos": []}


def test_cli_preparar_falha_de_construcao_sai_1(ambiente, monkeypatch, capsys):
    def falha(c, agente, cfg):
        raise FalhaPreparo("build falhou")

    monkeypatch.setattr(cli, "construir", falha)
    assert cli.main(["preparar", "--mcp", "sem", "--agentes", "kiro"]) == 1
    assert "build falhou" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [["preparar", "--mcp", "sem", "--agentes", "outro"], ["preparar", "--mcp", "nada.txt"]],
)
def test_cli_preparar_recusa_argumento_invalido(ambiente, argv):
    with pytest.raises(SystemExit) as saida:
        cli.main(argv)
    assert saida.value.code == 2


def test_cli_preparar_avisa_bridge_divergente_sem_falhar(ambiente, monkeypatch, capsys):
    monkeypatch.setattr(cli, "aviso_do_bridge", lambda c: "bridge 5.0.0 na wheel")
    assert cli.main(["preparar", "--mcp", "sem", "--agentes", "kiro"]) == 0
    assert "aviso: bridge 5.0.0 na wheel" in capsys.readouterr().out


def test_cli_preparar_falha_dos_casos_publicos_sai_1(ambiente, monkeypatch, capsys):
    def falha(versao, imagem, cfg):
        raise FalhaPreparo("commit da tag diferente")

    monkeypatch.setattr(cli, "preparar_publicos", falha)
    assert cli.main(["preparar", "--mcp", "sem", "--agentes", "kiro"]) == 1
    assert "commit da tag diferente" in capsys.readouterr().err


def test_cli_preparar_sem_pin_do_bridge_sai_1(ambiente, monkeypatch, capsys):
    monkeypatch.setattr(cli, "expected_version", lambda: None)
    assert cli.main(["preparar", "--mcp", "sem", "--agentes", "kiro"]) == 1
    assert "pin do novomodelo-bridge" in capsys.readouterr().err
