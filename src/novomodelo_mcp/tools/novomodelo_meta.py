"""Tools de meta-informação do NOVOMODELO: versão/build e export de schema.

Cada função envelopa exatamente um subcomando `novomodelo`. Zero regra de negócio.
"""

from __future__ import annotations

from typing import Any

from ..adapters import installer
from ..adapters.envelope import as_error
from ..adapters.novomodelo import run_novomodelo, version_cli
from ..adapters.paths import ensure_in_workspace
from ..config import Settings
from .annotations import DESTRUCTIVE_NET, READ_ONLY, WRITES
from .shaping import attach_artifact, cap_envelope


def register_novomodelo_meta(mcp, settings: Settings) -> None:
    """Registra a Version_Tool (e a Schema_Export_Tool) no servidor `mcp`."""

    @mcp.tool(annotations=READ_ONLY)
    def solver_version() -> dict[str, Any]:
        """Versão do NOVOMODELO, backend do solver e info de build (envelopa `novomodelo version`).

        Sem parâmetros e sem caminho. `novomodelo version` emite texto (não aceita
        `--json`); `version_cli` parseia os campos e preserva o texto bruto em
        `raw`. Falhas de transporte (binário ausente, timeout, erro) já voltam
        como Error_Envelope.
        """
        try:
            env = version_cli(settings=settings)
        except Exception as exc:  # noqa: BLE001 - never-raise: exceção vira Error_Envelope, não derruba o stdio
            return as_error(exc)
        return cap_envelope(env, settings)

    @mcp.tool(annotations=DESTRUCTIVE_NET)
    def install_novomodelo(confirm: bool = False, install_dir: str | None = None) -> dict[str, Any]:
        """Instala o executável `novomodelo` oficial, na versão que este MCP espera.

        Sem `confirm=True`, só mostra o plano: URL do instalador do release
        oficial, SHA-256 esperado, pasta de destino e o comando manual; nada é
        baixado. Com `confirm=True`, baixa o instalador, confere o SHA-256,
        executa e confirma com `novomodelo version`. `install_dir` (absoluta, opcional):
        raiz da instalação (o binário fica em `<install_dir>/bin`); padrão `~/.cargo`.
        O instalador oficial acrescenta a pasta ao PATH do perfil do shell. Sem
        rede, devolve `network_warning` com o comando manual.
        """
        try:
            return cap_envelope(
                installer.install(confirm=confirm, install_dir=install_dir), settings
            )
        except Exception as exc:  # noqa: BLE001 - never-raise: exceção vira Error_Envelope, não derruba o stdio
            return as_error(exc)

    @mcp.tool(annotations=WRITES)
    def schema_export(output_dir: str | None = None) -> dict[str, Any]:
        """Exporta os JSON Schemas de entrada do NOVOMODELO (envelopa `novomodelo schema export`).

        `output_dir` (opcional): pasta de destino, confinada ao workspace. Quando o
        export escreve em disco, o caminho vai em `artifacts.schemas`, nunca o
        conteúdo dos arquivos.
        """
        # Fail-closed antes de qualquer FS: caminho fora das raízes vira envelope 13.
        if err := ensure_in_workspace(output_dir, settings=settings):
            return err
        try:
            argv = ["schema", "export"]
            if output_dir is not None:
                argv += ["--output-dir", output_dir]
            env = run_novomodelo(argv, settings=settings)
            if output_dir is not None and env.get("exit_code") == 0:
                attach_artifact(env, "schemas", output_dir)
            return cap_envelope(env, settings)
        except Exception as exc:  # noqa: BLE001 - never-raise: exceção vira Error_Envelope, não derruba o stdio
            return as_error(exc)
