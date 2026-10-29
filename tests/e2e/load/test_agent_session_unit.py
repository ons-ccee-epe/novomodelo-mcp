"""Sessão de agente da carga pelo executor: sem container nem agente, com o executor falso."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.e2e.config import Config
from tests.e2e.executor.container import Execucao
from tests.e2e.executor.eventos import Evento, Leitura
from tests.e2e.executor.imagens import ConfigMCP
from tests.e2e.load.agent_engine import PreflightResult
from tests.e2e.load.agent_session import AGENTE_DO_PROVEDOR, ExecutorSessionRunner
from tests.e2e.load.agent_setup import session_factory
from tests.e2e.load.fakes import make_case
from tests.e2e.resultado.modelos import Registro

CONFIG_MCP = ConfigMCP("mcp-0.19.0", Path("/nao/usado.whl"))


def _cfg(tmp_path: Path) -> Config:
    return Config(
        motor="podman",
        resultados=tmp_path / "resultados",
        casos=None,
        cenarios_extra=None,
        token_claude=tmp_path / "token",
        volume_kiro="v",
        cache=tmp_path / "cache",
    )


def _leitura() -> Leitura:
    return Leitura(
        [
            Evento(
                tipo="tool",
                t=1.0,
                nome="docs_list",
                args={},
                erro=False,
                dados={"id": "a", "mcp": True},
            ),
            Evento(
                tipo="resultado_tool",
                t=2.0,
                nome="docs_list",
                args={},
                erro=False,
                dados={"id": "a", "mcp": True, "conteudo": '{"status": "ok"}'},
            ),
            Evento(
                tipo="fim",
                t=3.0,
                nome=None,
                args={},
                erro=False,
                dados={"resposta": "pronto"},
            ),
        ]
    )


class _Executor:
    def __init__(self, estado: str = "passou", motivo: str = "") -> None:
        self.estado, self.motivo = estado, motivo
        self.chamadas: list[tuple[Execucao, Path]] = []

    def __call__(self, e, cfg, pasta, avaliar) -> Registro:
        self.chamadas.append((e, pasta))
        if self.estado != "erro_infra":
            avaliar(_leitura())
        return Registro(
            rodada=pasta.name,
            conjunto=e.conjunto,
            caso=e.caso,
            agente=e.agente,
            config=e.config,
            repeticao=e.repeticao,
            estado=self.estado,  # type: ignore[arg-type]
            motivo=self.motivo,
            tools=(),
            duracao_s=4.0,
        )


def _runner(tmp_path: Path, executor: _Executor, **kwargs) -> ExecutorSessionRunner:
    return ExecutorSessionRunner(
        "claude", CONFIG_MCP, _cfg(tmp_path), tmp_path / "s0", executor=executor, **kwargs
    )


def test_carga_com_agente_usa_o_executor(tmp_path: Path) -> None:
    executor = _Executor()
    caso = replace(
        make_case("docs-list-all", tool="docs_list"),
        query="Liste os arquivos do caso {caso:exemplo_1dtoy}",
        timeout_s=90,
    )

    resultado = _runner(tmp_path, executor, preparados=tmp_path / "prep").execute(caso)

    ((execucao, pasta),) = executor.chamadas
    assert execucao.pedido == "Liste os arquivos do caso /estudos/exemplo_1dtoy"
    assert execucao.caso_origem == tmp_path / "prep" / "exemplo_1dtoy"
    assert execucao.liberar == ()
    assert execucao.somente_leitura is False
    assert (execucao.agente, execucao.timeout_s, execucao.config) == ("claude", 90, "mcp-0.19.0")
    assert execucao.imagem.endswith("claude-code-mcp-0.19.0") or "mcp-0.19.0" in execucao.imagem
    assert pasta == tmp_path / "s0"
    assert resultado.status == "completed"
    assert [c.name for c in resultado.tool_calls] == ["docs_list"]
    assert resultado.latency_ms == 4000.0


def test_cada_execucao_da_sessao_tem_repeticao_propria(tmp_path: Path) -> None:
    executor = _Executor()
    runner = _runner(tmp_path, executor)
    caso = make_case("docs-list-all", tool="docs_list")
    runner.execute(caso)
    runner.execute(caso)
    assert [e.repeticao for e, _ in executor.chamadas] == [1, 2]
    assert executor.chamadas[0][0].caso_origem is None


def test_tempo_esgotado_vira_timeout_e_outra_falha_levanta(tmp_path: Path) -> None:
    caso = make_case("docs-list-all", tool="docs_list")
    esgotado = _Executor("erro_infra", "tempo esgotado: o container foi encerrado pelo vigia")
    assert _runner(tmp_path, esgotado).execute(caso).status == "timeout"
    with pytest.raises(RuntimeError, match="motor de container ausente"):
        _runner(tmp_path, _Executor("erro_infra", "motor de container ausente")).execute(caso)


def test_cancelada_nao_executa(tmp_path: Path) -> None:
    executor = _Executor()
    runner = _runner(tmp_path, executor)
    runner.cancel()
    assert runner.execute(make_case("a", tool="docs_list")).status == "cancelled"
    assert executor.chamadas == []


def test_marcador_de_caso_nao_publico_e_recusado(tmp_path: Path) -> None:
    caso = replace(make_case("x", tool="docs_list"), query="Veja {caso:caso_interno}")
    with pytest.raises(ValueError, match="não é público"):
        _runner(tmp_path, _Executor()).execute(caso)


def test_fabrica_cria_uma_sessao_com_pasta_propria(tmp_path: Path) -> None:
    factory = session_factory("kiro-cli", CONFIG_MCP, _cfg(tmp_path), tmp_path / "run", None)
    primeira = factory(0, PreflightResult(selection=None))  # type: ignore[arg-type]
    segunda = factory(1, PreflightResult(selection=None))  # type: ignore[arg-type]
    assert primeira._pasta != segunda._pasta
    assert primeira._agente == AGENTE_DO_PROVEDOR["kiro-cli"] == "kiro"
