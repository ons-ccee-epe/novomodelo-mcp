"""`go-no-go` e `marcar-lancamento` da CLI, sobre pastas de rodada sintéticas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e import __main__ as cli
from tests.e2e.config import Config
from tests.e2e.go_no_go.lancamentos import marcar_lancamento
from tests.e2e.resultado.armazenamento import gravar_manifesto, gravar_registro
from tests.e2e.resultado.modelos import Conjunto, Estado, Manifesto, Registro

VERSOES = {
    chave: "1"
    for chave in (
        "novomodelo",
        "novomodelo-bridge",
        "claude-code",
        "kiro-cli",
        "juiz-modelo",
        "juiz-temperatura",
    )
}


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


@pytest.fixture(autouse=True)
def _ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "carregar_config", lambda env: _cfg(tmp_path))


def _reg(rodada, config, caso, estado: Estado, conjunto: Conjunto = "tools", rep=1) -> Registro:
    return Registro(
        rodada=rodada,
        conjunto=conjunto,
        caso=caso,
        agente="claude" if conjunto != "deterministica" else "nenhum",
        config=config if conjunto != "deterministica" else "checkout",
        repeticao=rep,
        estado=estado,
        motivo="",
        tools=(),
        duracao_s=1.0,
    )


def _rodada(tmp_path, nome, dados: dict[str, dict[str, Estado]], det: Estado = "passou") -> Path:
    """`dados`: configuração -> caso -> estado."""
    pasta = tmp_path / "res" / nome
    gravar_manifesto(
        pasta,
        Manifesto(
            rodada=nome,
            criado_em="2026-01-01T00:00:00Z",
            configs=tuple(dados),
            conjuntos=("deterministica", "tools"),
            agentes=("claude",),
            repeticoes=1,
            flags={"completa": False},
            versoes=VERSOES,
            commit_bateria="abc",
        ),
    )
    gravar_registro(pasta, _reg(nome, "x", "t", det, "deterministica"))
    for config, casos in dados.items():
        for caso, estado in casos.items():
            gravar_registro(pasta, _reg(nome, config, caso, estado))
    return pasta


def _go(*args: str) -> int:
    return cli.main(["go-no-go", *args])


def test_baseline_config_da_mesma_rodada(tmp_path, capsys):
    pasta = _rodada(tmp_path, "r1", {"antiga": {"c": "passou"}, "nova": {"c": "falhou"}})
    assert _go("r1", "--alvo", "nova", "--baseline-config", "antiga") == 1
    relatorio = (pasta / "relatorio-go-no-go.md").read_text(encoding="utf-8")
    assert relatorio.startswith("# Veredito: NO-GO")
    assert "antiga · rodada r1" in relatorio
    assert "Rodada `r1` · alvo: `nova` · baseline:" in relatorio
    assert (pasta / "junit.xml").is_file()


def test_baseline_de_outra_rodada_usa_a_config_de_mesmo_nome(tmp_path):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    _rodada(tmp_path, "r2", {"mcp": {"c": "falhou"}})
    assert _go("r2", "--alvo", "mcp", "--baseline", "r1") == 1
    _rodada(tmp_path, "r3", {"mcp": {"c": "passou"}})
    assert _go("r3", "--alvo", "mcp", "--baseline", "r1") == 0


def test_baseline_config_vence_baseline_e_vale_na_rodada_da_base(tmp_path):
    _rodada(tmp_path, "r1", {"velha": {"c": "passou"}})
    _rodada(tmp_path, "r2", {"mcp": {"c": "falhou"}})
    assert _go("r2", "--alvo", "mcp", "--baseline", "r1", "--baseline-config", "velha") == 1


def test_baseline_cai_para_ultimo_lancamento(tmp_path):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    _rodada(tmp_path, "r2", {"mcp": {"c": "falhou"}})
    marcar_lancamento(tmp_path / "res", "r1", "1.0.0", "mcp")
    assert _go("r2", "--alvo", "mcp") == 1


def test_lancamento_procura_a_config_primeiro_na_propria_rodada(tmp_path):
    _rodada(tmp_path, "r1", {"antiga": {"c": "falhou"}})
    pasta = _rodada(tmp_path, "r2", {"antiga": {"c": "passou"}, "nova": {"c": "falhou"}})
    marcar_lancamento(tmp_path / "res", "r1", "1.0.0", "antiga")
    assert _go("r2", "--alvo", "nova") == 1
    relatorio = (pasta / "relatorio-go-no-go.md").read_text(encoding="utf-8")
    assert "antiga · rodada r2" in relatorio


def test_sem_lancamento_sem_base(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "falhou"}})
    assert _go("r1", "--alvo", "mcp") == 0
    assert "Sem baseline" in (pasta / "relatorio-go-no-go.md").read_text(encoding="utf-8")


def test_sem_base_a_deterministica_ainda_bloqueia(tmp_path):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}}, det="falhou")
    assert _go("r1", "--alvo", "mcp") == 1


def test_codigos_de_saida(tmp_path):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    _rodada(tmp_path, "r2", {"mcp": {"c": "erro_infra"}})
    assert _go("r1", "--alvo", "mcp") == 0
    assert _go("r2", "--alvo", "mcp", "--baseline", "r1") == 2
    _rodada(tmp_path, "r3", {"mcp": {"c": "falhou"}})
    assert _go("r3", "--alvo", "mcp", "--baseline", "r1") == 1


def test_recusa_com_segredo_bloqueado(tmp_path, capsys):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    (pasta / "BLOQUEADO-SEGREDO.txt").write_text("achado", encoding="utf-8")
    assert _go("r1", "--alvo", "mcp") == 3
    assert "bloqueada por segredo" in capsys.readouterr().err
    assert not (pasta / "relatorio-go-no-go.md").exists()
    assert not (pasta / "junit.xml").exists()


@pytest.mark.parametrize(
    "argv, trecho",
    [
        (["inexistente", "--alvo", "mcp"], "não existe"),
        (["..", "--alvo", "mcp"], "inválido"),
        (["r1", "--alvo", "outra"], "--alvo 'outra' não está no manifesto"),
        (["r1", "--alvo", "mcp", "--baseline-config", "outra"], "--baseline-config 'outra'"),
        (["r1", "--alvo", "mcp", "--baseline", "r9"], "não existe"),
        (["r1", "--alvo", "mcp", "--baseline", "r1"], "própria rodada"),
    ],
)
def test_recusas_saem_2_com_mensagem(tmp_path, capsys, argv, trecho):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    assert _go(*argv) == 64
    assert trecho in capsys.readouterr().err


def test_marcar_lancamento_pela_cli(tmp_path, capsys):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    assert cli.main(["marcar-lancamento", "r1", "1.2.3", "--config", "mcp"]) == 0
    lista = json.loads((tmp_path / "res" / "lancamentos.json").read_text(encoding="utf-8"))
    assert [(x["versao"], x["rodada"], x["config"]) for x in lista] == [("1.2.3", "r1", "mcp")]


def test_marcar_lancamento_recusa_config_ou_rodada_desconhecida(tmp_path):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    assert cli.main(["marcar-lancamento", "r1", "1.0.0", "--config", "outra"]) == 64
    assert cli.main(["marcar-lancamento", "r9", "1.0.0", "--config", "mcp"]) == 64
    assert not (tmp_path / "res" / "lancamentos.json").exists()


def test_help_documenta_os_codigos_separados(capsys):
    with pytest.raises(SystemExit):
        cli.main(["go-no-go", "--help"])
    texto = " ".join(capsys.readouterr().out.split())
    assert "não são os do rodar" in texto
    assert "0 go; 1 no-go; 2 inconclusivo" in texto
    with pytest.raises(SystemExit):
        cli.main(["rodar", "--help"])
    assert "não são os do go-no-go" in " ".join(capsys.readouterr().out.split())


def test_manifesto_fora_do_schema_e_recusa_sem_traceback(tmp_path, capsys):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    dados = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    del dados["filtro"]
    (pasta / "manifesto.json").write_text(json.dumps(dados), encoding="utf-8")
    assert _go("r1", "--alvo", "mcp") == 64
    assert "resultado ilegível em r1" in capsys.readouterr().err


def test_lancamento_orfao_recusa_com_64(tmp_path, capsys):
    _rodada(tmp_path, "r2", {"mcp": {"c": "passou"}})
    marcar_lancamento(tmp_path / "res", "r9", "1.0.0", "mcp")
    assert _go("r2", "--alvo", "mcp") == 64
    assert "base indisponível" in capsys.readouterr().err
    pasta = _rodada(tmp_path, "r1", {"outra": {"c": "passou"}})
    marcar_lancamento(tmp_path / "res", "r1", "1.1.0", "mcp")
    assert _go("r2", "--alvo", "mcp") == 64
    marcar_lancamento(tmp_path / "res", "r1", "1.2.0", "outra")
    (pasta / "BLOQUEADO-SEGREDO.txt").write_text("x", encoding="utf-8")
    assert _go("r2", "--alvo", "mcp") == 64


def test_rotulo_da_base_quando_o_lancamento_e_de_outra_rodada(tmp_path):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    pasta = _rodada(tmp_path, "r2", {"mcp": {"c": "passou"}})
    marcar_lancamento(tmp_path / "res", "r1", "1.0.0", "mcp")
    assert _go("r2", "--alvo", "mcp") == 0
    relatorio = (pasta / "relatorio-go-no-go.md").read_text(encoding="utf-8")
    assert "baseline: `mcp · rodada r1 (lançamento 1.0.0)`" in relatorio


def test_reexecucao_sobrescreve_sem_deixar_temporarios(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    (pasta / "relatorio-go-no-go.md").write_text("velho", encoding="utf-8")
    (pasta / "junit.xml").write_text("velho", encoding="utf-8")
    assert _go("r1", "--alvo", "mcp") == 0
    assert (pasta / "relatorio-go-no-go.md").read_text(encoding="utf-8").startswith("# Veredito")
    assert (pasta / "junit.xml").read_text(encoding="utf-8").startswith("<?xml")
    assert not list(pasta.glob(".*.tmp"))


def test_falha_ao_escrever_mantem_o_relatorio_anterior(tmp_path, monkeypatch):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    (pasta / "relatorio-go-no-go.md").write_text("velho", encoding="utf-8")

    def quebra(*args, **kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(cli, "escrever_relatorio", quebra)
    with pytest.raises(OSError):
        _go("r1", "--alvo", "mcp")
    assert (pasta / "relatorio-go-no-go.md").read_text(encoding="utf-8") == "velho"
    assert not list(pasta.glob(".*.tmp"))


def test_deterministica_da_base_nao_influencia_o_veredito(tmp_path):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}}, det="falhou")
    _rodada(tmp_path, "r2", {"mcp": {"c": "passou"}}, det="passou")
    assert _go("r2", "--alvo", "mcp", "--baseline", "r1") == 0
    _rodada(tmp_path, "r3", {"mcp": {"c": "passou"}, "base": {"c": "passou"}}, det="passou")
    assert _go("r3", "--alvo", "mcp", "--baseline-config", "base") == 0
