"""Ferramentas de pós-rodada: comparação de casos e visualização (dashboard).

Cada função envelopa um subcomando de CLI existente. Zero regra de negócio.
"""
from __future__ import annotations

from typing import Literal

from ..adapters.bridge import run_bridge
from ..adapters.envelope import error
from ..adapters.paths import ensure_in_workspace
from ..config import Settings
from .shaping import attach_artifact, cap_envelope
from .annotations import WRITES


#: Vocabulário do `--format` do bridge, publicado como `enum` no schema da tool.
FormatoCompare = Literal["console", "html", "csv", "parquet", "json", "all"]


def _tolerance_type_error(tolerance) -> dict | None:
    if tolerance is None or (isinstance(tolerance, (int, float))
                             and not isinstance(tolerance, bool)):
        return None
    return error(2, "tolerance deve ser número", f"recebido: {tolerance!r}")


def _compare(kind: str, src_dir: str, output_dir: str, tolerance, fmt, out_dir,
             settings: Settings) -> dict:
    argv = ["compare", kind, src_dir, output_dir]
    if tolerance is not None:
        argv += ["--tolerance", str(tolerance)]
    if fmt:
        argv += ["--format", fmt]
    if out_dir:
        argv += ["--out-dir", out_dir]
    env = run_bridge(argv, settings=settings)
    # compare sempre sai com código 0; o veredito está no envelope, não no exit.
    if fmt == "html" and out_dir:
        attach_artifact(env, "report_dir", out_dir)
    return cap_envelope(env, settings)


def register_post_run(mcp, settings: Settings) -> None:
    """Registra as tools de pós-rodada no servidor `mcp`."""

    @mcp.tool(annotations=WRITES)
    def bridge_compare_newave(
        newave_dir: str,
        output_dir: str,
        tolerance: float | None = None,
        fmt: FormatoCompare = "json",
        out_dir: str | None = None,
    ) -> dict:
        """Compara resultados de uma rodada NEWAVE contra a saída Novomodelo convertida.

        `newave_dir`: pasta do caso NEWAVE (com os resultados dele).
        `output_dir`: pasta de SAÍDA do `novomodelo run` do caso convertido
        (a que contém `training/` e `simulation/`), não a pasta do caso.
        `fmt="html"` + `out_dir` geram um relatório multi-aba (custo, sistema,
        balanço energético, rede, convergência, performance, plantas, FPHA);
        o caminho volta em `artifacts.report_dir`. Um formato por chamada; para
        vários, uma chamada por formato. O veredito de aderência está no envelope
        (`status`/`diagnostics`), não no código de saída.
        """
        if (err := ensure_in_workspace(newave_dir, output_dir, out_dir, settings=settings)):
            return err
        if (err := _tolerance_type_error(tolerance)):
            return err
        return _compare("newave", newave_dir, output_dir, tolerance, fmt, out_dir,
                        settings)

    @mcp.tool(annotations=WRITES)
    def bridge_compare_decomp(
        decomp_dir: str,
        output_dir: str,
        tolerance: float | None = None,
        fmt: FormatoCompare = "json",
        out_dir: str | None = None,
    ) -> dict:
        """Compara uma rodada DECOMP contra a saída Novomodelo convertida.

        `decomp_dir`: pasta da revisão DECOMP (com os resultados dele).
        `output_dir`: pasta de SAÍDA do `novomodelo run` do caso convertido.
        Como `bridge_compare_newave` (um formato por chamada; para vários, uma
        chamada por formato); o relatório HTML acrescenta seções de REE,
        restrições e evaporação.
        """
        if (err := ensure_in_workspace(decomp_dir, output_dir, out_dir, settings=settings)):
            return err
        if (err := _tolerance_type_error(tolerance)):
            return err
        return _compare("decomp", decomp_dir, output_dir, tolerance, fmt, out_dir,
                        settings)

    @mcp.tool(annotations=WRITES)
    def bridge_dashboard(case_dir: str) -> dict:
        """Gera um dashboard HTML interativo a partir de resultados do Novomodelo.

        `case_dir`: pasta do CASO (a que contém `output/`), como no bridge; o HTML
        vai para `<case_dir>/dashboard.html`. Devolve o envelope; o
        caminho do HTML gerado aparece no `summary`/`diagnostics` do bridge.
        Nunca devolve o HTML inteiro — apenas metadados e caminho.
        """
        if (err := ensure_in_workspace(case_dir, settings=settings)):
            return err
        env = run_bridge(["dashboard", case_dir], settings=settings)
        return cap_envelope(env, settings)
