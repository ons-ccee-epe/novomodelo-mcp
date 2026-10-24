"""Consulta SQL read-only sobre arquivos do workspace, via DuckDB.

Fachada: nenhuma regra de negocio — so leitura. DuckDB e importado de forma
preguicosa (o modulo carrega sem ele; a tool acusa a ausencia com erro claro),
espelhando o tratamento do Polars em adapters/results.py.

Modelo de ameaca (o mesmo de adapters/paths): o agente controla a query. O guard
e fail-closed e roda ANTES de executar:
  1. um unico comando, comecando por SELECT ou WITH (CTE);
  2. nenhuma palavra-chave que escreva/anexe/carregue extensao/mude config
     (COPY, ATTACH, DETACH, INSTALL, LOAD, PRAGMA, SET, CALL, INSERT, UPDATE,
      DELETE, DROP, CREATE, ALTER, EXPORT, IMPORT, VACUUM, CHECKPOINT);
  3. todo literal que aparente caminho de arquivo tem de cair dentro do
     workspace (mesma regra do paths); esquema remoto ("://") e recusado.
Alem do guard textual, a conexao e :memory:, sem autoload de extensao e com
filesystems remotos desabilitados — defesa em profundidade, nao a defesa unica.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..config import Settings
from .envelope import error
from .paths import allowed_roots, refuse_outside

#: Comandos que apenas leem.
_ALLOWED_START = ("SELECT", "WITH")

#: Palavras proibidas em qualquer posicao (fora de literais/comentarios).
#: REPLACE fica de fora de proposito: `SELECT * REPLACE (...)` e leitura valida
#: no DuckDB, e a forma perigosa (CREATE/INSERT OR REPLACE) ja cai em CREATE/INSERT.
_FORBIDDEN = {
    "ATTACH", "DETACH", "COPY", "INSTALL", "LOAD", "PRAGMA", "SET", "CALL",
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "EXPORT", "IMPORT", "VACUUM", "CHECKPOINT",
}

#: Extensoes que marcam um literal como caminho de arquivo.
_PATH_EXT = (".parquet", ".pq", ".csv", ".tsv", ".json", ".ndjson", ".arrow", ".ipc")


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _strip_literals_and_comments(sql: str) -> str:
    """Troca literais '...'/"..." e comentarios (-- e /* */) por espaco.

    Deixa o restante do texto para a analise de palavras-chave, sem que um valor
    dentro de aspas ou de um comentario seja confundido com comando.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and sql[i + 1] == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c == "'":
            i += 1
            while i < n:
                if sql[i] == "'" and i + 1 < n and sql[i + 1] == "'":
                    i += 2
                    continue
                if sql[i] == "'":
                    i += 1
                    break
                i += 1
            out.append(" ")
            continue
        if c == '"':
            i += 1
            while i < n and sql[i] != '"':
                i += 1
            i += 1
            out.append(" ")
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _string_literals(sql: str) -> list[str]:
    """Conteudo dos literais '...' e dos identificadores "..." (com a aspa dobrada
    escapada): o DuckDB le um arquivo por qualquer dos dois. Ignora comentarios."""
    lits: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and sql[i + 1] == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c in "'\"":
            i += 1
            buf: list[str] = []
            while i < n:
                if sql[i] == c and i + 1 < n and sql[i + 1] == c:
                    buf.append(c)
                    i += 2
                    continue
                if sql[i] == c:
                    i += 1
                    break
                buf.append(sql[i])
                i += 1
            lits.append("".join(buf))
            continue
        i += 1
    return lits


def _looks_like_path(lit: str) -> bool:
    low = lit.lower()
    if "://" in lit or "/" in lit or "\\" in lit:
        return True
    return low.endswith(_PATH_EXT)


def guard_sql(query: str, roots: list[Path]) -> dict | None:
    """None se a query e leitura segura e confinada; senao, um envelope de erro.

    Puro (sem DuckDB), para ser testavel isoladamente — e a parte critica.
    """
    if not query or not query.strip():
        return error(22, "query vazia")

    scrubbed = _strip_literals_and_comments(query)

    statements = [s for s in scrubbed.split(";") if s.strip()]
    if len(statements) > 1:
        return error(22, "apenas um comando e permitido (encontrei mais de um)")

    m = re.match(r"[A-Za-z_]+", scrubbed.lstrip())
    kw = m.group(0).upper() if m else ""
    if kw not in _ALLOWED_START:
        return error(13, f"apenas SELECT/WITH (read-only) e permitido; comando: {kw or '?'}")

    words = set(re.findall(r"[A-Za-z_]+", scrubbed.upper()))
    hit = sorted(words & _FORBIDDEN)
    if hit:
        return error(13, f"palavra-chave nao permitida em consulta read-only: {hit}")

    for lit in _string_literals(query):
        if not _looks_like_path(lit):
            continue
        if "://" in lit:
            return error(13, f"acesso remoto nao permitido no SQL: {lit}")
        if roots:
            try:
                rp = Path(lit).expanduser().resolve()
            except OSError as exc:
                return error(22, f"caminho invalido no SQL: {lit}", str(exc))
            if not any(_within(rp, r) for r in roots):
                return refuse_outside(lit, rp, roots)
    return None


def _jsonable(v: Any) -> Any:
    if isinstance(v, (_dt.date, _dt.datetime, _dt.time)):
        return v.isoformat()
    if isinstance(v, _dt.timedelta):
        return v.total_seconds()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).hex()
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


def run_readonly_sql(query: str, *, settings: Settings,
                     max_rows: int | None = None) -> dict[str, Any]:
    """Roda a query (apos o guard) numa conexao DuckDB :memory: endurecida.

    Devolve sempre com teto de linhas; `truncated: true` sinaliza que ha mais.
    """
    roots = allowed_roots(settings)
    if (err := guard_sql(query, roots)):
        return err

    try:
        import duckdb
    except ModuleNotFoundError:
        return error(127, "duckdb nao instalado no ambiente do servidor",
                     "adicione 'duckdb' as dependencias e rode `uv sync`")

    cap = max(1, min(max_rows or settings.max_query_rows, settings.max_query_rows))
    con = duckdb.connect(database=":memory:")
    if roots:
        # Confinamento no motor: o guard textual nao enxerga caminho montado por
        # expressao (chr(47) || ...). Fail-closed: sem ele, a query nao roda.
        try:
            con.execute("SET allowed_directories=?", [[str(r) + os.sep for r in roots]])
            con.execute("SET enable_external_access=false")
        except Exception as exc:  # noqa: BLE001 - qualquer falha aqui recusa a query
            con.close()
            return error(13, "nao foi possivel confinar o SQL ao workspace", str(exc))
    for pragma in (
        "SET autoinstall_known_extensions=false",
        "SET autoload_known_extensions=false",
        "SET allow_community_extensions=false",
        "SET disabled_filesystems="
        "'HTTPFileSystem,S3FileSystem,GCSFileSystem,AzureBlobStorageFileSystem'",
        "SET lock_configuration=true",
    ):
        try:
            con.execute(pragma)
        except Exception:  # noqa: BLE001 - best-effort; o guard textual e a defesa primaria
            pass

    timer = threading.Timer(settings.default_timeout, con.interrupt)
    timer.start()
    try:
        cur = con.execute(query)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(cap + 1)
    except Exception as exc:  # noqa: BLE001 - repassa como erro, nao derruba o servidor
        return error(1, f"falha ao executar SQL: {type(exc).__name__}", str(exc))
    finally:
        timer.cancel()
        con.close()

    truncated = len(rows) > cap
    rows = rows[:cap]
    return {
        "status": "ok",
        "columns": columns,
        "row_count": len(rows),
        "truncated": truncated,
        "rows": [dict(zip(columns, (_jsonable(v) for v in r), strict=True)) for r in rows],
    }
