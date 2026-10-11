"""Ferramentas de pré-rodada: validação, conversão e prontidão para simular.

Cada função envelopa um subcomando de CLI existente. Zero regra de negócio.
"""
from __future__ import annotations

from ..adapters.bridge import run_bridge
from ..adapters.novomodelo import validate_deck_binding, validate_deck_cli
from ..adapters.discovery import find_novomodelo
from ..adapters.paths import ensure_in_workspace
from ..config import Settings
from .shaping import attach_artifact, cap_envelope


def register_pre_run(mcp, settings: Settings) -> None:
    """Registra as tools de pré-rodada no servidor `mcp`."""

    @mcp.tool()
    def bridge_check_newave(src: str) -> dict:
        """Pré-valida as ENTRADAS de um caso NEWAVE, sem converter (read-only).

        `src`: pasta do caso NEWAVE. Rode isto ANTES de converter para pegar
        problemas de entrada cedo. Devolve o envelope do novomodelo-bridge.
        """
        if (err := ensure_in_workspace(src, settings=settings)):
            return err
        env = run_bridge(["check", "newave", src], settings=settings)
        return cap_envelope(env, settings)

    @mcp.tool()
    def bridge_convert_newave(
        src: str,
        dst: str,
        validate: bool = True,
        force: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """Converte um caso NEWAVE para deck Novomodelo, escrevendo em `dst`.

        `validate=True` (recomendado) também valida o deck resultante numa
        tacada — é o portão de prontidão pré-rodada. `force` sobrescreve `dst`
        existente; `dry_run` não escreve nada. Devolve o envelope + o caminho
        do deck em `artifacts.deck`.
        """
        if (err := ensure_in_workspace(src, dst, settings=settings)):
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

    @mcp.tool()
    def case_validate(case_dir: str) -> dict:
        """Valida se um deck Novomodelo JÁ convertido está pronto para rodar (read-only).

        Envelopa `novomodelo validate <case_dir> --json` (pipeline de validação em 6
        camadas + fases de pré-solver). É o portão de prontidão quando o deck já
        existe e você quer revalidar sem reconverter.
        """
        if (err := ensure_in_workspace(case_dir, settings=settings)):
            return err
        # Caminho limpo: binding novomodelo.io.validate (saida ESTRUTURADA).
        # Se novomodelo-python nao estiver no venv, degrada para o CLI em modo texto.
        env = validate_deck_binding(case_dir, settings=settings)
        if env.get("exit_code") == 127 and find_novomodelo(settings) is not None:
            env = validate_deck_cli(case_dir, settings=settings)
            env["degraded"] = "novomodelo-python ausente; relatorio em modo texto"
        for _k in ("errors", "warnings"):
            _lst = env.get(_k)
            if isinstance(_lst, list) and len(_lst) > settings.max_diagnostics:
                env[f"{_k}_total"] = len(_lst)
                env[f"{_k}_truncated"] = True
                env[_k] = _lst[: settings.max_diagnostics]
        return cap_envelope(env, settings)


    @mcp.tool()
    def bridge_check_decomp(src: str) -> dict:
        """Pré-valida as ENTRADAS de um caso DECOMP, sem converter (read-only).

        `src`: pasta da revisão DECOMP. Rode antes de converter. Devolve o
        envelope do novomodelo-bridge.
        """
        if (err := ensure_in_workspace(src, settings=settings)):
            return err
        env = run_bridge(["check", "decomp", src], settings=settings)
        return cap_envelope(env, settings)

    @mcp.tool()
    def bridge_convert_decomp(
        src: str,
        dst: str,
        validate: bool = True,
        force: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """Converte uma revisão DECOMP para deck Novomodelo, escrevendo em `dst`.

        Espelha `bridge_convert_newave`: `validate=True` valida o deck resultante,
        `force` sobrescreve `dst`, `dry_run` não escreve. Caminho do deck em
        `artifacts.deck`.
        """
        if (err := ensure_in_workspace(src, dst, settings=settings)):
            return err
        argv = ["convert", "decomp", src, dst]
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
