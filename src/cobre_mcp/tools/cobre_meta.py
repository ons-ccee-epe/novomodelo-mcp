"""Tools de meta-informação do COBRE: versão/build e export de schema.

Cada função envelopa exatamente um subcomando `cobre`. Zero regra de negócio.
"""
from __future__ import annotations

from ..adapters.cobre import run_cobre, version_cli
from ..adapters.envelope import as_error
from ..adapters.paths import ensure_in_workspace
from ..config import Settings
from .shaping import attach_artifact, cap_envelope


def register_cobre_meta(mcp, settings: Settings) -> None:
    """Registra a Version_Tool (e a Schema_Export_Tool) no servidor `mcp`."""

    @mcp.tool()
    def cobre_version() -> dict:
        """Versão do COBRE, backend do solver e info de build (envelopa `cobre version`).

        Sem parâmetros e sem caminho. `cobre version` emite texto (não aceita
        `--json`); `version_cli` parseia os campos e preserva o texto bruto em
        `raw`. Falhas de transporte (binário ausente, timeout, erro) já voltam
        como Error_Envelope.
        """
        try:
            env = version_cli(settings=settings)
        except Exception as exc:  # noqa: BLE001 - never-raise: exceção vira Error_Envelope, não derruba o stdio
            return as_error(exc)
        return cap_envelope(env, settings)

    @mcp.tool()
    def cobre_schema_export(output_dir: str | None = None) -> dict:
        """Exporta os JSON Schemas de entrada do COBRE (envelopa `cobre schema export`).

        `output_dir` (opcional): pasta de destino, confinada ao workspace. Quando o
        export escreve em disco, o caminho vai em `artifacts.schemas`, nunca o
        conteúdo dos arquivos.
        """
        # Fail-closed antes de qualquer FS: caminho fora das raízes vira envelope 13.
        if (err := ensure_in_workspace(output_dir, settings=settings)):
            return err
        try:
            argv = ["schema", "export"]
            if output_dir is not None:
                argv += ["--output-dir", output_dir]
            env = run_cobre(argv, settings=settings)
            if output_dir is not None and env.get("exit_code") == 0:
                attach_artifact(env, "schemas", output_dir)
            return cap_envelope(env, settings)
        except Exception as exc:  # noqa: BLE001 - never-raise: exceção vira Error_Envelope, não derruba o stdio
            return as_error(exc)
