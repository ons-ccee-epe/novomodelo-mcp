"""`go-no-go` e `marcar-lancamento` da CLI, sobre pastas de rodada sintéticas."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.e2e import __main__ as cli
from tests.e2e import rodada
from tests.e2e.config import Config
from tests.e2e.go_no_go.lancamentos import marcar_lancamento
from tests.e2e.resultado.armazenamento import (
    gravar_manifesto,
    gravar_registro,
    ler_decisao,
)
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


def _plano_dos_casos_gravados(manifesto: Manifesto, cfg: Config) -> set[tuple]:
    """O plano do manifesto, com o catálogo trocado pelos casos que a rodada gravou."""
    execucoes = cfg.resultados / manifesto.rodada / "execucoes"
    casos = {
        (a.parent.name, a.name) for a in execucoes.glob("*/*") if a.parent.name != "deterministica"
    }
    return {
        (conjunto, caso, agente, config, rep)
        for conjunto, caso in casos
        for agente in manifesto.agentes
        for config in manifesto.configs
        for rep in range(1, manifesto.repeticoes + 1)
    }


@pytest.fixture(autouse=True)
def _ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "carregar_config", lambda env: _cfg(tmp_path))
    monkeypatch.setattr(rodada, "chaves_planejadas", _plano_dos_casos_gravados)
    monkeypatch.setattr(rodada, "varrer_segredos", lambda pasta: rodada.Varredura())


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


def _fim(pasta: Path, codigo: int) -> None:
    with (pasta / rodada.ARQUIVO_LOG).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"evento": "fim", "codigo": codigo, "motivo": "teste"}) + "\n")


def _rodada(
    tmp_path,
    nome,
    dados: dict[str, dict[str, Estado]],
    det: Estado = "passou",
    repeticoes: int = 1,
    codigo_fim: int | None = 0,
) -> Path:
    """`dados`: configuração -> caso -> estado, gravado na repetição 1."""
    pasta = tmp_path / "res" / nome
    gravar_manifesto(
        pasta,
        Manifesto(
            rodada=nome,
            criado_em="2026-01-01T00:00:00Z",
            configs=tuple(dados),
            conjuntos=("deterministica", "tools"),
            agentes=("claude",),
            repeticoes=repeticoes,
            flags={"completa": False},
            versoes=VERSOES,
            commit_bateria="abc",
        ),
    )
    gravar_registro(pasta, _reg(nome, "x", "t", det, "deterministica"))
    for config, casos in dados.items():
        for caso, estado in casos.items():
            gravar_registro(pasta, _reg(nome, config, caso, estado))
    if codigo_fim is not None:
        _fim(pasta, codigo_fim)
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

    def quebra(m, registros, decisao, alvo, base, destino, config_alvo=None):
        destino.write_text("parcial", encoding="utf-8")
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


@pytest.mark.parametrize(
    "argv",
    [
        ["go-no-go", "r1"],
        ["go-no-go", "r1", "--alvo", "mcp", "--inexistente"],
        ["marcar-lancamento", "r1", "1.0.0"],
        ["marcar-lancamento", "r1"],
    ],
)
def test_erro_de_uso_do_argparse_sai_64(argv, capsys):
    try:
        codigo = cli.main(argv)
    except SystemExit as saida:
        codigo = saida.code
    assert codigo == 64
    assert "erro:" in capsys.readouterr().err


@pytest.mark.skipif(os.name == "nt", reason="modos POSIX")
def test_arquivos_gravados_seguem_o_umask(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    antigo = os.umask(0o022)
    try:
        assert _go("r1", "--alvo", "mcp") == 0
    finally:
        os.umask(antigo)
    for nome in ("relatorio-go-no-go.md", "junit.xml"):
        assert (pasta / nome).stat().st_mode & 0o777 == 0o644


def test_grava_a_decisao_em_json_com_veredito_base_e_bloqueios(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"antiga": {"c": "passou"}, "nova": {"c": "falhou"}})
    assert _go("r1", "--alvo", "nova", "--baseline-config", "antiga") == 1
    dados = json.loads((pasta / "decisao-go-no-go.json").read_text(encoding="utf-8"))
    assert dados["schema_versao"] == 1
    assert dados["veredito"] == "no-go"
    assert dados["alvo"] == "nova"
    assert dados["base"] == "antiga · rodada r1"
    assert dados["bloqueios"][0]["caso"] == "c"
    assert dados["bloqueios"][0]["evidencia"]
    for campo in ("inconclusivos", "pulados", "sem_base", "ausentes"):
        assert isinstance(dados[campo], list)
    assert not list(pasta.glob(".decisao-go-no-go.json.*"))


def test_decisao_sem_base_grava_base_nula(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    assert _go("r1", "--alvo", "mcp") == 0
    dados = json.loads((pasta / "decisao-go-no-go.json").read_text(encoding="utf-8"))
    assert dados["veredito"] == "go" and dados["base"] is None


def test_decisao_gravada_valida_contra_o_schema(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"antiga": {"c": "passou"}, "nova": {"c": "falhou"}})
    assert _go("r1", "--alvo", "nova", "--baseline-config", "antiga") == 1
    assert ler_decisao(pasta)["veredito"] == "no-go"


def test_repeticoes_faltando_dao_inconclusivo_com_a_lista(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}}, repeticoes=3)
    assert _go("r1", "--alvo", "mcp") == 2
    dados = ler_decisao(pasta)
    assert dados["veredito"] == "inconclusivo"
    assert dados["incompleto"] == ["tools/c/claude/mcp/2", "tools/c/claude/mcp/3"]
    relatorio = (pasta / "relatorio-go-no-go.md").read_text(encoding="utf-8")
    assert "## Incompleto" in relatorio and "`tools/c/claude/mcp/3`" in relatorio


def test_base_incompleta_tambem_da_inconclusivo(tmp_path):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}}, repeticoes=2)
    _rodada(tmp_path, "r2", {"mcp": {"c": "passou"}})
    assert _go("r2", "--alvo", "mcp", "--baseline", "r1") == 2
    assert ler_decisao(tmp_path / "res" / "r2")["incompleto"] == ["base: tools/c/claude/mcp/2"]


def test_so_a_config_do_alvo_precisa_estar_completa(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}, "outra": {"c": "passou"}})
    for arquivo in (pasta / "execucoes" / "tools" / "c" / "claude" / "outra").rglob("*.json"):
        arquivo.unlink()
    assert _go("r1", "--alvo", "mcp") == 0


@pytest.mark.parametrize("codigo_fim", [5, None])
def test_fim_com_codigo_nao_zero_ou_sem_fim_da_inconclusivo(tmp_path, codigo_fim):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}}, codigo_fim=codigo_fim)
    assert _go("r1", "--alvo", "mcp") == 2
    [item] = ler_decisao(pasta)["incompleto"]
    assert "rodada.jsonl" in item


def test_vale_o_ultimo_fim_da_rodada_retomada(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}}, codigo_fim=4)
    _fim(pasta, 0)
    assert _go("r1", "--alvo", "mcp") == 0
    _fim(pasta, 5)
    assert _go("r1", "--alvo", "mcp") == 2


def test_falha_comprovada_continua_no_go_mesmo_incompleta(tmp_path):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}}, det="falhou", codigo_fim=1)
    assert _go("r1", "--alvo", "mcp") == 1
    assert ler_decisao(tmp_path / "res" / "r1")["incompleto"]


def test_rodada_completa_decide_normal_com_incompleto_vazio(tmp_path):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}}, repeticoes=1)
    assert _go("r1", "--alvo", "mcp") == 0
    assert ler_decisao(pasta)["incompleto"] == []
    assert "Rodada completa." in (pasta / "relatorio-go-no-go.md").read_text(encoding="utf-8")


def test_trava_viva_recusa_go_no_go_e_marcar_lancamento_com_64(tmp_path, monkeypatch, capsys):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    (pasta / rodada.ARQUIVO_TRAVA).write_text("4242 2026-01-01T00:00:00Z\n", encoding="utf-8")
    monkeypatch.setattr(rodada, "pid_vivo", lambda pid: pid == 4242)
    assert _go("r1", "--alvo", "mcp") == 64
    assert "em andamento" in capsys.readouterr().err
    assert not (pasta / "relatorio-go-no-go.md").exists()
    assert cli.main(["marcar-lancamento", "r1", "1.0.0", "--config", "mcp"]) == 64
    assert not (tmp_path / "res" / "lancamentos.json").exists()


def test_marcar_lancamento_recusa_rodada_incompleta(tmp_path, capsys):
    _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}}, repeticoes=2)
    assert cli.main(["marcar-lancamento", "r1", "1.0.0", "--config", "mcp"]) == 64
    assert "tools/c/claude/mcp/2" in capsys.readouterr().err
    _rodada(tmp_path, "r2", {"mcp": {"c": "passou"}}, codigo_fim=5)
    assert cli.main(["marcar-lancamento", "r2", "1.0.0", "--config", "mcp"]) == 64
    assert not (tmp_path / "res" / "lancamentos.json").exists()


@pytest.mark.parametrize(
    "varredura",
    [
        rodada.Varredura(arquivos=("execucoes/x/log.jsonl",)),
        rodada.Varredura(erro="gitleaks fora do PATH"),
    ],
)
def test_varredura_bloqueia_antes_do_relatorio(tmp_path, monkeypatch, capsys, varredura):
    pasta = _rodada(tmp_path, "r1", {"mcp": {"c": "passou"}})
    varridas = []
    monkeypatch.setattr(rodada, "varrer_segredos", lambda p: varridas.append(p) or varredura)
    assert _go("r1", "--alvo", "mcp") == 3
    assert varridas == [pasta]
    bloqueio = (pasta / rodada.ARQUIVO_BLOQUEIO).read_text(encoding="utf-8")
    assert (varredura.erro or varredura.arquivos[0]) in bloqueio
    for nome in ("relatorio-go-no-go.md", "junit.xml", "decisao-go-no-go.json"):
        assert not (pasta / nome).exists()
    assert "segredo" in capsys.readouterr().err
