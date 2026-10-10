"""Ferramentas de pós-rodada: comparação de casos e visualização (dashboard).

Cada função envelopa um subcomando de CLI existente. Zero regra de negócio.
"""
from __future__ import annotations

from ..adapters.bridge import run_bridge
from ..adapters.paths import ensure_in_workspace
from ..adapters.validate import validate_compare_inputs
from ..config import Settings
from .shaping import attach_artifact, cap_envelope


def _compare(kind: str, src_dir: str, case_dir: str, tolerance, fmt, out_dir,
             settings: Settings) -> dict:
    argv = ["compare", kind, src_dir, case_dir]
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

    @mcp.tool()
    def bridge_compare_newave(
        newave_dir: str,
        case_dir: str,
        tolerance: float | None = None,
        fmt: str = "json",
        out_dir: str | None = None,
    ) -> dict:
        """Compara resultados de uma rodada NEWAVE contra a saída Cobre convertida.

        `fmt="html"` + `out_dir` geram um relatório multi-aba (custo, sistema,
        balanço energético, rede, convergência, performance, plantas, FPHA);
        o caminho volta em `artifacts.report_dir`. O veredito de aderência está
        no envelope (`status`/`diagnostics`), não no código de saída.
        """
        if (err := ensure_in_workspace(newave_dir, case_dir, out_dir, settings=settings)):
            return err
        if (err := validate_compare_inputs(tolerance, fmt)):
            return err
        return _compare("newave", newave_dir, case_dir, tolerance, fmt, out_dir,
                        settings)

    @mcp.tool()
    def bridge_compare_decomp(
        decomp_dir: str,
        case_dir: str,
        tolerance: float | None = None,
        fmt: str = "json",
        out_dir: str | None = None,
    ) -> dict:
        """Compara uma rodada DECOMP contra a saída Cobre convertida.

        Como `bridge_compare_newave`; o relatório HTML acrescenta seções de REE,
        restrições e evaporação.
        """
        if (err := ensure_in_workspace(decomp_dir, case_dir, out_dir, settings=settings)):
            return err
        if (err := validate_compare_inputs(tolerance, fmt)):
            return err
        return _compare("decomp", decomp_dir, case_dir, tolerance, fmt, out_dir,
                        settings)

    @mcp.tool()
    def bridge_dashboard(case_dir: str) -> dict:
        """Gera um dashboard HTML interativo a partir de resultados do Cobre.

        `case_dir`: pasta de resultados de um `cobre run`. Devolve o envelope; o
        caminho do HTML gerado aparece no `summary`/`diagnostics` do bridge.
        Nunca devolve o HTML inteiro — apenas metadados e caminho.
        """
        if (err := ensure_in_workspace(case_dir, settings=settings)):
            return err
        env = run_bridge(["dashboard", case_dir], settings=settings)
        return cap_envelope(env, settings)
