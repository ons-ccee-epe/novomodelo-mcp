"""Ferramentas de pré-rodada: validação, conversão e prontidão para simular.

Cada função envelopa um subcomando de CLI existente. Zero regra de negócio.
"""

from __future__ import annotations

from ..adapters import budget
from ..adapters.bridge import run_bridge
from ..adapters.discovery import find_novomodelo
from ..adapters.envelope import error
from ..adapters.novomodelo import case_summary_binding, validate_deck_binding, validate_deck_cli
from ..adapters.paths import ensure_in_workspace
from ..config import Settings
from .annotations import READ_ONLY, WRITES
from .shaping import attach_artifact, cap_envelope, group_diagnostics


def _force_gate(force: bool, dry_run: bool, settings: Settings) -> dict | None:
    """O `--force` do bridge limpa o deck de destino antes de converter."""
    if force and not dry_run and not settings.allow_force:
        return error(
            13,
            "force=True desabilitado",
            "o convert com force apaga o deck de destino; defina "
            "NOVOMODELO_MCP_ALLOW_FORCE=1 para permitir",
        )
    return None


def register_pre_run(mcp, settings: Settings) -> None:
    """Registra as tools de pré-rodada no servidor `mcp`."""

    @mcp.tool(annotations=READ_ONLY)
    def bridge_check_newave(src: str) -> dict:
        """Pré-valida as ENTRADAS de um caso NEWAVE, sem converter (read-only).

        `src`: pasta do caso NEWAVE. Rode isto ANTES de converter para pegar
        problemas de entrada cedo. Devolve o envelope do novomodelo-bridge.
        """
        if err := ensure_in_workspace(src, settings=settings):
            return err
        env = run_bridge(["check", "newave", src], settings=settings)
        return cap_envelope(env, settings)

    @mcp.tool(annotations=WRITES)
    def bridge_convert_newave(
        src: str,
        dst: str,
        validate: bool = True,
        force: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """Converte um caso NEWAVE para deck Novomodelo, escrevendo em `dst`.

        `validate=True` (recomendado) também valida o deck resultante numa
        tacada — é o portão de prontidão pré-rodada. `force` apaga e regrava `dst`
        existente (exige NOVOMODELO_MCP_ALLOW_FORCE=1); `dry_run` não escreve nada.
        Devolve o envelope + o caminho do deck em `artifacts.deck`.
        """
        if err := ensure_in_workspace(src, dst, settings=settings):
            return err
        if err := _force_gate(force, dry_run, settings):
            return err
        argv = ["convert", "newave", src, dst]
        if validate:
            argv.append("--validate")
        if force:
            argv.append("--force")
        if dry_run:
            argv.append("--dry-run")
        env = run_bridge(argv, settings=settings)
        if env.get("exit_code") == 0 and not dry_run:
            attach_artifact(env, "deck", dst)
        return cap_envelope(env, settings)

    @mcp.tool(annotations=READ_ONLY)
    def case_validate(case_dir: str, output_dir: str | None = None) -> dict:
        """Valida se um deck Novomodelo JÁ convertido está pronto para rodar (read-only).

        Envelopa `novomodelo validate <case_dir> --json` (pipeline de validação em 6
        camadas + fases de pré-solver). É o portão de prontidão quando o deck já
        existe e você quer revalidar sem reconverter. Os avisos vêm agrupados por
        tipo e mensagem, com a contagem e até 3 exemplos de cada grupo.
        `output_dir`: pasta de saída de uma rodada anterior, para validar também a
        retomada (equivale a `novomodelo validate --output`).
        """
        if err := ensure_in_workspace(case_dir, output_dir, settings=settings):
            return err
        # Caminho limpo: binding novomodelo.io.validate (saida ESTRUTURADA).
        # Se novomodelo-python nao estiver no venv, degrada para o CLI em modo texto.
        env = validate_deck_binding(case_dir, output_dir=output_dir, settings=settings)
        if env.get("exit_code") == 127 and find_novomodelo(settings) is not None:
            env = validate_deck_cli(case_dir, output_dir=output_dir, settings=settings)
            env["degraded"] = "novomodelo-python ausente; relatorio em modo texto"
        errors = env.get("errors")
        if isinstance(errors, list) and len(errors) > settings.max_diagnostics:
            env["errors_total"] = len(errors)
            env["errors_truncated"] = True
            env["errors"] = errors[: settings.max_diagnostics]
        warnings = env.get("warnings")
        if isinstance(warnings, list):
            grouped = group_diagnostics(warnings, settings.max_diagnostics)
            env["warnings"] = grouped["groups"]
            env["warnings_total"] = grouped["total"]
            env["warnings_groups_total"] = grouped["groups_total"]
            env["warnings_grouped"] = True
        return cap_envelope(env, settings)

    @mcp.tool(annotations=READ_ONLY)
    def case_summary(case_dir: str) -> dict:
        """O caso como o novomodelo o lê e interpreta (`novomodelo.io.load_case`).

        Diferente do `deck_list` (os arquivos), mostra o caso já validado:
        `counts` por tipo (buses, lines, hydros, thermals, contracts,
        pumping_stations, non_controllable_sources, stages) e `items` com
        `{id, name}` de cada tipo em `entries`, com teto. Caso inválido → erro com a mensagem
        do novomodelo. Não grava nada.
        """
        if err := ensure_in_workspace(case_dir, settings=settings):
            return err
        return cap_envelope(
            budget.shrink_to_budget(
                case_summary_binding(
                    case_dir, max_items=budget.row_limit(settings), settings=settings
                ),
                settings,
            ),
            settings,
        )

    @mcp.tool(annotations=READ_ONLY)
    def bridge_check_decomp(src: str) -> dict:
        """Pré-valida as ENTRADAS de um caso DECOMP, sem converter (read-only).

        `src`: pasta da revisão DECOMP. Rode antes de converter. Devolve o
        envelope do novomodelo-bridge.
        """
        if err := ensure_in_workspace(src, settings=settings):
            return err
        env = run_bridge(["check", "decomp", src], settings=settings)
        return cap_envelope(env, settings)

    @mcp.tool(annotations=WRITES)
    def bridge_convert_decomp(
        src: str,
        dst: str,
        validate: bool = True,
        force: bool = False,
        dry_run: bool = False,
        import_fcf: bool = True,
    ) -> dict:
        """Converte uma revisão DECOMP para deck Novomodelo, escrevendo em `dst`.

        Espelha `bridge_convert_newave`: `validate=True` valida o deck resultante,
        `force` apaga e regrava `dst` (exige NOVOMODELO_MCP_ALLOW_FORCE=1), `dry_run` não
        escreve. Caminho do deck em `artifacts.deck`. `import_fcf=False` converte sem importar os cortes da
        FCF declarados no deck (`--no-fcf`); só no DECOMP, o conversor NEWAVE não
        tem essa opção.
        """
        if err := ensure_in_workspace(src, dst, settings=settings):
            return err
        if err := _force_gate(force, dry_run, settings):
            return err
        argv = ["convert", "decomp", src, dst]
        if validate:
            argv.append("--validate")
        if force:
            argv.append("--force")
        if dry_run:
            argv.append("--dry-run")
        if not import_fcf:
            argv.append("--no-fcf")
        env = run_bridge(argv, settings=settings)
        if env.get("exit_code") == 0 and not dry_run:
            attach_artifact(env, "deck", dst)
        return cap_envelope(env, settings)
