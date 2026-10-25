"""Manipulador de decks: ler JSON/Parquet e editar DENTRO do contrato de dados.

Segurança: toda tool confina o caminho à raiz permitida (ver adapters/paths).
Edições fazem backup + escrita atômica; JSON valida contra o schema oficial;
Parquet preserva colunas/dtypes. `ensure_valid` revalida (estruturado) e
reverte se reprovar. `force` só é aceito com NOVOMODELO_MCP_ALLOW_FORCE.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..adapters import deck_io
from ..adapters import reference as REF
from ..adapters.novomodelo import validate_deck_binding
from ..adapters.envelope import error
from ..adapters.obs import log
from ..adapters.paths import allowed_roots, ensure_in_workspace
from ..config import Settings
from .shaping import fit_to_budget, cap_envelope
from .annotations import DESTRUCTIVE, READ_ONLY


def register_deck(mcp, settings: Settings) -> None:
    """Registra as tools do manipulador de decks no servidor `mcp`."""

    def _guard(*paths: str) -> dict | None:
        return ensure_in_workspace(*paths, settings=settings)

    @mcp.tool(annotations=READ_ONLY)
    def deck_list(case_dir: str, max_files: int = 500) -> dict:
        """Mapa do caso: entradas (o deck), rodadas e outros arquivos.

        `files`: cada arquivo de ENTRADA (.json/.parquet) com caminho, tamanho e,
        quando houver, o tipo de schema (`schema`, use em schema_get). São os
        caminhos que deck_read_*, deck_sql e deck_edit_* recebem.
        `runs`: cada pasta de SAÍDA de rodada (tem training/metadata.json) numa linha
        (nº de arquivos, tamanho, marcos). Para os dados, use results_status /
        results_query com `output_dir` = essa pasta; o conteúdo não é listado.
        `others`: demais arquivos (backups, dashboard…), só o nome.
        Teto: `max_files` entradas (`files_truncated` avisa).
        """
        if (err := _guard(case_dir)):
            return err
        root = Path(case_dir)
        if not root.is_dir():
            return error(2, f"nao e uma pasta: {case_dir}")
        types = set(REF.list_schema_types(settings))
        return cap_envelope(deck_io.case_map(case_dir, types, max(1, int(max_files))),
                            settings)

    @mcp.tool(annotations=READ_ONLY)
    def deck_read_json(path: str) -> dict:
        """Lê um arquivo JSON do deck (com teto de tamanho).

        Recusa arquivos acima de NOVOMODELO_MCP_MAX_READ_BYTES — para arquivos grandes,
        edite por caminho com deck_edit_json em vez de ler tudo.
        """
        if (err := _guard(path)):
            return err
        if not os.path.exists(path):
            return error(2, f"arquivo nao existe: {path}")
        size = os.path.getsize(path)
        if size > settings.max_read_bytes:
            return error(7, f"arquivo grande demais para leitura direta ({size} bytes)",
                         f"teto: {settings.max_read_bytes} (NOVOMODELO_MCP_MAX_READ_BYTES)")
        try:
            content = deck_io.read_json(path)
        except Exception as exc:  # noqa: BLE001 - repassa como erro, nao derruba
            return error(1, f"falha ao ler JSON: {exc}")
        return {"status": "ok", "path": path, "bytes": size, "content": content}

    @mcp.tool(annotations=READ_ONLY)
    def deck_read_parquet(path: str, columns: list[str] | None = None,
                          limit: int | None = None) -> dict:
        """Lê um Parquet do deck: schema, nº de linhas e uma AMOSTRA (nunca tudo)."""
        if (err := _guard(path)):
            return err
        n = min(limit or settings.max_rows, settings.max_rows)
        try:
            out = deck_io.read_parquet_summary(path, columns=columns, limit=n)
        except Exception as exc:  # noqa: BLE001
            return error(1, f"falha ao ler Parquet: {exc}")
        out["status"] = "ok"
        return fit_to_budget(out, settings, "head")

    @mcp.tool(annotations=READ_ONLY)
    def deck_describe_parquet(path: str) -> dict:
        """Estatísticas de um Parquet do deck (schema + describe por coluna)."""
        if (err := _guard(path)):
            return err
        try:
            out = deck_io.describe_parquet(path)
        except Exception as exc:  # noqa: BLE001
            return error(1, f"falha ao descrever: {exc}")
        out["status"] = "ok"
        return out


    @mcp.tool(annotations=READ_ONLY)
    def deck_sql(query: str, max_rows: int | None = None) -> dict:
        """Consulta SQL read-only (DuckDB) sobre Parquet/CSV/JSON do deck ou dos resultados.

        Para AGREGAR / FILTRAR / juntar o que as outras tools nao cobrem: contagem
        condicional, min/max e P10/P90 por usina ou estagio, joins entre parquets.
        Aponte os arquivos por CAMINHO ABSOLUTO em read_parquet('/caminho/arq.parquet')
        (tambem read_csv/read_json).

        So leitura: apenas SELECT/WITH; COPY/ATTACH/INSTALL/escrita sao recusados.
        Todo caminho referenciado precisa estar dentro do workspace
        (NOVOMODELO_MCP_WORKSPACE); acesso remoto e a caminhos de fora e negado. A saida
        tem teto de tamanho (NOVOMODELO_MCP_MAX_RESPONSE_KB) e `truncated: true` avisa que
        ha mais — refine com agregacao/LIMIT.

        Ex.: SELECT hydro_id, min(value_m3s) AS min_v, max(value_m3s) AS max_v,
                    count(*) FILTER (WHERE value_m3s < 0) AS n_neg
             FROM read_parquet('/.../scenarios/inflow_history.parquet')
             GROUP BY hydro_id ORDER BY min_v LIMIT 20
        """
        from ..adapters.sql import run_readonly_sql
        log(settings, "deck_sql", query=query, max_rows=max_rows)
        return run_readonly_sql(query, settings=settings, max_rows=max_rows)

    @mcp.tool(annotations=DESTRUCTIVE)
    def deck_edit_json(path: str, changes: list[dict], dry_run: bool = False,
                       ensure_valid: bool = False, force: bool = False) -> dict:
        """Edita valores de um JSON do deck por caminho, DENTRO do contrato.

        `changes`: lista de {"path": "training.stopping_rules[0].limit", "value": 80}.
        Valida contra o JSON Schema oficial da versão instalada (variável
        `NOVOMODELO_MCP_SCHEMAS_DIR`, senão `novomodelo schema export`, senão os schemas
        embutidos); backup em `<arquivo>.bak` + escrita atômica. `dry_run` não grava.
        `ensure_valid=True` revalida o caso (estruturado) e REVERTE se reprovar.
        `force=True` só é aceito com NOVOMODELO_MCP_ALLOW_FORCE=1.
        """
        if (err := _guard(path)):
            return err
        if force and not settings.allow_force:
            return error(13, "force=True desabilitado",
                         "defina NOVOMODELO_MCP_ALLOW_FORCE=1 para gravar violando o schema")
        result = deck_io.edit_json(path, changes, schemas_dir=REF.schemas_root(settings),
                                   dry_run=dry_run, force=force)
        if result.get("status") != "ok" or not result.get("written"):
            return result
        if ensure_valid:
            case = deck_io.find_case_dir(path, stop_at=allowed_roots(settings))
            if case is None or ensure_in_workspace(case, settings=settings):
                result["case_validation"] = "pulada (raiz do caso nao encontrada no workspace)"
                return result
            v = validate_deck_binding(case, settings=settings)
            if v.get("exit_code") == 127:
                result["case_validation"] = "pulada (novomodelo-python ausente)"
                return result
            if v.get("status") != "ok":
                deck_io.restore_backup(path)
                return {"status": "error", "reverted": True, "path": path,
                        "changes": result.get("changes"),
                        "validation": cap_envelope(v, settings),
                        "diagnostics": ["validacao reprovou — edicao revertida"]}
            result["case_validation"] = "ok"
        return result

    @mcp.tool(annotations=DESTRUCTIVE)
    def deck_edit_parquet(path: str, where: dict, set_values: dict,
                          dry_run: bool = False) -> dict:
        """Edita células de um Parquet do deck PRESERVANDO o schema (colunas/dtypes)."""
        if (err := _guard(path)):
            return err
        return deck_io.edit_parquet(path, where, set_values, dry_run=dry_run)
