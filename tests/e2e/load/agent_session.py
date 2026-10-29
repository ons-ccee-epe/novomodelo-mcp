"""Sessão de agente da carga: cada caso roda no container do executor, descartável.

O container recebe a cópia própria do caso público citado no pedido (marcador
``{caso:<nome>}``), então nada que uma sessão grava é lido por outra, e o agente não vê o
host. A carga não libera tool que grava: uma tool que pede aprovação fica negada, como no
conjunto de tools sem ``liberar``.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

from tests.e2e.config import Config
from tests.e2e.conjuntos.tools.adaptador import (
    CONJUNTO,
    TIMEOUT_PADRAO,
    caso_logico,
    para_query_result,
    pedido_do_caso,
)
from tests.e2e.executor.casos import pasta_preparados
from tests.e2e.executor.container import Execucao, executar
from tests.e2e.executor.eventos import Leitura
from tests.e2e.executor.imagens import ConfigMCP, tag_imagem
from tests.e2e.load.sandbox import make_run_root
from tests.e2e.queries.models import QueryResult, QueryTestCase
from tests.e2e.resultado.modelos import Avaliacao, Metricas, Registro
from tests.e2e.rodada import encerrar_em_voo, prefixo_do_container

__all__ = ["AGENTE_DO_PROVEDOR", "ExecutorSessionRunner", "default_run_root"]

AGENTE_DO_PROVEDOR = {"claude": "claude", "kiro-cli": "kiro"}
PREFIXO_TEMPO_ESGOTADO = "tempo esgotado"
Executor = Callable[[Execucao, Config, Path, Callable[[Leitura], Avaliacao]], Registro]


class ExecutorSessionRunner:
    """Roda um caso por vez no executor; cada sessão da carga tem a sua instância.

    ``execute`` devolve o ``QueryResult`` do stream, ``status="timeout"`` quando o vigia
    encerrou o container e levanta ``RuntimeError`` com o motivo quando a execução não
    chegou a rodar (``erro_infra``).
    """

    def __init__(
        self,
        agente: str,
        config_mcp: ConfigMCP,
        cfg: Config,
        pasta: Path,
        timeout_s: float | None = None,
        preparados: Path | None = None,
        executor: Executor = executar,
    ) -> None:
        self._agente = agente
        self._config_mcp = config_mcp
        self._cfg = cfg
        self._pasta = pasta
        self._timeout_s = timeout_s
        self._preparados = preparados
        self._executor = executor
        self._execucoes = 0
        self._cancelado = threading.Event()
        self._atual: Execucao | None = None
        pasta.mkdir(parents=True, exist_ok=True)

    def _execucao(self, caso: QueryTestCase) -> Execucao:
        nome = caso_logico(caso)
        base = self._preparados or pasta_preparados(self._cfg)
        self._execucoes += 1
        return Execucao(
            conjunto=CONJUNTO,
            caso=caso.id,
            agente=cast("Literal['claude', 'kiro']", self._agente),
            config=self._config_mcp.nome,
            repeticao=self._execucoes,
            pedido=pedido_do_caso(caso),
            caso_origem=base / nome if nome else None,
            somente_leitura=False,
            timeout_s=int(self._timeout_s or caso.timeout_s or TIMEOUT_PADRAO),
            imagem=tag_imagem(self._config_mcp, self._agente),
        )

    def execute(self, test_case: QueryTestCase) -> QueryResult:
        if self._cancelado.is_set():
            return self._sem_stream(test_case, "cancelled")
        execucao = self._execucao(test_case)
        self._atual = execucao
        leituras: list[Leitura] = []

        def avaliar(leitura: Leitura) -> Avaliacao:
            leituras.append(leitura)
            return Avaliacao("passou", "carga: o motor valida o stream", Metricas())

        registro = self._executor(execucao, self._cfg, self._pasta, avaliar)
        if self._cancelado.is_set():
            return self._sem_stream(test_case, "cancelled")
        if registro.estado == "erro_infra" or not leituras:
            if registro.motivo.startswith(PREFIXO_TEMPO_ESGOTADO):
                return replace(
                    self._sem_stream(test_case, "timeout"),
                    latency_ms=registro.duracao_s * 1000.0,
                    timeout_s=float(execucao.timeout_s),
                )
            raise RuntimeError(registro.motivo or "execução sem stream")
        resultado = para_query_result(test_case, leituras[-1])
        return replace(resultado, latency_ms=registro.duracao_s * 1000.0)

    @staticmethod
    def _sem_stream(test_case: QueryTestCase, status: str) -> QueryResult:
        return QueryResult(test_case, [], "", 0.0, status, "", "")

    def cancel(self) -> None:
        """Encerra o container em andamento; a execução volta como cancelada."""
        self._cancelado.set()
        execucao = self._atual
        if execucao is not None:
            encerrar_em_voo(self._cfg, [prefixo_do_container(execucao, self._pasta.name)])

    def close(self) -> None:
        """Nada a liberar: o container de cada execução já foi removido pelo executor."""


def default_run_root(work_dir: str | Path | None = None) -> Path:
    """Pasta-raiz temporária das sessões de um run, em ``work_dir`` (ou no TEMP do motor)."""
    return make_run_root(work_dir, f"novomodelo-load-agent-{os.getpid()}-")
