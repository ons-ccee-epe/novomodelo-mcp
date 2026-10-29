"""Relatório de go/no-go e registro de lançamentos, sobre dados sintéticos."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.e2e.go_no_go.criterio import Bloqueio, Decisao, decidir
from tests.e2e.go_no_go.lancamentos import (
    LancamentosCorrompido,
    marcar_lancamento,
    ultimo_lancamento,
)
from tests.e2e.go_no_go.relatorio import avaliacao_ampla, escrever_relatorio, ordenar_configs
from tests.e2e.resultado.modelos import (
    ChamadaTool,
    Conjunto,
    Estado,
    Manifesto,
    Metricas,
    Registro,
)


def manifesto(configs: tuple[str, ...] = ("com-mcp",), completa: bool = False) -> Manifesto:
    return Manifesto(
        rodada="r2",
        criado_em="2026-01-02T03:04:05Z",
        configs=configs,
        conjuntos=("tools", "usuario"),
        agentes=("claude",),
        repeticoes=3,
        flags={"completa": completa},
        versoes={"mcp": "1.2.3", "novomodelo": "4.5.6"},
        commit_bateria="abc1234",
    )


def reg(
    caso: str,
    estado: Estado,
    repeticao: int = 1,
    config: str = "com-mcp",
    conjunto: Conjunto = "tools",
    tools: tuple[ChamadaTool, ...] = (),
    duracao_s: float = 10.0,
) -> Registro:
    return Registro(
        rodada="r2",
        conjunto=conjunto,
        caso=caso,
        agente="claude",
        config=config,
        repeticao=repeticao,
        estado=estado,
        motivo="",
        tools=tools,
        duracao_s=duracao_s,
    )


def gerar(
    tmp_path: Path,
    registros: list[Registro],
    decisao: Decisao | None = None,
    m: Manifesto | None = None,
    base: str | None = "r1",
) -> str:
    decisao = decisao or decidir(registros, None if base is None else registros)
    destino = tmp_path / "rodada" / "relatorio-go-no-go.md"
    destino.parent.mkdir(exist_ok=True)
    escrever_relatorio(m or manifesto(), registros, decisao, "r2", base, destino)
    return destino.read_text(encoding="utf-8")


def test_primeira_linha_tem_o_veredito(tmp_path: Path) -> None:
    texto = gerar(tmp_path, [reg("a", "passou")])
    assert "go" in texto.splitlines()[0].lower()
    decisao = Decisao("no-go", (), (), (), (), ())
    assert "no-go" in gerar(tmp_path, [], decisao).splitlines()[0].lower()


def test_bloqueio_lista_evidencia(tmp_path: Path) -> None:
    evidencia = ("execucoes/tools/a/claude/com-mcp/1", "execucoes/tools/a/claude/com-mcp/2")
    bloqueio = Bloqueio("regressao_tool", "tools", "a", "claude", evidencia)
    decisao = Decisao("no-go", (bloqueio,), (), (), (), ())
    texto = gerar(tmp_path, [reg("a", "falhou")], decisao)
    assert "regressao_tool" in texto
    for item in evidencia:
        assert item in texto


def test_taxa_com_intervalo_de_wilson(tmp_path: Path) -> None:
    registros = [reg("a", "passou", i) for i in range(1, 4)] + [reg("a", "falhou", 4)]
    registros += [reg("a", "pulado", 5), reg("a", "erro_infra", 6)]
    texto = gerar(tmp_path, registros)
    assert "75% [30–95%]" in texto


def test_uma_config_sem_completa_nao_tem_lado_a_lado(tmp_path: Path) -> None:
    assert "Configurações lado a lado" not in gerar(tmp_path, [reg("a", "passou")])


def test_taxa_sem_registros_contaveis_e_traco(tmp_path: Path) -> None:
    texto = gerar(tmp_path, [reg("a", "pulado")])
    assert "| — |" in texto


def test_configs_lado_a_lado(tmp_path: Path) -> None:
    registros = [reg("a", "passou", config="com-mcp"), reg("a", "falhou", config="sem")]
    texto = gerar(tmp_path, registros, m=manifesto(("com-mcp", "sem")))
    secao = texto.split("## Configurações lado a lado")[1]
    assert "com-mcp" in secao.splitlines()[2]
    assert "sem" in secao.splitlines()[2]


def test_secoes_de_inconclusivos_pulados_sem_base_e_ausentes(tmp_path: Path) -> None:
    decisao = Decisao(
        "inconclusivo",
        (),
        ("tools/i/claude",),
        ("tools/p/claude",),
        ("tools/s/claude",),
        ("tools/z/claude",),
    )
    texto = gerar(tmp_path, [reg("a", "passou")], decisao)
    for item in ("tools/i/claude", "tools/p/claude", "tools/s/claude", "tools/z/claude"):
        assert item in texto


def test_sem_baseline_nao_lista_ausentes(tmp_path: Path) -> None:
    decisao = Decisao("go", (), (), (), (), ("tools/z/claude",))
    texto = gerar(tmp_path, [reg("a", "passou")], decisao, base=None)
    assert "sem baseline" in texto.lower()
    assert "tools/z/claude" not in texto


def test_tempo_medio_ignora_pulado_e_erro_infra(tmp_path: Path) -> None:
    registros = [
        reg("a", "passou", 1, duracao_s=10.0),
        reg("a", "falhou", 2, duracao_s=20.0),
        reg("a", "pulado", 3, duracao_s=0.0),
        reg("a", "erro_infra", 4, duracao_s=900.0),
        reg("b", "pulado", 1, config="sem", duracao_s=5.0),
    ]
    texto = gerar(tmp_path, registros)
    secao = texto.split("## Tempo médio por execução")[1].split("##")[0]
    assert "| 15.0 |" in secao
    assert "| — |" in secao


def test_sem_baseline_diz_sem_baseline(tmp_path: Path) -> None:
    decisao = Decisao("go", (), (), (), (), ())
    assert "sem baseline" in gerar(tmp_path, [reg("a", "passou")], decisao, base=None).lower()


def test_tools_mais_chamadas_limitadas_a_dez_e_ordenadas(tmp_path: Path) -> None:
    chamadas = tuple(ChamadaTool(f"t{i:02d}", True, 0.1) for i in range(12) for _ in range(12 - i))
    texto = gerar(tmp_path, [reg("a", "passou", tools=chamadas)])
    assert "`t00`" in texto
    assert "`t09`" in texto
    assert "`t10`" not in texto


def test_relatorio_e_deterministico_e_ordenado(tmp_path: Path) -> None:
    registros = [reg("b", "passou"), reg("a", "falhou", 2), reg("a", "passou")]
    primeiro = gerar(tmp_path, registros)
    segundo = gerar(tmp_path, list(reversed(registros)))
    assert primeiro == segundo


def test_relatorio_sem_caminho_absoluto(tmp_path: Path) -> None:
    texto = gerar(tmp_path, [reg("a", "passou")])
    assert "/home/" not in texto
    assert "C:\\" not in texto
    assert str(tmp_path) not in texto
    assert "1.2.3" in texto.splitlines()[-1]


def amplo(
    caso: str,
    config: str,
    agente: str = "claude",
    estado: Estado = "passou",
    acerto: bool = True,
    nota: int | None = 2,
    interrupcoes: int = 1,
    t_total: float = 10.0,
    tokens: int | None = 1000,
) -> Registro:
    return Registro(
        rodada="r2",
        conjunto="usuario",
        caso=caso,
        agente=agente,
        config=config,
        repeticao=1,
        estado=estado,
        motivo="",
        tools=(),
        duracao_s=t_total + 500.0,
        metricas=Metricas(
            acerto_tool=acerto,
            contornos=0,
            interrupcoes=interrupcoes,
            indice_autonomia=0.5,
            t_total=t_total,
            tokens_entrada=tokens,
            nota_juiz=nota,
        ),
    )


CABECALHO = " | ".join(
    (
        "| condição",
        "n",
        "uso da tool esperada (0–1)",
        "nota juiz (0–2)",
        "contornos",
        "interrupções",
        "autonomia",
        "tempo (s)",
        "tokens entrada |",
    )
)

V19_CLAUDE = f"""### claude: resumo

{CABECALHO}
|---|---|---|---|---|---|---|---|---|
| sem-mcp | 1 | 0.00 | 1.00 | 0.00 | 3.00 | 0.50 | 20.00 | 1000 |
| mcp-0.18.0.post1 | 2 | 1.00 | 1.50 | 0.00 | 1.00 | 0.50 | 150 | 1000 |
| mcp-0.19.1 | 1 | 1.00 | 2.00 | 0.00 | 1.00 | 0.50 | 10.00 | 1000 |

### claude: por cenário (uso da tool / nota / interrupções / tempo)

| cenário | sem-mcp | mcp-0.18.0.post1 | mcp-0.19.1 |
|---|---|---|---|
| c01-a | 0.00 / 1.00 / 3.00 / 20.00 | 1.00 / 2.00 / 1.00 / 10.00 | 1.00 / 2.00 / 1.00 / 10.00 |
| c02-b | — | 1.00 / 1.00 / 1.00 / 290 | — |
"""

V19_KIRO = f"""### kiro: resumo

{CABECALHO}
|---|---|---|---|---|---|---|---|---|
| mcp-0.19.1 | 1 | 1.00 | 2.00 | 0.00 | 1.00 | 0.50 | 10.00 | — |
"""


def _registros_amplos() -> list[Registro]:
    return [
        amplo("c01-a", "mcp-0.19.1"),
        amplo("c01-a", "mcp-0.18.0.post1"),
        amplo("c02-b", "mcp-0.18.0.post1", nota=1, t_total=290.0),
        amplo("c01-a", "sem-mcp", acerto=False, nota=1, interrupcoes=3, t_total=20.0),
        amplo("c01-a", "mcp-0.19.1", agente="kiro", tokens=None),
        amplo("c03-c", "mcp-0.19.1", estado="erro_infra"),
        reg("caso-de-tools", "passou", conjunto="tools"),
    ]


def test_relatorio_amplo_no_formato_da_v19() -> None:
    texto = "\n".join(avaliacao_ampla(_registros_amplos())) + "\n"
    assert texto.startswith("## Avaliação ampla — 5 conversas\n")
    assert V19_CLAUDE in texto
    assert V19_KIRO in texto
    assert "c03-c" not in texto and "caso-de-tools" not in texto


def test_configs_em_ordem_sem_mcp_e_depois_por_versao() -> None:
    assert ordenar_configs(["mcp-0.19.1", "outra", "mcp-0.18.0.post1", "sem-mcp", "mcp-0.19"]) == [
        "sem-mcp",
        "mcp-0.18.0.post1",
        "mcp-0.19",
        "mcp-0.19.1",
        "outra",
    ]


def test_escrever_relatorio_inclui_a_avaliacao_ampla_so_com_o_conjunto_usuario(
    tmp_path: Path,
) -> None:
    texto = gerar(tmp_path, _registros_amplos(), m=manifesto(("mcp-0.19.1", "sem-mcp")))
    assert V19_CLAUDE in texto
    assert texto.index("## Avaliação ampla") < texto.index("Versões:")
    assert "Avaliação ampla" not in gerar(tmp_path, [reg("a", "passou")])


def test_marcar_e_ler_ultimo_lancamento(tmp_path: Path) -> None:
    marcar_lancamento(tmp_path, "r1", "1.0.0", "com-mcp")
    marcar_lancamento(tmp_path, "r2", "1.1.0", "com-mcp")
    ultimo = ultimo_lancamento(tmp_path)
    assert ultimo is not None
    assert (ultimo["versao"], ultimo["rodada"], ultimo["config"]) == ("1.1.0", "r2", "com-mcp")
    assert ultimo["marcado_em"].endswith("+00:00")
    assert datetime.fromisoformat(ultimo["marcado_em"]).utcoffset() == timedelta(0)
    assert len(json.loads((tmp_path / "lancamentos.json").read_text(encoding="utf-8"))) == 2


def test_lancamentos_vazio_devolve_none(tmp_path: Path) -> None:
    assert ultimo_lancamento(tmp_path) is None
    (tmp_path / "lancamentos.json").write_text("[]", encoding="utf-8")
    assert ultimo_lancamento(tmp_path) is None


@pytest.mark.parametrize("conteudo", ["{nao e json", '{"a": 1}', "[1]"])
def test_lancamentos_corrompido_nao_e_sobrescrito(tmp_path: Path, conteudo: str) -> None:
    arquivo = tmp_path / "lancamentos.json"
    arquivo.write_text(conteudo, encoding="utf-8")
    with pytest.raises(LancamentosCorrompido):
        marcar_lancamento(tmp_path, "r1", "1.0.0", "c")
    with pytest.raises(LancamentosCorrompido):
        ultimo_lancamento(tmp_path)
    assert arquivo.read_text(encoding="utf-8") == conteudo


def test_relatorio_mostra_sha256_origem_e_versoes(tmp_path: Path) -> None:
    sha = "ab" * 32
    m = Manifesto(
        rodada="r2",
        criado_em="2026-01-02T03:04:05Z",
        configs=("sem-mcp", "mcp-0.19.0"),
        conjuntos=("tools",),
        agentes=("claude", "kiro"),
        repeticoes=1,
        flags={"completa": True},
        versoes={
            "mcp:mcp-0.19.0": "0.19.0",
            "juiz-modelo": "modelo-do-juiz",
            "juiz-temperatura": "padrão do CLI (pedida 0.0)",
        },
        commit_bateria="abc1234",
        wheels={"mcp-0.19.0": {"arquivo": "x.whl", "sha256": sha, "origem": "release v0.19.0"}},
        imagens={
            "img:claude-mcp-0.19.0": {
                "novomodelo": "0.19.1",
                "novomodelo-bridge": "0.19.0",
                "claude-code": "2.1.310",
            },
            "img:kiro-mcp-0.19.0": {
                "novomodelo": "0.19.1",
                "novomodelo-bridge": "0.19.0",
                "kiro-cli": "1.2.3 (não fixada)",
            },
        },
        filtro="a01-x",
    )
    texto = gerar(tmp_path, [reg("a", "passou")], m=m)
    secao = texto.split("\n## Configurações\n")[1].split("\n---")[0]
    assert sha in secao
    assert "release v0.19.0" in secao
    assert "| mcp-0.19.0 | 0.19.0 |" in secao
    assert "| sem-mcp | sem MCP |" in secao
    assert "2.1.310" in secao
    assert "1.2.3 (não fixada)" in secao
    assert "modelo-do-juiz" in secao
    assert "padrão do CLI (pedida 0.0)" in secao
    assert "`a01-x`" in secao
    assert "/home" not in texto
