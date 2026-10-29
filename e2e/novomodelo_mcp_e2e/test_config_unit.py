"""Configuração da bateria e verificação do ambiente, sem rede nem container."""

from __future__ import annotations

import os
import sys
from pathlib import Path, PureWindowsPath

import platformdirs
import pytest

from novomodelo_mcp_e2e import config as modulo
from novomodelo_mcp_e2e.config import (
    APP,
    ITENS,
    Config,
    Problema,
    avisos,
    carregar_config,
    verificar,
    volume_existe_no_motor,
)

TOKEN_FALSO = "segredo-de-teste-123"


def so(*presentes: str):
    return lambda nome: f"/bin/{nome}" if nome in presentes else None


def cfg_em(tmp_path: Path, token: Path | None = None) -> Config:
    return Config(
        motor="podman",
        resultados=tmp_path / "res",
        casos=None,
        cenarios_extra=None,
        token_claude=token or tmp_path / "token",
        volume_kiro="vol",
        cache=tmp_path / "cache",
    )


def itens(problemas: list[Problema]) -> set[str]:
    return {p.item for p in problemas}


def test_defaults_por_platformdirs():
    cfg = carregar_config({}, quem=so("podman"))
    assert cfg.resultados == platformdirs.user_data_path(APP) / "resultados"
    assert cfg.token_claude == platformdirs.user_config_path(APP) / "token-claude"
    assert cfg.cache == platformdirs.user_cache_path(APP)
    assert cfg.volume_kiro == "novomodelo-bateria-kiro"
    assert cfg.casos is None
    assert cfg.cenarios_extra is None


def test_variaveis_sobrepoem_defaults(tmp_path):
    env = {
        "NOVOMODELO_BATERIA_MOTOR": "docker",
        "NOVOMODELO_BATERIA_RESULTADOS": str(tmp_path / "r"),
        "NOVOMODELO_BATERIA_CASOS": str(tmp_path / "c"),
        "NOVOMODELO_BATERIA_CENARIOS_EXTRA": str(tmp_path / "x"),
        "NOVOMODELO_BATERIA_TOKEN_CLAUDE": str(tmp_path / "t"),
        "NOVOMODELO_BATERIA_VOLUME_KIRO": "meu-volume",
    }
    cfg = carregar_config(env, quem=so("podman"))
    assert cfg.motor == "docker"
    assert cfg.resultados == tmp_path / "r"
    assert cfg.casos == tmp_path / "c"
    assert cfg.cenarios_extra == tmp_path / "x"
    assert cfg.token_claude == tmp_path / "t"
    assert cfg.volume_kiro == "meu-volume"


def test_valor_vazio_conta_como_ausente_e_til_expande():
    cfg = carregar_config(
        {"NOVOMODELO_BATERIA_MOTOR": "", "NOVOMODELO_BATERIA_CASOS": "~/casos-x"},
        quem=so("docker"),
    )
    assert cfg.motor == "docker"
    assert cfg.casos == Path("~/casos-x").expanduser()
    assert "~" not in str(cfg.casos)


def test_motor_prefere_podman_e_cai_para_docker():
    assert carregar_config({}, quem=so("podman", "docker")).motor == "podman"
    assert carregar_config({}, quem=so("docker")).motor == "docker"
    assert carregar_config({}, quem=so()).motor == "docker"


def preparar_ok(tmp_path: Path) -> Config:
    token = tmp_path / "token"
    token.write_text(TOKEN_FALSO)
    if sys.platform != "win32":
        token.chmod(0o600)
    return cfg_em(tmp_path, token)


def test_verificar_ambiente_ok_cria_pastas(tmp_path):
    cfg = preparar_ok(tmp_path)
    assert verificar(cfg, quem=so("podman"), volume_existe=lambda m, v: True) == []
    assert cfg.resultados.is_dir() and cfg.cache.is_dir()


def test_verificar_aponta_cada_item_ausente(tmp_path):
    cfg = Config(
        motor="podman",
        resultados=tmp_path / "res",
        casos=tmp_path / "sem-casos",
        cenarios_extra=tmp_path / "sem-extra",
        token_claude=tmp_path / "sem-token",
        volume_kiro="vol",
        cache=tmp_path / "cache",
    )
    problemas = verificar(cfg, quem=so(), volume_existe=lambda m, v: False)
    assert itens(problemas) == {
        "motor",
        "token_claude",
        "volume_kiro",
        "casos",
        "cenarios_extra",
    }


def test_verificar_recebe_motor_e_nome_do_volume(tmp_path):
    vistos = []
    cfg = preparar_ok(tmp_path)
    verificar(cfg, quem=so("podman"), volume_existe=lambda m, v: vistos.append((m, v)) or True)
    assert vistos == [("podman", "vol")]


def test_resultados_nao_gravavel_e_problema(tmp_path):
    arquivo = tmp_path / "arquivo"
    arquivo.write_text("x")
    cfg = preparar_ok(tmp_path)
    cfg = Config(**{**cfg.__dict__, "resultados": arquivo / "dentro"})
    problemas = verificar(cfg, quem=so("podman"), volume_existe=lambda m, v: True)
    assert "resultados" in itens(problemas)


@pytest.mark.skipif(sys.platform == "win32", reason="modo POSIX")
def test_token_com_permissao_aberta_e_recusado(tmp_path):
    cfg = preparar_ok(tmp_path)
    os.chmod(cfg.token_claude, 0o644)
    problemas = verificar(cfg, quem=so("podman"), volume_existe=lambda m, v: True)
    assert itens(problemas) == {"token_claude"}


def test_verificar_nunca_expoe_conteudo_do_token(tmp_path):
    cfg = preparar_ok(tmp_path)
    if sys.platform != "win32":
        os.chmod(cfg.token_claude, 0o644)
    problemas = verificar(cfg, quem=so(), volume_existe=lambda m, v: False)
    assert problemas
    for p in problemas:
        assert TOKEN_FALSO not in p.mensagem
        assert TOKEN_FALSO not in p.item
    home = str(Path.home())
    for p in problemas:
        resto = p.mensagem.replace(str(cfg.token_claude), "")
        resto = resto.replace(str(cfg.resultados), "").replace(str(cfg.cache), "")
        assert home not in resto


def test_caminhos_windows_e_espacos():
    bruto = "C:\\Users\\Fulano de Tal\\dados"
    p = PureWindowsPath(bruto)
    assert str(p) == bruto
    assert p.parts[2] == "Fulano de Tal"
    assert PureWindowsPath(str(p) + "\\resultados").parent == p
    assert PureWindowsPath(*p.parts) == p


def test_avisos_no_windows_sobre_permissao_do_token(tmp_path):
    cfg = cfg_em(tmp_path)
    saida = avisos(cfg, plataforma="win32")
    assert len(saida) == 1
    assert "permissão do token não verificada neste sistema" in saida[0]


def test_avisos_vazios_fora_do_windows(tmp_path):
    cfg = cfg_em(tmp_path)
    assert avisos(cfg, plataforma="linux") == []
    assert avisos(cfg, plataforma="darwin") == []


def falso_run(monkeypatch, *, retorno=None, erro=None):
    chamadas = []

    def run(args, **kw):
        chamadas.append(args)
        if erro:
            raise erro
        return retorno

    monkeypatch.setattr(modulo.subprocess, "run", run)
    return chamadas


class Feito:
    def __init__(self, returncode):
        self.returncode = returncode


def test_volume_existe_codigo_zero_e_diferente(monkeypatch):
    falso_run(monkeypatch, retorno=Feito(0))
    assert volume_existe_no_motor("podman", "v") is True
    falso_run(monkeypatch, retorno=Feito(1))
    assert volume_existe_no_motor("podman", "v") is False


@pytest.mark.parametrize(
    "erro", [OSError("x"), modulo.subprocess.TimeoutExpired(cmd="x", timeout=1)]
)
def test_volume_existe_erro_vira_falso(monkeypatch, erro):
    falso_run(monkeypatch, erro=erro)
    assert volume_existe_no_motor("podman", "v") is False


def test_volume_com_hifen_vem_depois_de_separador(monkeypatch):
    chamadas = falso_run(monkeypatch, retorno=Feito(0))
    volume_existe_no_motor("podman", "-x")
    args = chamadas[0]
    assert args.index("--") < args.index("-x")


def test_itens_dos_problemas_sao_os_estaveis(tmp_path):
    cfg = Config(
        motor="podman",
        resultados=tmp_path / "arq" / "r",
        casos=tmp_path / "c",
        cenarios_extra=tmp_path / "e",
        token_claude=tmp_path / "t",
        volume_kiro="v",
        cache=tmp_path / "arq" / "c",
    )
    (tmp_path / "arq").write_text("x")
    problemas = verificar(cfg, quem=so(), volume_existe=lambda m, v: False)
    assert itens(problemas) == set(ITENS)


def test_memoria_vem_do_ambiente_com_padrao():
    assert carregar_config({}, quem=so("podman")).memoria == "6g"
    env = {"NOVOMODELO_BATERIA_MEMORIA": "3g"}
    assert carregar_config(env, quem=so("podman")).memoria == "3g"


@pytest.mark.parametrize("motor", ["docker", "/usr/bin/docker", "nerdctl"])
def test_verificar_recusa_motor_que_nao_e_podman(tmp_path, motor):
    cfg = Config(**{**preparar_ok(tmp_path).__dict__, "motor": motor})
    problemas = verificar(cfg, quem=lambda nome: nome, volume_existe=lambda m, v: True)
    assert Problema("motor", "o token do Claude só entra pelo secret do podman; use podman") in (
        problemas
    )


@pytest.mark.parametrize("motor", ["podman", "/usr/bin/podman", "podman.exe"])
def test_verificar_aceita_podman_por_nome_ou_caminho(tmp_path, motor):
    cfg = Config(**{**preparar_ok(tmp_path).__dict__, "motor": motor})
    assert verificar(cfg, quem=lambda nome: nome, volume_existe=lambda m, v: True) == []
